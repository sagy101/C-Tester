"""Assignment-neutral workflow status for the main grading UX."""

from __future__ import annotations

import glob
import json
import os
from typing import Any

import pandas as pd

from .verification import (
    REVIEW_SCHEMA_VERSION,
    audit_metadata_is_current,
    latest_review_evidence_mtime,
)


WORKFLOW_STEPS = ("setup", "checker", "grade", "review")
DEDUCTION_CAUSES = ("student_code", "checker_or_app", "unclear")
CAUSE_LABELS = {
    "student_code": "Student",
    "checker_or_app": "Checker",
    "unclear": "Unclear",
}


def normalize_deduction_cause(value: Any) -> str:
    cause = str(value or "").strip().lower()
    if cause in DEDUCTION_CAUSES:
        return cause
    return "unclear"


def review_cause_label(value: Any) -> str:
    return CAUSE_LABELS[normalize_deduction_cause(value)]


def review_response_cause(response: dict[str, Any] | None) -> str:
    if not isinstance(response, dict):
        return "unclear"
    if "deduction_caused_by" in response:
        return normalize_deduction_cause(response.get("deduction_caused_by"))
    # Legacy reviews did not distinguish parser defects from student mistakes.
    # They must be re-reviewed instead of silently becoming student-side proof.
    return "unclear"


def attention_threshold_from_grades(final_grades: dict[str, float]) -> float:
    grades = sorted(float(grade) for grade in final_grades.values())
    if not grades:
        return 50.0
    middle = len(grades) // 2
    median = grades[middle] if len(grades) % 2 else (grades[middle - 1] + grades[middle]) / 2
    return float(median - 40)


def is_attention_grade(final_grade: float, threshold: float) -> bool:
    return float(final_grade) < 50 or float(final_grade) <= threshold


def load_final_grades_by_id(path: str = "final_grades.xlsx") -> dict[str, float]:
    if not os.path.exists(path):
        return {}
    try:
        frame = pd.read_excel(path)
    except Exception:
        return {}
    if "ID_number" not in frame.columns or "Final_Grade" not in frame.columns:
        return {}
    grades = {}
    for _, row in frame.iterrows():
        student_id = str(row.get("ID_number", "")).strip()
        if not student_id:
            continue
        try:
            grades[student_id] = float(row.get("Final_Grade", 0) or 0)
        except (TypeError, ValueError):
            grades[student_id] = 0.0
    return grades


