import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from c_tester.checker_calibration import (
    PopulationRecord,
    SemanticAuditEvidence,
    append_checker_version,
    audited_case_signature,
    checker_config_hash,
    evaluate_strict_population_confidence,
    finite_population_zero_error_upper_bound,
    hypergeometric_zero_error_probability,
    required_zero_error_sample_size,
    seeded_signature_stratified_sample,
    validate_candidate_against_rows,
)
from c_tester.checker_assistant import (
    AssignmentContext,
    AuditCase,
    _audit_case_signature,
    _audit_one_case,
    select_audit_cases,
    select_strict_audit_cases,
)


class _UncertainProvider:
    def complete_json(self, prompt, images=None, response_schema=None):
        return {"verdict": "uncertain", "risk": "medium", "reason": "evidence is truncated"}


class _SequenceAuditProvider:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete_json(self, prompt, images=None, response_schema=None):
        return self.responses.pop(0)


def _audit_response(behavior, semantic, format_requirement="not_explicit", evidence="Values match"):
    verdict = "flagged" if behavior in {"false_reject", "false_accept"} else "looks_correct"
    return {
        "verdict": verdict,
        "semantic_assessment": semantic,
        "format_requirement": format_requirement,
        "checker_behavior": behavior,
        "risk": "high" if verdict == "flagged" else "low",
        "reason": f"Checker behavior is {behavior}.",
        "evidence": evidence,
    }


