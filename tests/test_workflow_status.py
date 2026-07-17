import json
import os
import tempfile
import unittest

from c_tester.workflow_status import (
    compute_workflow_status,
    normalize_deduction_cause,
    review_cause_label,
    review_response_cause,
)


class WorkflowStatusTests(unittest.TestCase):
    def test_normalize_and_labels(self):
        self.assertEqual(normalize_deduction_cause("checker_or_app"), "checker_or_app")
        self.assertEqual(normalize_deduction_cause("weird"), "unclear")
        self.assertEqual(review_cause_label("student_code"), "Student")
        self.assertEqual(review_cause_label("checker_or_app"), "Checker")

    def test_legacy_review_without_cause_defaults_to_student(self):
        self.assertEqual(review_response_cause({"deduction_is_plausible": True}), "student_code")
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


if __name__ == "__main__":
    unittest.main()
