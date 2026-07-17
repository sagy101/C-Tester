import json
import os
import tempfile
import unittest
from unittest.mock import patch

from c_tester.workflow_status import (
    compute_workflow_status,
    normalize_deduction_cause,
    review_cause_label,
    review_response_cause,
)
from c_tester.verification import STRICT_CONFIDENCE_POLICY_VERSION, audit_metadata_is_current, editable_checker_hash


class WorkflowStatusTests(unittest.TestCase):
    def test_normalize_and_labels(self):
        self.assertEqual(normalize_deduction_cause("checker_or_app"), "checker_or_app")
        self.assertEqual(normalize_deduction_cause("weird"), "unclear")
        self.assertEqual(review_cause_label("student_code"), "Student")
        self.assertEqual(review_cause_label("checker_or_app"), "Checker")

    def test_legacy_review_without_cause_requires_rereview(self):
        self.assertEqual(review_response_cause({"deduction_is_plausible": True}), "unclear")
        self.assertEqual(review_response_cause({"deduction_is_plausible": False}), "unclear")

    def test_workflow_marks_review_attention_when_reviews_blame_checker(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                os.makedirs(os.path.join("Q1", "review"), exist_ok=True)
                with open(os.path.join("Q1", "review", "111.json"), "w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "review_schema_version": 2,
                            "evidence_fingerprint": "current-fixture",
                            "evidence_mtime": 9999999999,
                            "student_id": "111",
                            "question": "Q1",
                            "final_grade": 0,
                            "response": {
                                "summary": "Checker rejected equivalent phrasing.",
                                "deduction_is_plausible": False,
                                "deduction_caused_by": "checker_or_app",
                            },
                        },
                        handle,
                    )
                import pandas as pd

                pd.DataFrame([{"ID_number": "111", "Final_Grade": 0}, {"ID_number": "222", "Final_Grade": 100}]).to_excel(
                    "final_grades.xlsx",
                    index=False,
                )
                with open("checker_config.json", "w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "questions": {
                                "Q1": {
                                    "checker": "exact",
                                    "config": {},
                                    "metadata": {"calibration_status": "passed", "audit_status": "passed"},
                                }
                            }
                        },
                        handle,
                    )

                with open("checker_config.json", encoding="utf-8") as handle:
                    checker_config = json.load(handle)
                workflow = compute_workflow_status(
                    ["Q1"],
                    setup_readiness={"scoring": True},
                    checker_config=checker_config,
                )
                self.assertEqual(workflow["steps"]["checker"]["status"], "attention")
                self.assertEqual(workflow["steps"]["review"]["status"], "attention")
                self.assertEqual(workflow["next_step"], "checker")
                self.assertEqual(workflow["checker_defect_questions"], ["Q1"])
                self.assertEqual(len(workflow["checker_defect_findings"]), 1)
            finally:
                os.chdir(original_cwd)

    def test_grades_become_stale_after_newer_checker_config(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                import pandas as pd

                pd.DataFrame([{"ID_number": "1", "Final_Grade": 100}]).to_excel("final_grades.xlsx", index=False)
                with open("checker_config.json", "w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "questions": {
                                "Q1": {
                                    "checker": "exact",
                                    "config": {},
                                    "metadata": {"calibration_status": "passed", "audit_status": "passed"},
                                }
                            }
                        },
                        handle,
                    )
                # Make grades older than the checker config so regrade is required.
                older = os.path.getmtime("checker_config.json") - 10
                os.utime("final_grades.xlsx", (older, older))
                with open("checker_config.json", encoding="utf-8") as handle:
                    checker_config = json.load(handle)
                workflow = compute_workflow_status(
                    ["Q1"],
                    setup_readiness={"scoring": True},
                    checker_config=checker_config,
                )
                self.assertEqual(workflow["steps"]["grade"]["status"], "stale")
                self.assertEqual(workflow["next_step"], "grade")
            finally:
                os.chdir(original_cwd)

    def test_checker_done_requires_current_two_sided_gates(self):
        config = {"checker": "last_integer", "config": {}}
        config["metadata"] = {
            "calibration_status": "passed",
            "audit_status": "passed",
            "audit_rubric_version": 2,
            "audit_checker_hash": editable_checker_hash(config),
            "audit_evidence_fingerprint": "evidence",
            "audit_evidence_mtime": 9999999999,
            "positive_gate_status": "passed",
            "negative_gate_status": "passed",
            "strict_policy_version": STRICT_CONFIDENCE_POLICY_VERSION,
            "strict_status": "verified",
            "strict_checker_hash": editable_checker_hash(config),
            "grade_population_fingerprint": "population",
            "strict_sampled_id_hashes": ["anonymous"],
            "strict_too_low": {
                "status": "verified", "reviewed": 2, "required": 2,
                "observed_errors": 0, "blockers": [],
            },
            "strict_too_high": {
                "status": "verified", "reviewed": 39, "required": 39,
                "observed_errors": 0, "upper_bound": 0.05,
                "confidence_level": 0.95, "blockers": [],
            },
            "strict_blockers": [],
        }
        with patch("c_tester.verification.grade_population_evidence_fingerprint", return_value="population"):
            workflow = compute_workflow_status(
                ["Q1"],
                setup_readiness={"scoring": True},
                checker_config={"questions": {"Q1": config}},
                final_grades_path="missing-grades.xlsx",
                checker_config_path="missing-checker.json",
            )
        self.assertEqual(workflow["steps"]["checker"]["status"], "done")
        self.assertIn("Too-low", workflow["steps"]["checker"]["detail"])
        self.assertIn("Too-high", workflow["steps"]["checker"]["detail"])
        self.assertIn("2/2", workflow["steps"]["checker"]["detail"])
        self.assertIn("39/39", workflow["steps"]["checker"]["detail"])

        config["metadata"]["negative_gate_status"] = "failed"
        with patch("c_tester.verification.grade_population_evidence_fingerprint", return_value="population"):
            workflow = compute_workflow_status(
                ["Q1"],
                setup_readiness={"scoring": True},
                checker_config={"questions": {"Q1": config}},
                final_grades_path="missing-grades.xlsx",
                checker_config_path="missing-checker.json",
            )
        self.assertIn(workflow["steps"]["checker"]["status"], {"ready", "stale"})
        self.assertNotEqual(workflow["steps"]["checker"]["status"], "done")
        self.assertIn("Too-low", workflow["steps"]["checker"]["detail"])

    def test_partial_or_stale_strict_evidence_cannot_verify(self):
        config = {"checker": "exact", "config": {}}
        config["metadata"] = {
            "audit_status": "passed",
            "audit_rubric_version": 2,
            "audit_checker_hash": editable_checker_hash(config),
            "audit_evidence_fingerprint": "audit",
            "positive_gate_status": "passed",
            "negative_gate_status": "passed",
            "strict_policy_version": STRICT_CONFIDENCE_POLICY_VERSION,
            "strict_status": "verified",
            "strict_checker_hash": editable_checker_hash(config),
            "grade_population_fingerprint": "population",
            "strict_sampled_id_hashes": [],
            "strict_too_low": {
                "status": "verified", "reviewed": 1, "required": 2,
                "observed_errors": 0, "blockers": [],
            },
            "strict_too_high": {
                "status": "verified", "reviewed": 10, "required": 10,
                "observed_errors": 0, "upper_bound": 0.05,
                "confidence_level": 0.95, "blockers": [],
            },
            "strict_blockers": [],
        }
        self.assertFalse(audit_metadata_is_current(config))
        config["metadata"]["strict_too_low"]["reviewed"] = 2
        self.assertTrue(audit_metadata_is_current(config))
        config["metadata"]["strict_checker_hash"] = "old-checker"
        self.assertFalse(audit_metadata_is_current(config))

    def test_checker_detail_includes_blockers_when_not_verified(self):
        config = {"checker": "exact", "config": {}}
        config["metadata"] = {
            "calibration_status": "passed",
            "audit_status": "passed",
            "positive_gate_status": "passed",
            "negative_gate_status": "passed",
            "strict_status": "blocked",
            "strict_blockers": ["Deduction audit coverage is incomplete."],
            "strict_too_low": {"status": "blocked", "reviewed": 1, "required": 3},
            "strict_too_high": {"status": "blocked", "reviewed": 0, "required": 10, "upper_bound": 1.0},
        }
        workflow = compute_workflow_status(
            ["Q1"],
            setup_readiness={"scoring": True},
            checker_config={"questions": {"Q1": config}},
            final_grades_path="missing-grades.xlsx",
            checker_config_path="missing-checker.json",
        )
        detail = workflow["steps"]["checker"]["detail"]
        self.assertNotEqual(workflow["steps"]["checker"]["status"], "done")
        self.assertIn("Too-low 1/3", detail)
        self.assertIn("Too-high 0/10", detail)
        self.assertIn("Deduction audit coverage is incomplete.", detail)


if __name__ == "__main__":
    unittest.main()
