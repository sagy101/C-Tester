"""Headless strict population verification for Q1 (and friends).

Audits every deducted student plus the finite-population full-score sample,
updates checker_config.json confidence metadata, and writes a verification
report under tools/_verification/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from c_tester.checker_assistant import (  # noqa: E402
    AssignmentContext,
    GeminiProvider,
    audit_cases_with_llm,
    audit_population_records,
    audit_result_cache_entry,
    load_audit_population,
    parse_assignment_context,
    select_strict_audit_cases,
)
from c_tester.checker_calibration import (  # noqa: E402
    SemanticAuditEvidence,
    anonymized_student_hashes,
    evaluate_strict_population_confidence,
)
from c_tester.semantic_grading import (  # noqa: E402
    DEFAULT_CHECKER_CONFIG_PATH,
    load_checker_config,
    save_checker_config,
)
from c_tester.verification import (  # noqa: E402
    editable_checker_hash,
    grade_population_evidence_fingerprint,
    stable_fingerprint,
    strict_confidence_metadata,
)


def _default_assignment_context() -> AssignmentContext:
    candidates = [
        ROOT / "materials" / "assignment.pdf",
        ROOT / "materials" / "hw4.pdf",
        ROOT / "materials" / "HW4.pdf",
        ROOT / "Q1" / "assignment.pdf",
    ]
    for path in candidates:
        if path.exists():
            return parse_assignment_context(str(path))
    # Fall back to reference solution + starter as assignment text.
    chunks = []
    for rel in ("Q1/original_sol.c", "materials/starter_hw4.c", "materials/moodle_samples_app_input_format.txt"):
        path = ROOT / rel
        if path.exists():
            chunks.append(f"===== {rel} =====\n{path.read_text(encoding='utf-8', errors='replace')}")
    return AssignmentContext(text="\n\n".join(chunks))


def _progress(result, done, total):
    print(
        f"[{done}/{total}] {result.student_id} {result.status}/{result.checker_behavior}: "
        f"{str(result.reason)[:120]}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="Q1")
    parser.add_argument("--model", default=os.getenv("C_TESTER_GEMINI_MODEL", "gemini-flash-latest"))
    parser.add_argument(
        "--cheap-model",
        default=os.getenv("C_TESTER_CHEAP_GEMINI_MODEL", "gemini-flash-lite-latest"),
    )
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    question = args.question.upper()
    os.environ["C_TESTER_CHEAP_GEMINI_MODEL"] = args.cheap_model

    checker_config = load_checker_config(DEFAULT_CHECKER_CONFIG_PATH)
    question_cfg = checker_config.get("questions", {}).get(question)
    if not isinstance(question_cfg, dict):
        print(f"No checker config for {question}", file=sys.stderr)
        return 2

    seed = args.seed if args.seed is not None else sum(ord(c) for c in question) * 1000 + 1
    cases = select_strict_audit_cases([question], seed=seed)
    population = load_audit_population([question])
    print(
        f"Population={len(population)} selected_for_audit={len(cases)} "
        f"(deductions={sum(1 for c in population if c.score < 99.999)}, "
        f"full={sum(1 for c in population if c.score >= 99.999)})",
        flush=True,
    )
    if not cases:
        print("No audit cases selected — ensure grades Excel files exist.", file=sys.stderr)
        return 3

    assignment_context = _default_assignment_context()
    cheap = GeminiProvider(model=args.cheap_model, thinking_level="MEDIUM")
    expensive = GeminiProvider(model=args.model, thinking_level="MEDIUM")
    checker_hash = editable_checker_hash(question_cfg)
    case_cache = question_cfg.get("metadata", {}).get("audit_case_cache", {})
    if not isinstance(case_cache, dict):
        case_cache = {}

    results = audit_cases_with_llm(
        cases,
        checker_config.get("questions", {}),
        cheap,
        assignment_context,
        max_workers=max(1, args.workers),
        progress_callback=_progress,
        expensive_provider=expensive,
        case_cache=case_cache,
        checker_hash=checker_hash,
    )

    for result in results:
        case = next((item for item in cases if item.student_id == result.student_id), None)
        if case is None:
            continue
        if result.status == "passed" and result.checker_behavior == "correct":
            case_cache[str(result.student_id)] = audit_result_cache_entry(case, result, checker_hash)

    status_counts = Counter(result.status for result in results)
    behavior_counts = Counter(result.checker_behavior for result in results)
    false_rejects = [r for r in results if r.checker_behavior == "false_reject" or r.status == "flagged"]
    errors = [r for r in results if r.status == "error"]

    evidence = [
        SemanticAuditEvidence(
            student_id=result.student_id,
            status=result.status,
            checker_behavior=result.checker_behavior,
            checker_hash=checker_hash,
            evidence_fingerprint=stable_fingerprint(
                result.status,
                result.checker_behavior,
                result.reason,
                result.evidence,
            ),
            verification_passes=result.verification_passes,
            disagreement=(
                result.status == "uncertain" and "disagreed" in str(result.reason).lower()
            ),
        )
        for result in results
    ]
    strict = evaluate_strict_population_confidence(
        audit_population_records(population),
        evidence,
        checker_hash=checker_hash,
        deterministic_negative_gate_passed=True,
        seed=seed,
        fresh=True,
        sampled_full_score_ids={
            case.student_id for case in cases if float(case.score) >= 99.999
        },
    )

    metadata = question_cfg.setdefault("metadata", {})
    metadata.update(
        strict_confidence_metadata(
            strict,
            checker_hash=checker_hash,
            population_fingerprint=grade_population_evidence_fingerprint(question),
            sampled_id_hashes=anonymized_student_hashes(set(strict.sampled_ids)),
        )
    )
    metadata["audit_case_cache"] = case_cache
    metadata["audit_status"] = (
        "flagged" if false_rejects else ("error" if errors and len(errors) == len(results) else "passed")
    )
    metadata["audit_reviewed"] = len(results)
    metadata["audit_errors"] = len(errors)
    metadata["audit_checker_hash"] = checker_hash
    metadata["verification_run_at"] = datetime.now(timezone.utc).isoformat()
    save_checker_config(checker_config, DEFAULT_CHECKER_CONFIG_PATH)

    out_dir = ROOT / "tools" / "_verification"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "question": question,
        "model": args.model,
        "cheap_model": args.cheap_model,
        "status_counts": dict(status_counts),
        "behavior_counts": dict(behavior_counts),
        "strict": strict.to_dict(),
        "false_rejects": [
            {
                "student_id": r.student_id,
                "status": r.status,
                "checker_behavior": r.checker_behavior,
                "reason": r.reason,
                "evidence": r.evidence,
            }
            for r in false_rejects
        ],
        "errors": [
            {"student_id": r.student_id, "reason": r.reason}
            for r in errors
        ],
        "results": [
            {
                "student_id": r.student_id,
                "score_case": next((c.score for c in cases if c.student_id == r.student_id), None),
                "status": r.status,
                "checker_behavior": r.checker_behavior,
                "risk": r.risk,
                "verification_passes": r.verification_passes,
                "reason": r.reason,
                "evidence": r.evidence,
            }
            for r in results
        ],
    }
    report_path = out_dir / f"verify_{question}_{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status_counts": dict(status_counts), "behavior_counts": dict(behavior_counts), "strict_status": strict.status, "report": str(report_path)}, indent=2))
    return 0 if strict.status == "verified" and not false_rejects else 1


if __name__ == "__main__":
    raise SystemExit(main())
