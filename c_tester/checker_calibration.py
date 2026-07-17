"""Deterministic guards and version metadata for checker calibration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os

from .semantic_grading import compare_output_with_config


def editable_checker_config(question_config: dict) -> dict:
    return {key: deepcopy(value) for key, value in (question_config or {}).items() if key != "metadata"}


def checker_config_hash(question_config: dict) -> str:
    payload = editable_checker_config(question_config)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def append_checker_version(
    question_config: dict,
    candidate: dict,
    round_number: int,
    status: str,
    reason: str,
) -> dict:
    updated = deepcopy(candidate)
    existing_metadata = deepcopy((question_config or {}).get("metadata", {}))
    versions = list(existing_metadata.get("versions", []))
    candidate_hash = checker_config_hash(candidate)
    parent_config = editable_checker_config(question_config)
    parent_hash = checker_config_hash(question_config) if question_config else ""
    if not versions and parent_config and parent_hash != candidate_hash:
        versions.append(
            {
                "hash": parent_hash,
                "parent_hash": "",
                "round": max(0, int(round_number) - 1),
                "status": "promoted",
                "reason": "Imported active checker before version tracking.",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "config": parent_config,
            }
        )
    if not versions or versions[-1].get("hash") != candidate_hash or versions[-1].get("status") != status:
        versions.append(
            {
                "hash": candidate_hash,
                "parent_hash": "" if parent_hash == candidate_hash else parent_hash,
                "round": int(round_number),
                "status": status,
                "reason": str(reason)[:500],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "config": editable_checker_config(candidate),
            }
        )
    existing_metadata["versions"] = versions[-12:]
    existing_metadata["active_version"] = candidate_hash if status == "promoted" else existing_metadata.get("active_version", "")
    updated["metadata"] = existing_metadata
    return updated


def validate_candidate_against_rows(candidate: dict, rows: list[dict]) -> tuple[bool, list[str]]:
    failures = []
    for row in rows:
        comparison = compare_output_with_config(
            candidate,
            row.get("input", ""),
            row.get("expected_output", ""),
            row.get("actual_output", ""),
        )
        expected_pass = bool(row.get("expected_pass", row.get("variant") != "wrong"))
        if comparison.passed != expected_pass:
            failures.append(f"{row.get('variant', 'case')}: {comparison.reason}")
    return not failures, failures


def audited_case_signature(
    question: str,
    student_id: str,
    checker_config: dict,
    expected_outputs: list[tuple[str, str]],
) -> tuple | None:
    path = os.path.join(question, "output", f"{student_id}.txt")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as output_file:
            output_text = output_file.read()
    except OSError:
        return None
    actual_by_input = _parse_output_cases(output_text)
    signature = []
    for input_value, expected_output in expected_outputs:
        actual_output = actual_by_input.get(_normalize_input(input_value))
        if actual_output is None:
            signature.append((_normalize_input(input_value), False, "missing output"))
            continue
        comparison = compare_output_with_config(checker_config, input_value, expected_output, actual_output)
        signature.append(
            (
                _normalize_input(input_value),
                comparison.passed,
            )
        )
    return tuple(signature)


def candidate_preserves_audited_cases(
    question: str,
    student_ids: set[str],
    active_config: dict,
    candidate: dict,
    expected_outputs: list[tuple[str, str]],
    allowed_changed_ids: set[str] | None = None,
) -> tuple[bool, list[str]]:
    changed = []
    allowed = {str(student_id) for student_id in (allowed_changed_ids or set())}
    for student_id in sorted(student_ids):
        active_signature = audited_case_signature(question, student_id, active_config, expected_outputs)
        candidate_signature = audited_case_signature(question, student_id, candidate, expected_outputs)
        if active_signature != candidate_signature and str(student_id) not in allowed:
            changed.append(student_id)
    return not changed, changed


def anonymized_student_hashes(student_ids: set[str]) -> list[str]:
    return sorted(hashlib.sha256(str(student_id).encode("utf-8")).hexdigest()[:12] for student_id in student_ids)


def _parse_output_cases(output_text: str) -> dict[str, str]:
    cases = {}
    normalized = str(output_text).replace("\r\n", "\n").replace("\r", "\n")
    for block in normalized.split("\nInput: "):
        block = block.removeprefix("Input: ")
        if "\nOutput: " not in block:
            continue
        input_value, output = block.split("\nOutput: ", 1)
        cases[_normalize_input(input_value)] = output.rstrip()
    return cases


def _normalize_input(input_value: str) -> str:
    return " ".join(str(input_value).split())


