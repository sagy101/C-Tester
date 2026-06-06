import os
import tempfile
import unittest

import pandas as pd

from c_tester.create_excel import (
    compute_final_grades,
    extract_compilation_repair_attempts,
    extract_compilation_repair_note,
    extract_compilation_repair_penalty,
    extract_compilation_repair_status,
    extract_original_compilation_error,
    parse_submit_errors,
)


class TestCreateExcelParsing(unittest.TestCase):
    def test_parse_submit_errors_preserves_colons_in_issue_text(self):
        content = (
            "Submissions with processing errors/warnings: 1 submissions with a total of 2 issues:\n"
            "- Student_123456789.zip:  * ID found but has .zip suffix * Files found in subfolder(s), Missing Qs: Q1\n"
        )

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        try:
            errors = parse_submit_errors(temp_path)
        finally:
            os.remove(temp_path)

        self.assertEqual(
            errors["123456789"],
            "ID found but has .zip suffix; Files found in subfolder(s), Missing Qs: Q1",
        )

    def test_extract_compilation_repair_metadata(self):
        text = (
            "Grade: 90%\n"
            "Original Compilation Error: yes\n"
            "Compilation Repair: fixed\n"
            "Compilation Repair Attempts: 2\n"
            "Compilation Repair Penalty: -10\n"
            "Compilation Repair Note: added missing semicolon.\n"
        )

        self.assertTrue(extract_original_compilation_error(text))
        self.assertEqual(extract_compilation_repair_status(text), "fixed")
        self.assertEqual(extract_compilation_repair_attempts(text), 2)
        self.assertEqual(extract_compilation_repair_penalty(text), 10)
        self.assertEqual(extract_compilation_repair_note(text), "added missing semicolon.")

    def test_final_comments_include_weighted_grade_calculation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                folder_data = {
                    "Q1": self._grade_df("123456789", 86),
                    "Q2": self._grade_df("123456789", 100),
                }

                result = compute_final_grades(folder_data, {"Q1": 50, "Q2": 50}, penalty=5, slim=True)

                self.assertEqual(result.loc[0, "Final_Grade"], 93)
                comments = result.loc[0, "Comments"]
                self.assertIn("Grade Calculation:", comments)
                self.assertIn("Q1: 86 x 50% = 43.00", comments)
                self.assertIn("Q2: 100 x 50% = 50.00", comments)
                self.assertIn("Weighted subtotal: 93.00", comments)
                self.assertIn("Final grade: ceil(max(0, 93.00)) = 93", comments)
                self.assertNotIn("Submission penalty:", comments)
            finally:
                os.chdir(original_cwd)

    def test_final_comments_include_cumulative_submission_penalty_calculation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with open("submit_error.txt", "w", encoding="utf-8") as error_file:
                    error_file.write(
                        "Submissions with processing errors/warnings: 1 submissions with a total of 2 issues:\n"
                        "- Student_123456789.zip:  * bad archive name * nested folder\n"
                    )
                folder_data = {
                    "Q1": self._grade_df("123456789", 90),
                    "Q2": self._grade_df("123456789", 90),
                }

                result = compute_final_grades(
                    folder_data,
                    {"Q1": 50, "Q2": 50},
                    penalty=5,
                    slim=True,
                    per_error_penalty=True,
                )

                self.assertEqual(result.loc[0, "Final_Grade"], 80)
                comments = result.loc[0, "Comments"]
                self.assertIn("Weighted subtotal: 90.00", comments)
                self.assertIn("Submission penalty: -5 x 2 = -10", comments)
                self.assertIn("Final grade: ceil(max(0, 80.00)) = 80", comments)
                self.assertIn("Penalty: bad archive name; nested folder (-5% x 2 = -10%)", comments)
            finally:
                os.chdir(original_cwd)

    def test_final_comments_show_compile_repair_penalty_in_question_breakdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                folder_data = {
                    "Q1": self._grade_df("123456789", 100),
                    "Q2": self._grade_df(
                        "123456789",
                        85,
                        repair_status="fixed",
                        repair_attempts=2,
                        repair_penalty=15,
                        repair_note="renamed the entry point to main.",
                    ),
                }

                result = compute_final_grades(folder_data, {"Q1": 50, "Q2": 50}, penalty=5, slim=True)

                self.assertEqual(result.loc[0, "Final_Grade"], 93)
                comments = result.loc[0, "Comments"]
                self.assertIn("Q2: 85 x 50% = 42.50 (includes compile repair penalty -15)", comments)
                self.assertIn("Compilation Repair: Q2: fixed after 2 attempts (-15): renamed the entry point to main.", comments)
            finally:
                os.chdir(original_cwd)

    @staticmethod
    def _grade_df(
        student_id,
        grade,
        wrong_inputs="",
        timeout_inputs="",
        repair_status="",
        repair_attempts=0,
        repair_penalty=0,
        repair_note="",
    ):
        return pd.DataFrame(
            [
                {
                    "ID_number": student_id,
                    "Grade": grade,
                    "Compilation_Error": False,
                    "Original_Compilation_Error": bool(repair_status),
                    "Timeouts": 0,
                    "Wrong_Inputs": wrong_inputs,
                    "Timeout_Inputs": timeout_inputs,
                    "Compilation_Repair_Status": repair_status,
                    "Compilation_Repair_Attempts": repair_attempts,
                    "Compilation_Repair_Penalty": repair_penalty,
                    "Compilation_Repair_Note": repair_note,
                }
            ]
        )


if __name__ == "__main__":
    unittest.main()
