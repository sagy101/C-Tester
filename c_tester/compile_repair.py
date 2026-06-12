"""LLM-assisted compile-only repair helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Callable, Protocol

from .checker_assistant import LLMProvider, complete_json_with_schema


COMPILE_REPAIR_SYSTEM_PROMPT = (
    "You are a C compilation repair assistant for intro-to-C homework submissions. "
    "Goal: make the submitted C source compile with the smallest compile-only edit. "
    "Preserve the student's apparent algorithm, prompts, output wording, data flow, and mistakes. "
    "Do not improve correctness, scoring behavior, formatting, edge-case handling, or assignment logic. "
    "Return fixed_candidate when the failure is a clear compile-only issue. Return too_bad only when compiling "
    "requires guessing missing business logic or replacing the student's intended algorithm. "
    "Return only JSON matching the schema."
)
COMPILE_REPAIR_DECISION_RUBRIC = {
    "fixed_candidate_when": [
        "The compiler points to local syntax or structure that can be repaired without changing the algorithm.",
        "Examples: missing semicolon or comma; unmatched brace/parenthesis/bracket; malformed declaration; typo in a C keyword or standard function casing; missing standard include for a used standard function; wrong entry-point spelling such as main1/Main when the body is otherwise the submitted program; linker error for missing main when the submitted entry point is obvious.",
        "The change is mechanical and would not alter what inputs are read, what outputs are intended, or which formula/loop/condition the student wrote.",
    ],
    "too_bad_when": [
        "The code is missing a substantial function/body/algorithm and the intended logic is not present.",
        "The only way to compile is to invent assignment-specific behavior, formulas, loop bounds, divisor/reverse-number logic, or output text.",
        "The requested edit would fix a logic bug rather than a compile error, such as changing = to == in a condition, changing loop limits, changing integer division behavior, adding missing edge-case handling, or replacing an incorrect algorithm with a correct one.",
    ],
    "self_check_before_too_bad": [
        "Identify the first compiler error.",
        "Ask: can one or two local syntax/declaration/include/entry-point edits make this compile while preserving the student's behavior?",
        "If yes, return fixed_candidate. If no, return too_bad with a concise reason.",
    ],
}
COMPILE_REPAIR_VALIDATION_EXAMPLES = {
    "q1_sum_and_average": [
        {
            "compile_issue": "missing semicolon after scanf or assignment",
            "expected_decision": "fixed_candidate",
            "boundary": "Add punctuation only; do not change the formula or prompts.",
        },
        {
            "compile_issue": "missing #include <stdio.h> while using printf or scanf",
            "expected_decision": "fixed_candidate",
            "boundary": "Add the standard include only; do not rewrite I/O behavior.",
        },
        {
            "compile_issue": "main1 or Main is used instead of main",
            "expected_decision": "fixed_candidate",
            "boundary": "Rename the obvious entry point only.",
        },
        {
            "compile_issue": "malformed declaration such as int a b;",
            "expected_decision": "fixed_candidate",
            "boundary": "Repair declaration syntax only when the intended variables are clear.",
        },
    ],
    "q2_loops_divisors_or_reverse_number": [
        {
            "compile_issue": "missing closing brace in a for or while block",
            "expected_decision": "fixed_candidate",
            "boundary": "Close the syntactic block without moving logic across branches.",
        },
        {
            "compile_issue": "undeclared identifier caused by a clear local typo",
            "expected_decision": "fixed_candidate",
            "boundary": "Fix the local spelling only when it matches an existing variable.",
        },
        {
            "compile_issue": "bad for syntax such as for(i = 0; i < n i++)",
            "expected_decision": "fixed_candidate",
            "boundary": "Add missing separators only; do not alter loop bounds.",
        },
        {
            "compile_issue": "missing parenthesis in a condition such as while (num > 0 {",
            "expected_decision": "fixed_candidate",
            "boundary": "Balance delimiters only.",
        },
    ],
    "q3_arrays_strings_or_max_min": [
        {
            "compile_issue": "broken array declaration such as int arr[n",
            "expected_decision": "fixed_candidate",
            "boundary": "Balance brackets only when the declaration is otherwise clear.",
        },
        {
            "compile_issue": "missing quote in a printf string literal",
            "expected_decision": "fixed_candidate",
            "boundary": "Close the literal without changing the printed words.",
        },
        {
            "compile_issue": "helper function is called before a visible prototype",
            "expected_decision": "fixed_candidate",
            "boundary": "Add a prototype or move declarations without changing the function body.",
        },
        {
            "compile_issue": "no usable C entry point due to void main or missing main symbol",
            "expected_decision": "fixed_candidate",
            "boundary": "Use a standard main signature only when the program body is obvious.",
        },
    ],
    "too_bad_examples": [
        "empty file or comments only",
        "missing the whole assignment algorithm or core function body",
        "custom helper is referenced but neither its body nor intended behavior is present",
        "unrelated fragments have no clear entry point or data flow",
    ],
}
COMPILE_FIX_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["fixed_candidate", "too_bad"]},
        "too_bad": {"type": "boolean"},
        "fixed_code": {"type": "string"},
        "compile_issue": {"type": "string"},
        "fix_reason": {"type": "string"},
        "changes_made": {"type": "string"},
        "risk_note": {"type": "string"},
        "decision_check": {"type": "string"},
    },
    "required": [
        "status",
        "too_bad",
        "fixed_code",
        "compile_issue",
        "fix_reason",
        "changes_made",
        "risk_note",
        "decision_check",
    ],
    "additionalProperties": False,
}

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
        "decision_rubric": COMPILE_REPAIR_DECISION_RUBRIC,
        "validation_examples": COMPILE_REPAIR_VALIDATION_EXAMPLES,
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
            "decision_check": "one short sentence explaining why this is compile-only or why it truly requires too_bad",
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
        report_repair_progress(progress_callback, f"repair attempt {attempt_number}/{max_attempts}")

        prompt = build_compile_fix_prompt(original_code, current_compile_error, attempts)
        response = complete_json_with_schema(provider, prompt, response_schema=COMPILE_FIX_RESPONSE_SCHEMA)
        suggestion = parse_compile_fix_response(response)
        if suggestion.too_bad:
            result, current_compile_error, should_continue = handle_too_bad_suggestion(
                original_code,
                current_compile_error,
                attempts,
                student_repair_dir,
                attempt_number,
                max_attempts,
                repair_penalty,
                compile_func,
            )
            if result:
                return result
            if should_continue:
                continue

        result, current_compile_error = try_llm_candidate_repair(
            suggestion,
            attempts,
            student_repair_dir,
            attempt_number,
            repair_penalty,
            compile_func,
        )
        if result:
            return result

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


def report_repair_progress(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback:
        progress_callback(message)


def try_llm_candidate_repair(
    suggestion: CompileFixSuggestion,
    attempts: list[CompileRepairAttempt],
    student_repair_dir: str,
    attempt_number: int,
    repair_penalty: float,
    compile_func: CompileFunction,
) -> tuple[CompileRepairResult | None, str]:
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
    if not compiled:
        return None, compile_error or "Compilation failed without compiler output."
    result = CompileRepairResult(
        status="fixed",
        attempts=attempt_number,
        fixed_code_path=candidate_path,
        executable_path=executable or "",
        repair_note=suggestion.fix_reason or suggestion.compile_issue or "compile-only repair applied",
        repair_penalty=repair_penalty,
        attempts_history=tuple(attempts),
    )
    write_repair_report(student_repair_dir, result)
    return result, compile_error or ""


def handle_too_bad_suggestion(
    original_code: str,
    current_compile_error: str,
    attempts: list[CompileRepairAttempt],
    student_repair_dir: str,
    attempt_number: int,
    max_attempts: int,
    repair_penalty: float,
    compile_func: CompileFunction,
) -> tuple[CompileRepairResult | None, str, bool]:
    del original_code, repair_penalty, compile_func
    if attempt_number < max_attempts:
        return None, build_too_bad_challenge_error(current_compile_error, attempts), True
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
    return result, current_compile_error, False


def build_too_bad_challenge_error(current_compile_error: str, attempts: list[CompileRepairAttempt]) -> str:
    previous_reasons = [attempt.fix_reason or attempt.compile_issue for attempt in attempts if attempt.fix_reason or attempt.compile_issue]
    history_text = "; ".join(previous_reasons[-3:]) if previous_reasons else "none"
    return (
        f"{current_compile_error}\n\n"
        "The previous LLM response returned too_bad. Re-evaluate using decision_rubric and self_check_before_too_bad. "
        "Do not return too_bad merely because the compiler output is noisy or there are many errors after the first one. "
        "If the first/root error can be fixed by a local compile-only edit that preserves the student's behavior, return "
        "fixed_candidate. Return too_bad only if compiling requires inventing missing assignment logic. "
        f"Previous attempt reasons: {history_text}"
    )


def write_repair_report(repair_dir: str, result: CompileRepairResult):
    os.makedirs(repair_dir, exist_ok=True)
    report_path = os.path.join(repair_dir, "repair_report.json")
    with open(report_path, "w", encoding="utf-8") as report_file:
        json.dump(asdict(result), report_file, indent=2, ensure_ascii=False)
