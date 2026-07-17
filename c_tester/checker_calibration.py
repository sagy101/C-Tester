"""Deterministic guards and version metadata for checker calibration."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
import random
from typing import Any

from .semantic_grading import compare_output_with_config


STRICT_CONFIDENCE_POLICY_VERSION = 1
STRICT_CONFIDENCE_LEVEL = 0.95
STRICT_FALSE_ACCEPT_TARGET = 0.05


@dataclass(frozen=True)
class PopulationRecord:
    student_id: str
    score: float
    signature: str
    high_risk: bool = False
    extraction_only: bool = False
    anomaly: bool = False

    @property
    def deducted(self) -> bool:
        return float(self.score) < 99.999


@dataclass(frozen=True)
class SemanticAuditEvidence:
    student_id: str
    status: str
    checker_behavior: str
    checker_hash: str
    evidence_fingerprint: str
    verification_passes: int = 1
    disagreement: bool = False


@dataclass(frozen=True)
class ConfidenceGate:
    name: str
    status: str
    reviewed: int
    required: int
    population: int
    observed_errors: int = 0
    uncertain: int = 0
    errors: int = 0
    disagreements: int = 0
    upper_bound: float | None = None
    confidence_level: float | None = None
    blockers: tuple[str, ...] = ()
    next_action: str = ""


@dataclass(frozen=True)
class StrictConfidenceResult:
    status: str
    too_low: ConfidenceGate
    too_high: ConfidenceGate
    fresh: bool
    blockers: tuple[str, ...] = ()
    sampled_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def hypergeometric_zero_error_probability(population: int, defects: int, sample: int) -> float:
    """P(observe zero defects) for sampling without replacement."""
    population = int(population)
    defects = int(defects)
    sample = int(sample)
    if not 0 <= defects <= population or not 0 <= sample <= population:
        raise ValueError("population, defects, and sample must describe a valid finite population")
    if sample > population - defects:
        return 0.0
    if sample == 0 or defects == 0:
        return 1.0
    probability = 1.0
    for offset in range(sample):
        probability *= (population - defects - offset) / (population - offset)
    return probability


def finite_population_zero_error_upper_bound(
    population: int,
    sample: int,
    confidence: float = STRICT_CONFIDENCE_LEVEL,
) -> float:
    """Exact one-sided upper confidence bound on finite-population prevalence."""
    population = int(population)
    sample = int(sample)
    if population < 0 or not 0 <= sample <= population:
        raise ValueError("sample must be between zero and population")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    if population == 0 or sample == population:
        return 0.0
    alpha = 1.0 - confidence
    upper_defects = 0
    for defects in range(1, population + 1):
        if hypergeometric_zero_error_probability(population, defects, sample) + 1e-15 >= alpha:
            upper_defects = defects
        else:
            break
    return upper_defects / population


def required_zero_error_sample_size(
    population: int,
    target: float = STRICT_FALSE_ACCEPT_TARGET,
    confidence: float = STRICT_CONFIDENCE_LEVEL,
) -> int:
    """Smallest exact without-replacement sample whose upper bound meets target."""
    population = int(population)
    if population < 0:
        raise ValueError("population cannot be negative")
    if not 0 <= target < 1:
        raise ValueError("target must be in [0, 1)")
    for sample in range(population + 1):
        if finite_population_zero_error_upper_bound(population, sample, confidence) <= target:
            return sample
    return population


def seeded_signature_stratified_sample(
    records: list[PopulationRecord],
    sample_size: int,
    seed: int,
) -> list[PopulationRecord]:
    """Deterministically spread a sample across observed full-score signatures."""
    full_score = [record for record in records if not record.deducted]
    sample_size = min(max(0, int(sample_size)), len(full_score))
    buckets: dict[str, list[PopulationRecord]] = {}
    for record in full_score:
        buckets.setdefault(str(record.signature or "unknown"), []).append(record)
    rng = random.Random(seed)
    for signature in sorted(buckets):
        rng.shuffle(buckets[signature])
    signatures = sorted(buckets)
    rng.shuffle(signatures)
    selected: list[PopulationRecord] = []
    while len(selected) < sample_size and signatures:
        remaining = []
        for signature in signatures:
            bucket = buckets[signature]
            if bucket and len(selected) < sample_size:
                selected.append(bucket.pop())
            if bucket:
                remaining.append(signature)
        signatures = remaining
    return selected


def evaluate_strict_population_confidence(
    population: list[PopulationRecord],
    audits: list[SemanticAuditEvidence],
    *,
    checker_hash: str,
    deterministic_negative_gate_passed: bool,
    seed: int,
    fresh: bool = True,
    sampled_full_score_ids: set[str] | None = None,
) -> StrictConfidenceResult:
    """Evaluate explicit too-low and too-high gates for the current grade population."""
    evidence_by_id: dict[str, list[SemanticAuditEvidence]] = {}
    for audit in audits:
        if audit.checker_hash == checker_hash and audit.evidence_fingerprint:
            evidence_by_id.setdefault(str(audit.student_id), []).append(audit)

    deductions = [record for record in population if record.deducted]
    low_blockers: list[str] = []
    low_reviewed = 0
    for record in deductions:
        evidence = evidence_by_id.get(str(record.student_id), [])
        required_passes = 2 if record.high_risk or record.extraction_only or record.anomaly else 1
        if not evidence:
            low_blockers.append("Deduction audit coverage is incomplete.")
            continue
        if any(item.status in {"uncertain", "error"} for item in evidence):
            low_blockers.append("Deduction audits contain uncertainty or transport errors.")
            continue
        if any(item.disagreement for item in evidence):
            low_blockers.append("Deduction audit passes disagree.")
            continue
        if any(item.checker_behavior == "false_reject" or item.status == "flagged" for item in evidence):
            low_blockers.append("A possible false rejection requires checker refinement.")
            continue
        agreeing_passes = sum(
            max(1, int(item.verification_passes))
            for item in evidence
            if item.status == "passed" and item.checker_behavior == "correct"
        )
        if agreeing_passes < required_passes:
            low_blockers.append("High-risk, extraction-only, and anomaly deductions need two agreeing audits.")
            continue
        low_reviewed += 1
    low_blockers = list(dict.fromkeys(low_blockers))
    too_low = ConfidenceGate(
        name="too_low",
        status="verified" if fresh and low_reviewed == len(deductions) and not low_blockers else ("stale" if not fresh else "blocked"),
        reviewed=low_reviewed,
        required=len(deductions),
        population=len(deductions),
        observed_errors=sum(
            1
            for record in deductions
            for item in evidence_by_id.get(str(record.student_id), [])
            if item.checker_behavior == "false_reject"
        ),
        uncertain=sum(
            1 for record in deductions for item in evidence_by_id.get(str(record.student_id), [])
            if item.status == "uncertain"
        ),
        errors=sum(
            1 for record in deductions for item in evidence_by_id.get(str(record.student_id), [])
            if item.status == "error"
        ),
        disagreements=sum(
            1 for record in deductions for item in evidence_by_id.get(str(record.student_id), [])
            if item.disagreement
        ),
        blockers=tuple(low_blockers or (() if fresh else ("Evidence is stale for the current checker or grades.",))),
        next_action=(
            "Audit every deducted submission and resolve flagged or uncertain results."
            if low_reviewed < len(deductions) or low_blockers
            else ("Regrade and rerun verification." if not fresh else "")
        ),
    )

    full_score = [record for record in population if not record.deducted]
    required_sample = required_zero_error_sample_size(len(full_score))
    if sampled_full_score_ids is None:
        selected = seeded_signature_stratified_sample(population, required_sample, seed)
    else:
        requested = {str(student_id) for student_id in sampled_full_score_ids}
        selected = [record for record in full_score if str(record.student_id) in requested]
    selected_ids = {str(record.student_id) for record in selected}
    high_evidence = {
        student_id: evidence_by_id.get(student_id, [])
        for student_id in selected_ids
    }
    reviewed_ids = {
        student_id
        for student_id, evidence in high_evidence.items()
        if evidence
        and all(item.status == "passed" and item.checker_behavior == "correct" for item in evidence)
        and not any(item.disagreement for item in evidence)
    }
    false_accepts = sum(
        1
        for evidence in high_evidence.values()
        if any(item.checker_behavior == "false_accept" or item.status == "flagged" for item in evidence)
    )
    high_blockers: list[str] = []
    if not deterministic_negative_gate_passed:
        high_blockers.append("Deterministic negative mutation gate has not passed.")
    if len(reviewed_ids) < required_sample:
        high_blockers.append("Full-score audit sample coverage is incomplete.")
    if any(
        item.status in {"uncertain", "error"}
        for evidence in high_evidence.values()
        for item in evidence
    ):
        high_blockers.append("Full-score audits contain uncertainty or transport errors.")
    if any(
        item.disagreement
        for evidence in high_evidence.values()
        for item in evidence
    ):
        high_blockers.append("Full-score audit passes disagree.")
    if false_accepts:
        high_blockers.append("A possible false acceptance requires checker refinement.")
    achieved_bound = finite_population_zero_error_upper_bound(
        len(full_score),
        len(reviewed_ids) if false_accepts == 0 else 0,
    )
    high_verified = (
        fresh
        and deterministic_negative_gate_passed
        and len(reviewed_ids) == required_sample
        and false_accepts == 0
        and achieved_bound <= STRICT_FALSE_ACCEPT_TARGET
        and not high_blockers
    )
    too_high = ConfidenceGate(
        name="too_high",
        status="verified" if high_verified else ("stale" if not fresh else "blocked"),
        reviewed=len(reviewed_ids),
        required=required_sample,
        population=len(full_score),
        observed_errors=false_accepts,
        uncertain=sum(
            1 for evidence in high_evidence.values() for item in evidence if item.status == "uncertain"
        ),
        errors=sum(
            1 for evidence in high_evidence.values() for item in evidence if item.status == "error"
        ),
        disagreements=sum(
            1 for evidence in high_evidence.values() for item in evidence if item.disagreement
        ),
        upper_bound=achieved_bound,
        confidence_level=STRICT_CONFIDENCE_LEVEL,
        blockers=tuple(high_blockers or (() if fresh else ("Evidence is stale for the current checker or grades.",))),
        next_action=(
            "Pass negative mutations, then audit the remaining seeded full-score sample."
            if not high_verified and fresh
            else ("Regrade and rerun verification." if not fresh else "")
        ),
    )
    blockers = tuple(dict.fromkeys((*too_low.blockers, *too_high.blockers)))
    verified = fresh and too_low.status == "verified" and too_high.status == "verified"
    return StrictConfidenceResult(
        status="verified" if verified else ("stale" if not fresh else "blocked"),
        too_low=too_low,
        too_high=too_high,
        fresh=fresh,
        blockers=blockers,
        sampled_ids=tuple(sorted(selected_ids)),
    )


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


