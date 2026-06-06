"""LLM-assisted compile-only repair helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Callable, Protocol

from .checker_assistant import LLMProvider


COMPILE_REPAIR_SYSTEM_PROMPT = (
    "You are a C compilation repair assistant. Your only job is to make the submitted C code compile. "
    "You must preserve the student's apparent logic and output behavior. Do not improve the algorithm, "
    "change business logic, change prompts/output text, add new features, or infer missing intended behavior. "
    "If the code cannot be made to compile without making meaningful assumptions about the student's intended "
    "logic, return too_bad. Return only JSON matching the schema."
)

TOO_BAD_EXCEL_NOTE = "code cannot be made to compile without guessing the student's intended logic."


@dataclass(frozen=True)
class CompileFixSuggestion:
    status: str
    too_bad: bool
    fixed_code: str
    compile_issue: str
    fix_reason: str
    changes_made: str
    risk_note: str


@dataclass(frozen=True)
class CompileRepairAttempt:
    attempt: int
    candidate_path: str
    candidate_code: str
    compile_error: str
    compile_issue: str
    fix_reason: str
    changes_made: str
    risk_note: str
    compiled: bool


@dataclass(frozen=True)
class CompileRepairResult:
    status: str
    attempts: int
    fixed_code_path: str
    executable_path: str
    repair_note: str
    repair_penalty: float
    attempts_history: tuple[CompileRepairAttempt, ...]

    @property
    def fixed(self) -> bool:
        return self.status == "fixed"


class CompileFunction(Protocol):
    def __call__(self, c_file: str) -> tuple[str | None, str | None]:
        ...


ProgressCallback = Callable[[str], None]


def build_compile_fix_prompt(
    original_code: str,
    current_compile_error: str,
    attempt_history: list[CompileRepairAttempt] | tuple[CompileRepairAttempt, ...],
) -> str:
    """Build a context-minimal prompt that excludes student/question metadata."""
    payload = {
        "task": "compile_fix",
        "system_prompt": COMPILE_REPAIR_SYSTEM_PROMPT,
        "original_code": original_code,
        "current_compile_error": current_compile_error,
        "attempt_history": [
            {
                "attempt": attempt.attempt,
                "candidate_code": attempt.candidate_code,
                "compile_error": attempt.compile_error,
                "brief_reason": attempt.fix_reason,
            }
            for attempt in attempt_history
        ],
        "response_schema": {
            "status": "fixed_candidate | too_bad",
            "too_bad": "boolean",
            "fixed_code": "full C source when status=fixed_candidate, otherwise empty string",
            "compile_issue": "one short sentence describing the compiler issue",
            "fix_reason": "one very brief sentence describing what was changed and why",
            "changes_made": "short bullet-style string, max 2-3 compile-only items",
            "risk_note": "empty or one short sentence if the fix might be unsafe",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_compile_fix_response(response: dict) -> CompileFixSuggestion:
    status = str(response.get("status", "")).strip()
    too_bad = bool(response.get("too_bad", False)) or status == "too_bad"
    fixed_code = clean_fixed_code(str(response.get("fixed_code", "") or ""))
    if too_bad:
        status = "too_bad"
        fixed_code = ""
    elif status != "fixed_candidate" or not fixed_code.strip():
        status = "too_bad"
        too_bad = True
        fixed_code = ""

    return CompileFixSuggestion(
        status=status,
        too_bad=too_bad,
        fixed_code=fixed_code,
        compile_issue=brief_text(response.get("compile_issue", "")),
        fix_reason=brief_text(response.get("fix_reason", "")),
        changes_made=brief_text(response.get("changes_made", "")),
        risk_note=brief_text(response.get("risk_note", "")),
    )


def clean_fixed_code(code: str) -> str:
    stripped = code.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip() + "\n"
    return stripped + ("\n" if stripped else "")


def brief_text(value, fallback: str = "") -> str:
    text = " ".join(str(value or fallback).split())
    return text[:300]


def repair_compilation_failure(
    source_path: str,
    original_compile_error: str,
    provider: LLMProvider,
    compile_func: CompileFunction,
    max_attempts: int = 3,
    repair_penalty: float = 10,
    repair_root: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> CompileRepairResult:
    with open(source_path, "r", encoding="utf-8", errors="ignore") as source_file:
        original_code = source_file.read()

    if repair_root is None:
        repair_root = os.path.join(os.path.dirname(os.path.dirname(source_path)), "llm_fixed")
    student_id = os.path.splitext(os.path.basename(source_path))[0]
    student_repair_dir = os.path.join(repair_root, student_id)
    os.makedirs(student_repair_dir, exist_ok=True)

    attempts: list[CompileRepairAttempt] = []
    current_compile_error = original_compile_error

    for attempt_number in range(1, max_attempts + 1):
        if progress_callback:
            progress_callback(f"repair attempt {attempt_number}/{max_attempts}")

        prompt = build_compile_fix_prompt(original_code, current_compile_error, attempts)
        response = provider.complete_json(prompt)
        suggestion = parse_compile_fix_response(response)
        if suggestion.too_bad:
            result = CompileRepairResult(
                status="too_bad",
                attempts=attempt_number,
                fixed_code_path="",
                executable_path="",
                repair_note=TOO_BAD_EXCEL_NOTE,
                repair_penalty=0,
                attempts_history=tuple(attempts),
            )
            write_repair_report(student_repair_dir, result)
            return result

        candidate_path = os.path.join(student_repair_dir, f"attempt_{attempt_number}.c")
        with open(candidate_path, "w", encoding="utf-8", newline="\n") as candidate_file:
            candidate_file.write(suggestion.fixed_code)

        executable, compile_error = compile_func(candidate_path)
        compiled = compile_error is None and executable is not None
        attempt = CompileRepairAttempt(
            attempt=attempt_number,
            candidate_path=candidate_path,
            candidate_code=suggestion.fixed_code,
            compile_error=compile_error or "",
            compile_issue=suggestion.compile_issue,
            fix_reason=suggestion.fix_reason,
            changes_made=suggestion.changes_made,
            risk_note=suggestion.risk_note,
            compiled=compiled,
        )
        attempts.append(attempt)
        if compiled:
            result = CompileRepairResult(
                status="fixed",
                attempts=attempt_number,
                fixed_code_path=candidate_path,
                executable_path=executable,
                repair_note=suggestion.fix_reason or suggestion.compile_issue or "compile-only repair applied",
                repair_penalty=repair_penalty,
                attempts_history=tuple(attempts),
            )
            write_repair_report(student_repair_dir, result)
            return result
        current_compile_error = compile_error or "Compilation failed without compiler output."

    result = CompileRepairResult(
        status="failed",
        attempts=max_attempts,
        fixed_code_path=attempts[-1].candidate_path if attempts else "",
        executable_path="",
        repair_note=attempts[-1].compile_issue if attempts else "compile repair failed",
        repair_penalty=0,
        attempts_history=tuple(attempts),
    )
    write_repair_report(student_repair_dir, result)
    return result


def write_repair_report(repair_dir: str, result: CompileRepairResult):
    os.makedirs(repair_dir, exist_ok=True)
    report_path = os.path.join(repair_dir, "repair_report.json")
    with open(report_path, "w", encoding="utf-8") as report_file:
        json.dump(asdict(result), report_file, indent=2, ensure_ascii=False)
