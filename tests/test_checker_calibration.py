import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from c_tester.checker_calibration import (
    append_checker_version,
    audited_case_signature,
    checker_config_hash,
    validate_candidate_against_rows,
)
from c_tester.checker_assistant import AssignmentContext, AuditCase, _audit_one_case, select_audit_cases


class _UncertainProvider:
    def complete_json(self, prompt, images=None, response_schema=None):
        return {"verdict": "uncertain", "risk": "medium", "reason": "evidence is truncated"}


class CheckerCalibrationTests(unittest.TestCase):
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

    def test_uncertain_audit_is_not_treated_as_checker_defect(self):
        case = AuditCase("123", "Q1", 50, "Grade: 50", "truncated", {}, {})
        result = _audit_one_case(case, {"checker": "exact", "config": {}}, _UncertainProvider(), AssignmentContext())
        self.assertEqual(result.status, "uncertain")


if __name__ == "__main__":
    unittest.main()
