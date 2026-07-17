"""Post-scoring review helpers for explaining grading deductions."""

from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
import json
import os
import re
from typing import Any

import pandas as pd

from .checker_assistant import LLMProvider, complete_json_with_schema
from . import configuration
from .workflow_status import normalize_deduction_cause


MAX_PROMPT_TEXT = 12000
DEFAULT_MAX_FAILED_CASES = 12
SCORE_REVIEW_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "deduction_is_plausible": {"type": "boolean"},
        "deduction_caused_by": {
            "type": "string",
            "enum": ["student_code", "checker_or_app", "unclear"],
        },
        "root_causes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "failed_inputs": {"type": "array", "items": {"type": "string"}},
                    "deduction_impact": {"type": "string"},
                    "examples": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "input": {"type": "string"},
                                "expected_output": {"type": "string"},
                                "actual_output": {"type": "string"},
                                "why_it_failed": {"type": "string"},
                            },
                            "required": ["input", "expected_output", "actual_output", "why_it_failed"],
                        },
                    },
                },
                "required": ["issue", "failed_inputs", "deduction_impact", "examples"],
            },
        },
        "inline_comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer", "nullable": True},
                    "comment": {"type": "string"},
                },
                "required": ["line", "comment"],
            },
        },
        "fix_to_full_score": {"type": "string"},
        "risk_note": {"type": "string"},
    },
    "required": [
        "summary",
        "deduction_is_plausible",
        "deduction_caused_by",
        "root_causes",
        "inline_comments",
        "fix_to_full_score",
        "risk_note",
    ],
    "additionalProperties": False,
}
COMMON_INTRO_C_LOGIC_RUBRIC = {
    "assignment_instead_of_comparison": (
        "Code compiles but uses assignment in a condition, for example if (x = 5) instead of if (x == 5). "
        "Treat this as a logic issue, not a compile repair issue."
    ),
    "integer_division": (
        "Code compiles but uses integer division where a fractional result is expected, for example sum / count "
        "instead of casting or using a floating operand."
    ),
    "off_by_one_loop_or_index": (
        "Code compiles but loops one too many or one too few times, commonly from <= versus < or incorrect "
        "zero-based array bounds."
    ),
    "scanf_runtime_or_format_misuse": (
        "Code compiles but reads data incorrectly, such as missing & for numeric scanf targets or using %f for "
        "a double where scanf expects %lf."
    ),
    "wrong_algorithm_condition": (
        "Code compiles but the algorithm condition is wrong, for example missing a divisor boundary, stopping a "
        "reverse-number loop early, or using the wrong comparison branch."
    ),
}


@dataclass(frozen=True)
class ReviewFailure:
    input_value: str
    expected_output: str
    actual_output: str
    reason: str = ""


@dataclass(frozen=True)
class ReviewCase:
    student_id: str
    anonymized_label: str
    question: str
    question_score: float
    final_grade: float
    notes: str
    grade_text: str
    student_output_text: str
    expected_output_text: str
    code_path: str
    code_text: str
    code_source: str
    failed_cases: tuple[ReviewFailure, ...] = ()
    excel_fields: dict[str, Any] = field(default_factory=dict)
    final_fields: dict[str, Any] = field(default_factory=dict)
    repair_metadata: dict[str, Any] = field(default_factory=dict)
    grading_policy: dict[str, Any] = field(default_factory=dict)
    review_path: str = ""
    saved_review: dict[str, Any] | None = None

    @property
    def reviewed(self) -> bool:
        return bool(self.saved_review)


@dataclass(frozen=True)
class ReviewResult:
    student_id: str
    anonymized_label: str
    question: str
    review_path: str
    response: dict[str, Any]
    status: str = "reviewed"