def collect_saved_reviews(questions: list[str]) -> list[dict[str, Any]]:
    reviews = []
    for question in questions:
        pattern = os.path.join(question, "review", "*.json")
        for path in sorted(glob.glob(pattern)):
            try:
                with open(path, encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
            student_id = str(payload.get("student_id", "")).strip() or os.path.splitext(os.path.basename(path))[0]
            current = (
                payload.get("review_schema_version") == REVIEW_SCHEMA_VERSION
                and bool(payload.get("evidence_fingerprint"))
                and float(payload.get("evidence_mtime", 0) or 0) + 0.001
                >= latest_review_evidence_mtime(str(payload.get("question") or question), student_id)
                and "deduction_caused_by" in response
            )
            reviews.append(
                {
                    "question": str(payload.get("question") or question),
                    "student_id": student_id,
                    "path": path,
                    "question_score": payload.get("question_score"),
                    "final_grade": payload.get("final_grade"),
                    "response": response,
                    "cause": review_response_cause(response) if current else "unclear",
                    "current": current,
                    "summary": str(response.get("summary", "")),
                    "risk_note": str(response.get("risk_note", "")),
                }
            )
    return reviews


def checker_defect_findings(reviews: list[dict[str, Any]], question: str | None = None) -> list[dict[str, Any]]:
    findings = []
    for review in reviews:
        if not review.get("current", False):
            continue
        if review.get("cause") != "checker_or_app":
            continue
        if question and review.get("question") != question:
            continue
        findings.append(
            {
                "question": review["question"],
                "student_id": review["student_id"],
                "summary": review.get("summary", ""),
                "risk_note": review.get("risk_note", ""),
                "root_causes": review.get("response", {}).get("root_causes", []),
                "semantic_assessment": review.get("response", {}).get("semantic_assessment", "unclear"),
                "format_requirement": review.get("response", {}).get("format_requirement", "unclear"),
                "format_requirement_evidence": review.get("response", {}).get("format_requirement_evidence", ""),
                "cause": "checker_or_app",
            }
        )
    return findings


def compute_workflow_status(
    questions: list[str],
    *,
    setup_readiness: dict[str, Any],
    checker_config: dict[str, Any] | None = None,
    final_grades_path: str = "final_grades.xlsx",
    checker_config_path: str = "checker_config.json",
) -> dict[str, Any]:
    questions = list(questions or [])
    checker_config = checker_config if isinstance(checker_config, dict) else {}
    question_configs = checker_config.get("questions", {}) if isinstance(checker_config.get("questions", {}), dict) else {}
    final_grades = load_final_grades_by_id(final_grades_path)
    grades_exist = bool(final_grades) or os.path.exists(final_grades_path)
    threshold = attention_threshold_from_grades(final_grades)
    attention_ids = {
        student_id
        for student_id, grade in final_grades.items()
        if is_attention_grade(grade, threshold)
    }
    reviews = collect_saved_reviews(questions)
    attention_reviews = [
        review
        for review in reviews
        if review.get("current")
        and (review["student_id"] in attention_ids or is_attention_grade(float(review.get("final_grade") or 0), threshold))
    ]
    defect_findings = checker_defect_findings(reviews)
    defect_questions = sorted({finding["question"] for finding in defect_findings})

    setup_done = bool(setup_readiness.get("scoring"))
    setup_step = {
        "id": "setup",
        "number": 1,
        "title": "Setup",
        "status": "done" if setup_done else "ready",
        "detail": (
            "Assignment, weights, and tools are ready."
            if setup_done
            else "Open Setup Assistant and finish the readiness checks."
        ),
        "action": "open_setup",
    }

    calibrated = []
    configured = []
    missing = []
    checker_confidence = {}
    for question in questions:
        question_config = question_configs.get(question) or question_configs.get(str(question).upper())
        if not isinstance(question_config, dict):
            missing.append(question)
            continue
        configured.append(question)
        metadata = question_config.get("metadata", {}) if isinstance(question_config.get("metadata"), dict) else {}
        positive_ok = metadata.get("positive_gate_status") == "passed"
        negative_ok = metadata.get("negative_gate_status") == "passed"
        current_audit = audit_metadata_is_current(question_config, question)
        checker_confidence[question] = strict_confidence_status(metadata)
        if checker_confidence[question]["status"] == "verified" and not current_audit:
            checker_confidence[question]["status"] = "stale"
            checker_confidence[question]["too_low"]["status"] = "stale"
            checker_confidence[question]["too_high"]["status"] = "stale"
            checker_confidence[question]["blockers"] = ["Checker or grade-population evidence changed."]
            checker_confidence[question]["next_action"] = "Regrade and rerun strict verification."
        if metadata.get("calibration_status") == "passed" and current_audit and positive_ok and negative_ok:
            calibrated.append(question)

    if defect_questions:
        checker_status = "attention"
        checker_detail = (
            f"Reviews blame the checker on {', '.join(defect_questions)}. "
            "Recalibrate those questions before trusting grades."
        )
    elif not questions:
        checker_status = "pending"
        checker_detail = "Add question folders in Configuration first."
    elif missing:
        checker_status = "ready"
        checker_detail = f"Configure and one-click calibrate: {', '.join(missing)}."
    elif len(calibrated) == len(questions):
        checker_status = "done"
        checker_detail = "Checkers passed current false-rejection and false-acceptance verification."
    elif configured:
        checker_status = "ready"
        checker_detail = (
            f"Saved checkers still need calibration: "
            f"{', '.join(q for q in questions if q not in calibrated)}."
        )
    else:
        checker_status = "ready"
        checker_detail = "Open Checker Manager and run One-click Calibrate."
    checker_step = {
        "id": "checker",
        "number": 2,
        "title": "Checker",
        "status": checker_status,
        "detail": checker_detail,
        "action": "open_checker",
    }

    checker_mtime = os.path.getmtime(checker_config_path) if os.path.exists(checker_config_path) else 0
    grades_mtime = os.path.getmtime(final_grades_path) if os.path.exists(final_grades_path) else 0
    if not grades_exist:
        grade_status = "pending" if checker_status in {"pending", "ready", "attention"} and not setup_done else "ready"
        if checker_status == "pending" or not setup_done:
            grade_status = "pending"
        grade_detail = "Run grading after setup and checker calibration."
        if not setup_done:
            grade_detail = "Finish setup before grading."
        elif checker_status in {"ready", "attention"} and missing:
            grade_detail = "Calibrate checkers first so grades stay fair."
    elif grades_mtime + 1 < checker_mtime or checker_status == "attention":
        grade_status = "stale"
        grade_detail = (
            "Grades are older than the latest checker changes, or reviews found checker defects. Regrade all students."
        )
    else:
        grade_status = "done"
        grade_detail = f"Graded {len(final_grades) or 'all'} students. Open the Excel anytime."
    grade_step = {
        "id": "grade",
        "number": 3,
        "title": "Grade",
        "status": grade_status,
        "detail": grade_detail,
        "action": "run_grading",
    }

    attention_total = len(attention_ids) if attention_ids else 0
    # Count reviewed attention students across any question row for that ID.
    reviewed_attention_ids = {review["student_id"] for review in attention_reviews}
    if not grades_exist:
        review_status = "pending"
        review_detail = "Grade students first, then review attention-needed rows."
    elif attention_total == 0:
        review_status = "done"
        review_detail = "No attention-needed students after grading."
    elif defect_findings:
        review_status = "attention"
        review_detail = (
            f"{len(defect_findings)} review(s) say the deduction came from the checker/app, "
            f"not the student. Recalibrate, regrade, then re-review."
        )
    elif len(reviewed_attention_ids) >= attention_total:
        review_status = "done"
        review_detail = f"All {attention_total} attention-needed student(s) have reviews."
    else:
        remaining = attention_total - len(reviewed_attention_ids & attention_ids)
        review_status = "ready"
        review_detail = (
            f"{remaining} of {attention_total} attention-needed student(s) still need review. "
            "Use Review All Attention Needed."
        )
    review_step = {
        "id": "review",
        "number": 4,
        "title": "Review",
        "status": review_status,
        "detail": review_detail,
        "action": "open_review",
    }

    steps = {
        "setup": setup_step,
        "checker": checker_step,
        "grade": grade_step,
        "review": review_step,
    }
    next_step = _next_step(steps)
    return {
        "steps": steps,
        "next_step": next_step,
        "next_hint": _next_hint(steps, next_step),
        "checker_defect_questions": defect_questions,
        "checker_defect_findings": defect_findings,
        "attention_total": attention_total,
        "attention_reviewed": len(reviewed_attention_ids & attention_ids) if attention_ids else len(reviewed_attention_ids),
        "attention_threshold": threshold,
        "checker_confidence": checker_confidence,
    }


def strict_confidence_status(metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata if isinstance(metadata, dict) else {}
    low = metadata.get("strict_too_low") if isinstance(metadata.get("strict_too_low"), dict) else {}
    high = metadata.get("strict_too_high") if isinstance(metadata.get("strict_too_high"), dict) else {}
    status = str(metadata.get("strict_status", "in_progress"))
    if status not in {"verified", "blocked", "stale"}:
        status = "in_progress"
    blockers = list(metadata.get("strict_blockers", []) or [])
    bound = high.get("upper_bound")
    return {
        "status": status,
        "too_low": {
            "status": str(low.get("status", "in_progress")),
            "reviewed": int(low.get("reviewed", 0) or 0),
            "required": int(low.get("required", 0) or 0),
            "line": (
                f"Too-low: deductions reviewed {int(low.get('reviewed', 0) or 0)}/"
                f"{int(low.get('required', 0) or 0)}."
            ),
        },
        "too_high": {
            "status": str(high.get("status", "in_progress")),
            "reviewed": int(high.get("reviewed", 0) or 0),
            "required": int(high.get("required", 0) or 0),
            "upper_bound": bound,
            "line": (
                f"Too-high: full-score sample {int(high.get('reviewed', 0) or 0)}/"
                f"{int(high.get('required', 0) or 0)}; 95% upper bound "
                f"{'not available' if bound is None else f'{100 * float(bound):.1f}%'}."
            ),
        },
        "blockers": blockers,
        "next_action": (
            str(low.get("next_action") or high.get("next_action") or "")
            if status != "verified"
            else ""
        ),
    }


def _next_step(steps: dict[str, dict[str, Any]]) -> str:
    priority = ("attention", "stale", "ready", "pending")
    for status in priority:
        for step_id in WORKFLOW_STEPS:
            if steps[step_id]["status"] == status:
                return step_id
    return "review"


def _next_hint(steps: dict[str, dict[str, Any]], next_step: str) -> str:
    step = steps.get(next_step) or steps["setup"]
    prefixes = {
        "setup": "Next: Setup — ",
        "checker": "Next: Checker — ",
        "grade": "Next: Grade — ",
        "review": "Next: Review — ",
    }
    return prefixes.get(next_step, "Next: ") + str(step.get("detail", ""))
