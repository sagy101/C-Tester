"""Versioned fingerprints for checker audits and post-scoring reviews."""

from __future__ import annotations

import hashlib
import glob
import json
import os
from typing import Any


AUDIT_RUBRIC_VERSION = 2
REVIEW_SCHEMA_VERSION = 2


def stable_fingerprint(*values: Any) -> str:
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def editable_checker_hash(question_config: dict[str, Any] | None) -> str:
    payload = {
        key: value
        for key, value in (question_config or {}).items()
        if key != "metadata"
    }
    return stable_fingerprint(payload)[:16]


def audit_evidence_fingerprint(case: Any) -> str:
    return stable_fingerprint(
        getattr(case, "question", ""),
        getattr(case, "score", 0),
        getattr(case, "grade_text", ""),
        getattr(case, "output_text", ""),
        getattr(case, "reference_output_text", ""),
        getattr(case, "excel_fields", {}),
        getattr(case, "final_fields", {}),
    )


def review_evidence_fingerprint(case: Any) -> str:
    return stable_fingerprint(
        getattr(case, "question", ""),
        getattr(case, "question_score", 0),
        getattr(case, "final_grade", 0),
        getattr(case, "grade_text", ""),
        getattr(case, "student_output_text", ""),
        getattr(case, "expected_output_text", ""),
        getattr(case, "code_text", ""),
        getattr(case, "grading_policy", {}),
    )


def latest_audit_evidence_mtime(question: str) -> float:
    paths = [
        os.path.join(question, f"{question}_grades_to_upload.xlsx"),
        os.path.join(question, "original_sol_output.txt"),
        "final_grades.xlsx",
        *glob.glob(os.path.join(question, "grade", "*.txt")),
        *glob.glob(os.path.join(question, "output", "*.txt")),
    ]
    return max((os.path.getmtime(path) for path in paths if os.path.exists(path)), default=0.0)


def latest_review_evidence_mtime(question: str, student_id: str) -> float:
    paths = [
        os.path.join(question, f"{question}_grades_to_upload.xlsx"),
        os.path.join(question, "original_sol_output.txt"),
        os.path.join(question, "grade", f"{student_id}.txt"),
        os.path.join(question, "output", f"{student_id}.txt"),
        os.path.join(question, "C", f"{student_id}.c"),
        "final_grades.xlsx",
    ]
    return max((os.path.getmtime(path) for path in paths if os.path.exists(path)), default=0.0)


def audit_metadata_is_current(question_config: dict[str, Any] | None, question: str = "") -> bool:
    config = question_config if isinstance(question_config, dict) else {}
    metadata = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
    metadata_current = (
        metadata.get("audit_status") == "passed"
        and metadata.get("audit_rubric_version") == AUDIT_RUBRIC_VERSION
        and metadata.get("audit_checker_hash") == editable_checker_hash(config)
        and bool(metadata.get("audit_evidence_fingerprint"))
        and metadata.get("positive_gate_status") == "passed"
        and metadata.get("negative_gate_status") == "passed"
    )
    if not metadata_current:
        return False
    if question:
        recorded_mtime = float(metadata.get("audit_evidence_mtime", 0) or 0)
        return recorded_mtime + 0.001 >= latest_audit_evidence_mtime(question)
    return True


def saved_review_is_current(saved_review: Any, evidence_fingerprint: str) -> bool:
    if not isinstance(saved_review, dict):
        return False
    return (
        saved_review.get("review_schema_version") == REVIEW_SCHEMA_VERSION
        and saved_review.get("evidence_fingerprint") == evidence_fingerprint
        and isinstance(saved_review.get("response"), dict)
        and "deduction_caused_by" in saved_review["response"]
    )