def load_review_cases(
    questions: list[str],
    max_failed_cases: int = DEFAULT_MAX_FAILED_CASES,
    grading_policy: dict[str, Any] | None = None,
) -> list[ReviewCase]:
    final_df = _read_excel_if_exists("final_grades.xlsx")
    final_by_id = _rows_by_id(final_df)
    cases: list[ReviewCase] = []
    policy = grading_policy or default_grading_policy()

    for question in questions:
        question_df = _read_excel_if_exists(os.path.join(question, f"{question}_grades_to_upload.xlsx"))
        if question_df.empty:
            continue
        for _, row in question_df.iterrows():
            student_id = str(row.get("ID_number", "")).strip()
            if not student_id:
                continue
            anonymized_label = f"student_{len(cases) + 1:03d}"
            cases.append(_build_review_case(question, row.to_dict(), final_by_id.get(student_id, {}), anonymized_label, max_failed_cases, policy))

    return sorted(cases, key=lambda item: (item.question, _sort_score(item.question_score), item.student_id))


def build_score_review_prompt(case: ReviewCase) -> str:
    student_id = case.student_id
    payload = {
        "task": "review_score_deduction",
        "role": (
            "You explain deterministic C homework grading deductions to a human grader. "
            "You do not change the grade, do not assign a replacement score, and do not need student identity."
        ),
        "student_label": case.anonymized_label,
        "question": case.question,
        "question_focus": (
            f"Review only {case.question}. The student_code may contain all homework questions in one file; "
            f"ignore other question functions unless they directly call, dispatch to, or change behavior for {case.question}."
        ),
        "assigned_question_score": case.question_score,
        "assigned_final_grade": case.final_grade,
        "grading_policy": case.grading_policy,
        "common_intro_c_logic_rubric": COMMON_INTRO_C_LOGIC_RUBRIC,
        "artifact_guide": {
            "assigned_question_score": "The deterministic score for this question after test-case scoring and question-level adjustments.",
            "question_focus": "The scope boundary for the review. Explain only the selected question even if the same C file contains other questions.",
            "assigned_final_grade": "The final weighted grade after question weights and final/report-level penalties.",
            "notes": "The final Excel comments/notes shown to the grader for this row.",
            "code_source": "Whether student_code is the original submitted code or the LLM-repaired code used after a successful compile repair.",
            "student_code": "The submitted C code used for review. If compile repair succeeded, this is the repaired code; otherwise it is the original submitted code.",
            "failed_cases": "Parsed discrepancy blocks from the grade text. Each item contains one input, the expected output for that input, the actual student output for that input, and the deterministic checker reason when available.",
            "student_output_by_input": "Raw captured stdout from running this student's program for all test inputs.",
            "expected_output_by_input": "Raw reference stdout produced by original_sol.c for all test inputs.",
            "grade_text": "The deterministic grader's text report for this question.",
            "excel_fields": "The per-question Excel row for this student, excluding ID_number.",
            "final_fields": "The final Excel row for this student, excluding ID_number.",
            "repair_metadata": "Compile-repair report, if one exists; any real ID in paths is redacted.",
            "grading_policy": "The scoring and penalty settings active when this review is being performed.",
            "common_intro_c_logic_rubric": "Common compiling-but-wrong beginner C mistakes to consider when grouping failures.",
        },
        "notes": _anonymize_value(case.notes, student_id),
        "code_source": case.code_source,
        "student_code": _anonymize_value(case.code_text[:MAX_PROMPT_TEXT], student_id),
        "failed_cases": [_anonymize_value(failure.__dict__, student_id) for failure in case.failed_cases],
        "grade_text": _anonymize_value(case.grade_text[:MAX_PROMPT_TEXT], student_id),
        "student_output_by_input": _anonymize_value(case.student_output_text[:MAX_PROMPT_TEXT], student_id),
        "expected_output_by_input": _anonymize_value(case.expected_output_text[:MAX_PROMPT_TEXT], student_id),
        "excel_fields": _anonymize_value(_public_excel_fields(case.excel_fields), student_id),
        "final_fields": _anonymize_value(_public_excel_fields(case.final_fields), student_id),
        "repair_metadata": _anonymize_value(case.repair_metadata, student_id),
        "instructions": (
            f"Focus strictly on {case.question}. If the C file contains Q1/Q2/Q3 together, discuss only the function, dispatch path, shared helper, or main branch that affects {case.question}. "
            "Do not critique unrelated question functions. "
            "Use expected_output_by_input and failed_cases as the reference behavior, and use "
            "student_output_by_input plus student_code as the student's behavior. Group failures by likely root cause. "
            "For each root cause, include 1-3 concrete examples copied from failed_cases with input, expected output, actual output, and why that example demonstrates the issue. "
            "Explain how one code issue can fail multiple inputs and connect that to the assigned score/notes using grading_policy. "
            "If notes or final_fields mention preprocessing/submission errors such as RAR extraction, naming, missing files, or nested subfolder issues, explain them as submission penalties rather than code-output failures. "
            "If code_source is repaired, include the compile_repair penalty from grading_policy and repair_metadata when explaining the final deduction. "
            "Describe why the observed deductions are plausible or where a grader should double-check. "
            "Set deduction_caused_by to exactly one of: student_code, checker_or_app, or unclear. "
            "Use student_code when the student's logic, missing implementation, crash, wrong values, or genuinely missing required output facts caused the deduction. "
            "Use checker_or_app when the student's output is semantically equivalent to the expected output and the deduction comes from checker/parser/label/anchor/phrasing sensitivity or an application defect; in that case set deduction_is_plausible to false. "
            "Use unclear only when the evidence is insufficient to choose. "
            "Suggest the smallest question-specific fix needed to pass all inputs for this question. "
            "Do not recommend style cleanup, refactors, rewrites, or edits to unrelated questions unless they are required for this question to pass. "
            "Return inline comments using 1-based line numbers from student_code when possible."
        ),
        "response_schema": {
            "summary": "short grader-facing explanation",
            "deduction_is_plausible": "boolean",
            "deduction_caused_by": "student_code | checker_or_app | unclear",
            "root_causes": [
                {
                    "issue": "logic issue",
                    "failed_inputs": ["input values"],
                    "deduction_impact": "how this affected the score",
                    "examples": [
                        {
                            "input": "input value",
                            "expected_output": "expected output excerpt",
                            "actual_output": "actual student output excerpt",
                            "why_it_failed": "short explanation",
                        }
                    ],
                }
            ],
            "inline_comments": [
                {
                    "line": "1-based line number or null",
                    "comment": "brief code comment",
                }
            ],
            "fix_to_full_score": "minimal question-specific fix guidance; no unrelated cleanup",
            "risk_note": "uncertainty or empty string",
        },
    }
    prompt = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if case.student_id and case.student_id in prompt:
        raise ValueError("Review prompt leaked the real student ID")
    return prompt


