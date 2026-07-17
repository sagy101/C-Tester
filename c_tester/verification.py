"""Versioned fingerprints for checker audits and post-scoring reviews."""

from __future__ import annotations

import hashlib
import glob
import json
import os
from typing import Any


AUDIT_RUBRIC_VERSION = 2
REVIEW_SCHEMA_VERSION = 2
STRICT_CONFIDENCE_POLICY_VERSION = 1


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


def grade_population_evidence_fingerprint(question: str) -> str:
    """Fingerprint the complete current per-question grade population without exposing IDs."""
    paths = [
        os.path.join(question, f"{question}_grades_to_upload.xlsx"),
        os.path.join(question, "original_sol_output.txt"),
        *glob.glob(os.path.join(question, "grade", "*.txt")),
        *glob.glob(os.path.join(question, "output", "*.txt")),
    ]
    evidence = []
    for path in sorted(path for path in paths if os.path.isfile(path)):
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            continue
        # Only anonymized path shape and content hash enter persisted verification evidence.
        evidence.append((os.path.basename(os.path.dirname(path)), os.path.splitext(path)[1], digest.hexdigest()))
    return stable_fingerprint(evidence) if evidence else ""


def strict_confidence_metadata(
    result: Any,
    *,
    checker_hash: str,
    population_fingerprint: str,
    sampled_id_hashes: list[str],
) -> dict[str, Any]:
    """Serialize strict confidence evidence into explicit, versioned metadata."""
    too_low = getattr(result, "too_low", None)
    too_high = getattr(result, "too_high", None)
    return {
        "strict_policy_version": STRICT_CONFIDENCE_POLICY_VERSION,
        "strict_status": getattr(result, "status", "blocked"),
        "strict_checker_hash": checker_hash,
        "grade_population_fingerprint": population_fingerprint,
        "strict_sampled_id_hashes": sorted(str(item) for item in sampled_id_hashes),
        "strict_too_low": _gate_metadata(too_low),
        "strict_too_high": _gate_metadata(too_high),
        "strict_blockers": list(getattr(result, "blockers", ()) or ()),
    }


def _gate_metadata(gate: Any) -> dict[str, Any]:
    return {
        "status": getattr(gate, "status", "blocked"),
        "reviewed": int(getattr(gate, "reviewed", 0) or 0),
        "required": int(getattr(gate, "required", 0) or 0),
        "population": int(getattr(gate, "population", 0) or 0),
        "observed_errors": int(getattr(gate, "observed_errors", 0) or 0),
        "uncertain": int(getattr(gate, "uncertain", 0) or 0),
        "errors": int(getattr(gate, "errors", 0) or 0),
        "disagreements": int(getattr(gate, "disagreements", 0) or 0),
        "upper_bound": getattr(gate, "upper_bound", None),
        "confidence_level": getattr(gate, "confidence_level", None),
        "blockers": list(getattr(gate, "blockers", ()) or ()),
        "next_action": str(getattr(gate, "next_action", "") or ""),
    }


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
        and metadata.get("strict_policy_version") == STRICT_CONFIDENCE_POLICY_VERSION
        and metadata.get("strict_status") == "verified"
        and metadata.get("strict_checker_hash") == editable_checker_hash(config)
        and bool(metadata.get("grade_population_fingerprint"))
        and isinstance(metadata.get("strict_sampled_id_hashes"), list)
        and _strict_gate_is_complete(metadata.get("strict_too_low"), require_bound=False)
        and _strict_gate_is_complete(metadata.get("strict_too_high"), require_bound=True)
        and not metadata.get("strict_blockers")
    )
    if not metadata_current:
        return False
    if question:
        recorded_mtime = float(metadata.get("audit_evidence_mtime", 0) or 0)
        return (
            recorded_mtime + 0.001 >= latest_audit_evidence_mtime(question)
            and metadata.get("grade_population_fingerprint") == grade_population_evidence_fingerprint(question)
        )
    return True


def _strict_gate_is_complete(value: Any, *, require_bound: bool) -> bool:
    if not isinstance(value, dict) or value.get("status") != "verified":
        return False
    try:
        reviewed = int(value.get("reviewed", -1))
        required = int(value.get("required", -1))
        observed_errors = int(value.get("observed_errors", -1))
        uncertain = int(value.get("uncertain", 0))
        errors = int(value.get("errors", 0))
        disagreements = int(value.get("disagreements", 0))
    except (TypeError, ValueError):
        return False
    if (
        reviewed != required
        or required < 0
        or observed_errors != 0
        or uncertain != 0
        or errors != 0
        or disagreements != 0
        or value.get("blockers")
    ):
        return False
    if require_bound:
        try:
            bound = float(value.get("upper_bound"))
            confidence = float(value.get("confidence_level"))
        except (TypeError, ValueError):
            return False
        return confidence >= 0.95 and bound <= 0.05
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