class CheckerCalibrationTests(unittest.TestCase):
    def test_exact_finite_population_sample_size_and_bound(self):
        self.assertAlmostEqual(hypergeometric_zero_error_probability(100, 5, 45), 0.046206343362087114)
        self.assertEqual(required_zero_error_sample_size(10), 10)
        self.assertEqual(required_zero_error_sample_size(100), 39)
        self.assertEqual(required_zero_error_sample_size(1000), 56)
        self.assertEqual(finite_population_zero_error_upper_bound(100, 38), 0.06)
        self.assertEqual(finite_population_zero_error_upper_bound(100, 39), 0.05)
        self.assertEqual(finite_population_zero_error_upper_bound(100, 100), 0.0)

    def test_signature_stratification_covers_strata_before_repeats(self):
        records = [
            PopulationRecord(f"a{index}", 100, "common")
            for index in range(8)
        ] + [
            PopulationRecord("b", 100, "rare-b"),
            PopulationRecord("c", 100, "rare-c"),
        ]
        sample = seeded_signature_stratified_sample(records, 3, seed=17)
        self.assertEqual({record.signature for record in sample}, {"common", "rare-b", "rare-c"})
        self.assertEqual(
            [record.student_id for record in sample],
            [record.student_id for record in seeded_signature_stratified_sample(records, 3, seed=17)],
        )

    def test_audit_signature_distinguishes_output_shapes_but_not_values(self):
        first = AuditCase("1", "Q1", 100, "", "Point (1, 2)\nArea: 3.0", {}, {})
        equivalent_shape = AuditCase("2", "Q1", 100, "", "Point (8, 9)\nArea: 10.5", {}, {})
        different_shape = AuditCase("3", "Q1", 100, "", "Coordinates 8 9\nTriangle size 10.5", {}, {})
        self.assertEqual(_audit_case_signature(first), _audit_case_signature(equivalent_shape))
        self.assertNotEqual(_audit_case_signature(first), _audit_case_signature(different_shape))

    def test_strict_gate_requires_all_deductions_and_dual_agreement(self):
        population = [
            PopulationRecord("deducted", 80, "failure"),
            PopulationRecord("risky", 0, "extraction", extraction_only=True),
            *[PopulationRecord(f"full-{index}", 100, f"sig-{index % 2}") for index in range(20)],
        ]
        checker_hash = "checker"
        selected = seeded_signature_stratified_sample(
            population,
            required_zero_error_sample_size(20),
            seed=9,
        )
        audits = [
            SemanticAuditEvidence("deducted", "passed", "correct", checker_hash, "d1"),
            SemanticAuditEvidence("risky", "passed", "correct", checker_hash, "r1", verification_passes=1),
            *[
                SemanticAuditEvidence(record.student_id, "passed", "correct", checker_hash, f"f-{index}")
                for index, record in enumerate(selected)
            ],
        ]
        blocked = evaluate_strict_population_confidence(
            population,
            audits,
            checker_hash=checker_hash,
            deterministic_negative_gate_passed=True,
            seed=9,
        )
        self.assertEqual(blocked.too_low.status, "blocked")
        self.assertIn("two agreeing audits", " ".join(blocked.too_low.blockers))

        audits[1] = SemanticAuditEvidence("risky", "passed", "correct", checker_hash, "r2", verification_passes=2)
        verified = evaluate_strict_population_confidence(
            population,
            audits,
            checker_hash=checker_hash,
            deterministic_negative_gate_passed=True,
            seed=9,
        )
        self.assertEqual(verified.status, "verified")
        self.assertEqual(verified.too_low.reviewed, 2)
        self.assertLessEqual(verified.too_high.upper_bound, 0.05)

    def test_uncertainty_stale_and_negative_gate_block(self):
        population = [PopulationRecord("deducted", 50, "failure")]
        audit = SemanticAuditEvidence("deducted", "uncertain", "unclear", "checker", "evidence")
        result = evaluate_strict_population_confidence(
            population,
            [audit],
            checker_hash="checker",
            deterministic_negative_gate_passed=False,
            seed=1,
            fresh=False,
        )
        self.assertEqual(result.status, "stale")
        self.assertTrue(result.blockers)
        self.assertIn("negative mutation", " ".join(result.too_high.blockers))

    def test_disagreement_blocks_both_confidence_gates(self):
        population = [
            PopulationRecord("deducted", 80, "failure"),
            PopulationRecord("full", 100, "success"),
        ]
        audits = [
            SemanticAuditEvidence(
                "deducted", "passed", "correct", "checker", "deduction",
                verification_passes=2, disagreement=True,
            ),
            SemanticAuditEvidence(
                "full", "passed", "correct", "checker", "full",
                disagreement=True,
            ),
        ]
        result = evaluate_strict_population_confidence(
            population,
            audits,
            checker_hash="checker",
            deterministic_negative_gate_passed=True,
            seed=1,
            sampled_full_score_ids={"full"},
        )
        self.assertEqual(result.too_low.status, "blocked")
        self.assertEqual(result.too_high.status, "blocked")
        self.assertIn("disagree", " ".join(result.blockers))

    def test_defect_refinement_regrade_invalidation_fresh_pass_and_holdout_exhaustion(self):
        population = [
            PopulationRecord("deducted", 50, "failure"),
            *[PopulationRecord(f"full-{index}", 100, f"sig-{index % 3}") for index in range(20)],
        ]
        old_hash = "old"
        old_sample = seeded_signature_stratified_sample(population, required_zero_error_sample_size(20), 4)
        defect_audits = [
            SemanticAuditEvidence("deducted", "flagged", "false_reject", old_hash, "defect", verification_passes=2),
            *[
                SemanticAuditEvidence(item.student_id, "passed", "correct", old_hash, f"old-{index}")
                for index, item in enumerate(old_sample)
            ],
        ]
        defect = evaluate_strict_population_confidence(
            population, defect_audits, checker_hash=old_hash,
            deterministic_negative_gate_passed=True, seed=4,
        )
        self.assertEqual(defect.status, "blocked")

        new_hash = "refined"
        invalidated = evaluate_strict_population_confidence(
            population, defect_audits, checker_hash=new_hash,
            deterministic_negative_gate_passed=True, seed=5, fresh=False,
        )
        self.assertEqual(invalidated.status, "stale")

        new_sample = seeded_signature_stratified_sample(population, required_zero_error_sample_size(20), 5)
        fresh_audits = [
            SemanticAuditEvidence("deducted", "passed", "correct", new_hash, "fixed"),
            *[
                SemanticAuditEvidence(item.student_id, "passed", "correct", new_hash, f"new-{index}")
                for index, item in enumerate(new_sample)
            ],
        ]
        fresh = evaluate_strict_population_confidence(
            population, fresh_audits, checker_hash=new_hash,
            deterministic_negative_gate_passed=True, seed=5,
        )
        self.assertEqual(fresh.status, "verified")

        exhausted_ids = {item.student_id for item in new_sample[:-1]}
        exhausted = evaluate_strict_population_confidence(
            population, fresh_audits, checker_hash=new_hash,
            deterministic_negative_gate_passed=True, seed=6,
            sampled_full_score_ids=exhausted_ids,
        )
        self.assertEqual(exhausted.too_high.status, "blocked")
        self.assertIn("coverage is incomplete", " ".join(exhausted.too_high.blockers))

    def test_versions_keep_parent_and_candidate_hashes(self):
        active = {"checker": "exact", "config": {}, "metadata": {}}
        candidate = {"checker": "normalized_text", "config": {"ignore_case": True}}
        versioned = append_checker_version(active, candidate, 1, "promoted", "passed gates")
        version = versioned["metadata"]["versions"][-1]
        self.assertEqual(version["parent_hash"], checker_config_hash(active))
        self.assertEqual(versioned["metadata"]["active_version"], checker_config_hash(candidate))

    def test_checker_hash_changes_when_draft_json_changes(self):
        first = {"checker": "normalized_text", "config": {"ignore_case": True}}
        second = {"checker": "normalized_text", "config": {"ignore_case": False}}
        self.assertNotEqual(checker_config_hash(first), checker_config_hash(second))

    def test_first_unchanged_version_has_no_self_parent(self):
        config = {"checker": "exact", "config": {}}
        versioned = append_checker_version(config, config, 0, "promoted", "initial save")
        version = versioned["metadata"]["versions"][-1]
        self.assertNotEqual(version["hash"], version["parent_hash"])

    def test_cumulative_rows_reject_regression(self):
        rows = [
            {
                "variant": "accepted",
                "input": "",
                "expected_output": "Answer: 5",
                "actual_output": "Answer: 5",
                "expected_pass": True,
            },
            {
                "variant": "rejected",
                "input": "",
                "expected_output": "Answer: 5",
                "actual_output": "Wrong label: 5",
                "expected_pass": False,
            },
        ]
        ok, failures = validate_candidate_against_rows({"checker": "exact", "config": {}}, rows)
        self.assertTrue(ok, failures)
        regressed, _ = validate_candidate_against_rows({"checker": "last_integer", "config": {}}, rows)
        self.assertFalse(regressed)

    def test_signature_tracks_each_input_not_only_total_score(self):
        config = {"checker": "last_integer", "config": {}}
        with tempfile.TemporaryDirectory() as temp_dir:
            question = os.path.join(temp_dir, "Q1")
            os.makedirs(os.path.join(question, "output"))
            with open(os.path.join(question, "output", "123.txt"), "w", encoding="utf-8") as output_file:
                output_file.write("Input: 1\nOutput: result 2\n\nInput: 2\nOutput: result 4\n")
            signature = audited_case_signature(
                question,
                "123",
                config,
                [("1", "result 2"), ("2", "result 5")],
            )
        self.assertEqual([item[1] for item in signature], [True, False])

    def test_signature_ignores_checker_specific_canonical_shapes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            question = os.path.join(temp_dir, "Q1")
            os.makedirs(os.path.join(question, "output"))
            with open(os.path.join(question, "output", "123.txt"), "w", encoding="utf-8") as output_file:
                output_file.write("Input: 1\nOutput: Hello, world!\n")
            exact = audited_case_signature(
                question,
                "123",
                {"checker": "exact", "config": {}},
                [("1", "Hello, world!")],
            )
            normalized = audited_case_signature(
                question,
                "123",
                {"checker": "normalized_text", "config": {}},
                [("1", "Hello, world!")],
            )
        self.assertEqual(exact, normalized)

    def test_seeded_stratified_samples_are_reproducible_and_excludable(self):
        question_rows = pd.DataFrame(
            [
                {"ID_number": str(index), "Grade": grade}
                for index, grade in enumerate([100, 100, 90, 75, 40, 0, 0], start=1)
            ]
        )
        with patch(
            "c_tester.checker_assistant._read_excel_if_exists",
            side_effect=lambda path: pd.DataFrame() if path == "final_grades.xlsx" else question_rows,
        ):
            first = select_audit_cases(["Q1"], max_cases=4, seed=77)
            second = select_audit_cases(["Q1"], max_cases=4, seed=77)
            excluded = {case.student_id for case in first}
            third = select_audit_cases(["Q1"], max_cases=4, seed=78, exclude_student_ids=excluded)
        self.assertEqual([case.student_id for case in first], [case.student_id for case in second])
        self.assertTrue(excluded.isdisjoint({case.student_id for case in third}))

    def test_strict_selection_includes_every_deduction_and_exact_full_sample(self):
        question_rows = pd.DataFrame(
            [{"ID_number": f"d{index}", "Grade": 80} for index in range(4)]
            + [{"ID_number": f"f{index}", "Grade": 100, "Wrong_Inputs": index % 3} for index in range(20)]
        )
        with patch(
            "c_tester.checker_assistant._read_excel_if_exists",
            side_effect=lambda path: pd.DataFrame() if path == "final_grades.xlsx" else question_rows,
        ):
            selected = select_strict_audit_cases(["Q1"], seed=23)
        deducted = [case for case in selected if case.score < 100]
        full = [case for case in selected if case.score == 100]
        self.assertEqual(len(deducted), 4)
        self.assertEqual({case.student_id for case in deducted}, {f"d{index}" for index in range(4)})
        self.assertEqual(len(full), required_zero_error_sample_size(20))

    def test_uncertain_audit_is_not_treated_as_checker_defect(self):
        case = AuditCase("123", "Q1", 50, "Grade: 50", "truncated", {}, {})
        result = _audit_one_case(case, {"checker": "exact", "config": {}}, _UncertainProvider(), AssignmentContext())
        self.assertEqual(result.status, "uncertain")

    def test_format_only_zero_requires_two_agreeing_false_reject_audits(self):
        case = AuditCase(
            "123",
            "Q1",
            0,
            "Semantic Reason: field value [missing_anchor]: anchor 'Value' was not found",
            "Result is 4",
            {},
            {},
            "Value: 4",
        )
        provider = _SequenceAuditProvider(
            [
                _audit_response("false_reject", "equivalent"),
                _audit_response("false_reject", "equivalent"),
            ]
        )
        result = _audit_one_case(case, {"checker": "exact", "config": {}}, provider, AssignmentContext())
        self.assertEqual(result.status, "flagged")
        self.assertEqual(result.checker_behavior, "false_reject")
        self.assertEqual(result.verification_passes, 2)

    def test_high_risk_audit_disagreement_is_uncertain(self):
        case = AuditCase(
            "123",
            "Q1",
            0,
            "Semantic Reason: field value [missing_label]: missing label",
            "Result is 4",
            {},
            {},
            "Value: 4",
        )
        provider = _SequenceAuditProvider(
            [
                _audit_response("false_reject", "equivalent"),
                _audit_response("correct", "genuine_error"),
            ]
        )
        result = _audit_one_case(case, {"checker": "exact", "config": {}}, provider, AssignmentContext())
        self.assertEqual(result.status, "uncertain")

    def test_false_accept_is_flagged(self):
        case = AuditCase("123", "Q1", 100, "Grade: 100", "Value: 5", {}, {}, "Value: 4")
        provider = _SequenceAuditProvider(
            [
                _audit_response("false_accept", "genuine_error"),
                _audit_response("false_accept", "genuine_error"),
            ]
        )
        result = _audit_one_case(case, {"checker": "last_integer", "config": {}}, provider, AssignmentContext())
        self.assertEqual(result.status, "flagged")
        self.assertEqual(result.checker_behavior, "false_accept")


if __name__ == "__main__":
    unittest.main()