def review_cases_with_llm(
    cases: list[ReviewCase],
    provider: LLMProvider,
    max_workers: int = 2,
    progress_callback=None,
) -> list[ReviewResult]:
    pending_cases = [case for case in cases if not case.reviewed]
    results: list[ReviewResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_review_one_case, case, provider): case for case in pending_cases}
        total = len(futures)
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if progress_callback:
                progress_callback(result, len(results), total)
    return sorted(results, key=lambda item: (item.question, item.student_id))


def save_review_result(case: ReviewCase, response: dict[str, Any]) -> ReviewResult:
    os.makedirs(os.path.dirname(case.review_path), exist_ok=True)
    payload = {
        "student_id": case.student_id,
        "anonymized_label": case.anonymized_label,
        "question": case.question,
        "question_score": case.question_score,
        "final_grade": case.final_grade,
        "response": response,
    }
    with open(case.review_path, "w", encoding="utf-8") as review_file:
        json.dump(payload, review_file, indent=2, ensure_ascii=False, default=str)
    return ReviewResult(case.student_id, case.anonymized_label, case.question, case.review_path, response)


def _review_one_case(case: ReviewCase, provider: LLMProvider) -> ReviewResult:
    prompt = build_score_review_prompt(case)
    try:
        response = complete_json_with_schema(provider, prompt, response_schema=SCORE_REVIEW_RESPONSE_SCHEMA)
    except Exception as exc:
        response = {
            "summary": f"Review failed: {exc}",
            "deduction_is_plausible": False,
            "deduction_caused_by": "unclear",
            "root_causes": [],
            "inline_comments": [],
            "fix_to_full_score": "",
            "risk_note": str(exc),
        }
    return save_review_result(case, _normalize_review_response(response))


def _build_review_case(
    question: str,
    excel_fields: dict[str, Any],
    final_fields: dict[str, Any],
    anonymized_label: str,
    max_failed_cases: int,
    grading_policy: dict[str, Any],
) -> ReviewCase:
    student_id = str(excel_fields.get("ID_number", "")).strip()
    grade_text = _read_optional_text(os.path.join(question, "grade", f"{student_id}.txt"))
    student_output_text = _read_optional_text(os.path.join(question, "output", f"{student_id}.txt"))
    expected_output_text = _read_optional_text(os.path.join(question, "original_sol_output.txt"))
    repair_metadata = _load_repair_metadata(question, student_id)
    code_path, code_text, code_source = _load_preferred_code(question, student_id, repair_metadata)
    review_path = os.path.join(question, "review", f"{student_id}.json")
    saved_review = _read_json_if_exists(review_path)
    failed_cases = tuple(_parse_failed_cases(grade_text, max_failed_cases))
    return ReviewCase(
        student_id=student_id,
        anonymized_label=anonymized_label,
        question=question,
        question_score=_safe_float(excel_fields.get("Grade", 0)),
        final_grade=_safe_float(final_fields.get("Final_Grade", 0)),
        notes=str(final_fields.get("Comments", "") or ""),
        grade_text=grade_text,
        student_output_text=student_output_text,
        expected_output_text=expected_output_text,
        code_path=code_path,
        code_text=code_text,
        code_source=code_source,
        failed_cases=failed_cases,
        excel_fields=excel_fields,
        final_fields=final_fields,
        repair_metadata=repair_metadata,
        grading_policy=grading_policy,
        review_path=review_path,
        saved_review=saved_review,
    )


def default_grading_policy() -> dict[str, Any]:
    return {
        "test_case_scoring": {
            "mode": configuration.test_scoring_mode,
            "percentage_formula": "ceil(correct_tests / total_tests * 100) when mode is percentage",
            "per_error_deduction_formula": (
                f"max(0, 100 - {configuration.test_error_deduction:g} * failed_tests) "
                "when mode is per_error_deduction"
            ),
            "deduction_per_failed_input": configuration.test_error_deduction,
        },
        "submission_error_penalty": {
            "points_per_error": configuration.penalty,
            "mode": "cumulative_per_error" if configuration.per_error_penalty else "once_per_student",
            "applies_to": (
                "preprocessing/submission problems such as unsupported or failed RAR extraction, "
                "missing C files, invalid naming, files nested too deeply, or question files not found"
            ),
        },
        "compile_repair": {
            "enabled": configuration.llm_compile_repair_enabled,
            "penalty_after_successful_repair": configuration.llm_compile_repair_penalty,
            "max_attempts": configuration.llm_compile_repair_max_attempts,
        },
    }


def _load_preferred_code(question: str, student_id: str, repair_metadata: dict[str, Any]) -> tuple[str, str, str]:
    fixed_path = str(repair_metadata.get("fixed_code_path", "") or "")
    if fixed_path and os.path.exists(fixed_path):
        return fixed_path, _read_optional_text(fixed_path), "repaired"

    attempt_paths = sorted(glob.glob(os.path.join(question, "llm_fixed", student_id, "attempt_*.c")))
    if repair_metadata.get("status") == "fixed" and attempt_paths:
        fixed_path = attempt_paths[-1]
        return fixed_path, _read_optional_text(fixed_path), "repaired"

    original_path = os.path.join(question, "C", f"{student_id}.c")
    return original_path, _read_optional_text(original_path), "original"


def _load_repair_metadata(question: str, student_id: str) -> dict[str, Any]:
    report_path = os.path.join(question, "llm_fixed", student_id, "repair_report.json")
    report = _read_json_if_exists(report_path) or {}
    if report:
        return report
    return {}


def _parse_failed_cases(grade_text: str, max_failed_cases: int) -> list[ReviewFailure]:
    cases: list[ReviewFailure] = []
    blocks = re.split(r"\n(?=Input:\s*)", grade_text)
    for block in blocks:
        input_match = re.search(r"^Input:\s*(.*)$", block, re.MULTILINE)
        expected_match = re.search(r"^Expected:\s*(.*)$", block, re.MULTILINE)
        actual_match = re.search(r"^Actual:\s*(.*)$", block, re.MULTILINE)
        reason_match = re.search(r"^Semantic Reason:\s*(.*)$", block, re.MULTILINE)
        if not input_match:
            continue
        cases.append(
            ReviewFailure(
                input_value=input_match.group(1).strip(),
                expected_output=expected_match.group(1).strip() if expected_match else "",
                actual_output=actual_match.group(1).strip() if actual_match else "",
                reason=reason_match.group(1).strip() if reason_match else "",
            )
        )
        if len(cases) >= max_failed_cases:
            break
    return cases


def _normalize_review_response(response: dict[str, Any]) -> dict[str, Any]:
    cause = normalize_deduction_cause(response.get("deduction_caused_by"))
    plausible = bool(response.get("deduction_is_plausible", False))
    if cause == "checker_or_app":
        plausible = False
    return {
        "summary": str(response.get("summary", "")),
        "deduction_is_plausible": plausible,
        "deduction_caused_by": cause,
        "root_causes": _normalize_root_causes(response.get("root_causes", [])),
        "inline_comments": response.get("inline_comments", []) if isinstance(response.get("inline_comments", []), list) else [],
        "fix_to_full_score": str(response.get("fix_to_full_score", "")),
        "risk_note": str(response.get("risk_note", "")),
    }


def _normalize_root_causes(root_causes: Any) -> list[dict[str, Any]]:
    if not isinstance(root_causes, list):
        return []

    normalized = []
    for cause in root_causes:
        if not isinstance(cause, dict):
            continue
        examples = cause.get("examples", [])
        normalized.append(
            {
                "issue": str(cause.get("issue", "")),
                "failed_inputs": cause.get("failed_inputs", []) if isinstance(cause.get("failed_inputs", []), list) else [],
                "deduction_impact": str(cause.get("deduction_impact", "")),
                "examples": examples if isinstance(examples, list) else [],
            }
        )
    return normalized


def _public_excel_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key != "ID_number"}


def _anonymize_value(value: Any, student_id: str) -> Any:
    if isinstance(value, str):
        return value.replace(student_id, "<student_id>") if student_id else value
    if isinstance(value, dict):
        return {key: _anonymize_value(item, student_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_anonymize_value(item, student_id) for item in value]
    if isinstance(value, tuple):
        return tuple(_anonymize_value(item, student_id) for item in value)
    return value


def _read_excel_if_exists(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_excel(path, dtype={"ID_number": str}).fillna("")


def _rows_by_id(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "ID_number" not in df.columns:
        return {}
    return {str(row["ID_number"]): row.to_dict() for _, row in df.iterrows()}


def _read_optional_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="ignore") as text_file:
        return text_file.read()


def _read_json_if_exists(path: str) -> dict[str, Any] | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as json_file:
            loaded = json.load(json_file)
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sort_score(value: float) -> float:
    return value if value > 0 else -1
