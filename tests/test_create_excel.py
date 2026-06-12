import os
import json
import tempfile
import unittest

import pandas as pd

from c_tester.create_excel import (
    build_summary_tables,
    compute_final_grades,
    create_excels,
    extract_compilation_repair_attempts,
    extract_compilation_repair_note,
    extract_compilation_repair_penalty,
    extract_compilation_repair_status,
    extract_grade_calculation,
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

    def test_extract_grade_calculation(self):
        text = (
            "Grade: 96%\n"
            "(Calculated grade is: 96.00% (deducted 2 point(s) x 2 failed test case(s); "
            "3/5 correct, percentage would be 60.00%))\n"
            "Wrong Inputs: 3, 7\n"
        )

        self.assertEqual(
            extract_grade_calculation(text),
            "Calculated grade is: 96.00% (deducted 2 point(s) x 2 failed test case(s); "
            "3/5 correct, percentage would be 60.00%)",
        )

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

    def test_failed_test_cases_include_question_grade_calculation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                folder_data = {
                    "Q1": self._grade_df(
                        "123456789",
                        96,
                        wrong_inputs="3, 7",
                        grade_calculation=(
                            "Calculated grade is: 96.00% (deducted 2 point(s) x 2 failed test case(s); "
                            "3/5 correct, percentage would be 60.00%)"
                        ),
                    ),
                    "Q2": self._grade_df("123456789", 100),
                }

                result = compute_final_grades(folder_data, {"Q1": 50, "Q2": 50}, penalty=5, slim=True)

                self.assertEqual(result.loc[0, "Final_Grade"], 98)
                comments = result.loc[0, "Comments"]
                self.assertIn("Failed Test Cases:", comments)
                self.assertIn(
                    "Q1: failed 2/5 inputs (examples: 3, 7) | Calculated grade is: 96.00% "
                    "(deducted 2 point(s) x 2 failed test case(s); 3/5 correct, percentage would be 60.00%)",
                    comments,
                )
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

    def test_final_comments_show_structural_penalty_in_question_breakdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                folder_data = {
                    "Q1": self._grade_df("123456789", 100),
                    "Q2": self._grade_df(
                        "123456789",
                        0,
                        structural_status="failed",
                        structural_penalty=100,
                        structural_notes=(
                            "Non-recursive solution check failed: no required recursive call "
                            "was found from 'q_2'."
                        ),
                    ),
                }

                result = compute_final_grades(folder_data, {"Q1": 50, "Q2": 50}, penalty=5, slim=True)

                self.assertEqual(result.loc[0, "Final_Grade"], 50)
                comments = result.loc[0, "Comments"]
                self.assertIn("Q2: 0 x 50% = 0.00 (includes structural penalty -100)", comments)
                self.assertIn(
                    "Non-Recursive Solution Checks: Q2: failed (-100): "
                    "Non-recursive solution check failed: no required recursive call was found from 'q_2'.",
                    comments,
                )
            finally:
                os.chdir(original_cwd)

    def test_build_summary_tables_counts_key_metrics_and_top_wrong_inputs(self):
        final_grades_df = pd.DataFrame(
            [
                {"ID_number": "111", "Comments": "", "Final_Grade": 100},
                {"ID_number": "222", "Comments": "Penalty: nested folder (-5%)", "Final_Grade": 20},
                {"ID_number": "333", "Comments": "", "Final_Grade": 0},
            ]
        )
        folder_data = {
            "Q1": pd.DataFrame(
                [
                    self._grade_row("111", 100),
                    self._grade_row("222", 50, compilation_error=True, wrong_inputs="1 2, 1 3", timeouts=1),
                    self._grade_row(
                        "333",
                        0,
                        wrong_inputs="1 2",
                        structural_status="failed",
                        structural_penalty=100,
                        structural_notes="Non-recursive solution.",
                    ),
                ]
            ),
            "Q2": pd.DataFrame(
                [
                    self._grade_row("111", 100),
                    self._grade_row("222", 60, repair_status="fixed", repair_note="added semicolon."),
                    self._grade_row("333", 0, wrong_inputs="2 9"),
                ]
            ),
        }

        tables = build_summary_tables(final_grades_df, folder_data, {"Q1": 50, "Q2": 50}, top_wrong_inputs=2)

        overall = dict(zip(tables["overall"]["Metric"], tables["overall"]["Value"]))
        self.assertEqual(overall["Students graded"], 3)
        self.assertEqual(overall["Median final grade"], 20)
        self.assertEqual(overall["Students with compilation errors"], 1)
        self.assertEqual(overall["LLM compile repairs"], 1)
        self.assertEqual(overall["Non-recursive penalties"], 1)
        self.assertEqual(overall["Submission penalties applied"], 1)

        q1 = tables["per_question"][tables["per_question"]["Question"] == "Q1"].iloc[0]
        self.assertEqual(q1["Average"], 50)
        self.assertEqual(q1["Compilation_Errors"], 1)
        self.assertEqual(q1["Students_With_Timeouts"], 1)
        self.assertEqual(q1["Top_Wrong_Inputs"], "1 2 (2); 1 3 (1)")

        top_wrong = tables["top_wrong_inputs"].iloc[0]
        self.assertEqual(top_wrong["Question"], "Q1")
        self.assertEqual(top_wrong["Input"], "1 2")
        self.assertEqual(top_wrong["Failed_Students"], 2)
        self.assertEqual(top_wrong["Failure_Rate"], 66.67)

        attention = tables["attention_needed"]
        self.assertEqual(set(attention["ID_number"]), {"222", "333"})
        details_by_id = dict(zip(attention["ID_number"], attention["Details"]))
        self.assertIn("Q1: score 50", details_by_id["222"])
        self.assertIn("compilation error", details_by_id["222"])
        self.assertIn("Submission penalty", details_by_id["222"])
        self.assertIn("Overall: final grade is 0", details_by_id["333"])
        self.assertIn("non-recursive penalty -100", details_by_id["333"])

    def test_final_comments_summarize_all_or_almost_all_failed_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                folder_data = {
                    "Q1": self._grade_df(
                        "123456789",
                        0,
                        wrong_inputs="1, 2, 3, 4, 5",
                        grade_calculation="Calculated grade is: 0.00% (0/5 correct, percentage would be 0.00%)",
                    ),
                    "Q2": self._grade_df(
                        "123456789",
                        10,
                        wrong_inputs="1, 2, 3, 4, 5, 6, 7, 8, 9",
                        grade_calculation="Calculated grade is: 10.00% (1/10 correct, percentage would be 10.00%)",
                    ),
                }

                result = compute_final_grades(folder_data, {"Q1": 50, "Q2": 50}, penalty=0, slim=True)

                comments = result.loc[0, "Comments"]
                self.assertIn("Q1: failed all 5 inputs", comments)
                self.assertIn("Q2: failed 9/10 inputs; passed only 1", comments)
            finally:
                os.chdir(original_cwd)

    def test_create_excels_writes_summary_sheet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with open("student_names.json", "w", encoding="utf-8") as names_file:
                    json.dump({"123456789": "Student Name"}, names_file)
                os.makedirs(os.path.join("Q1", "grade"))
                with open(os.path.join("Q1", "grade", "123456789.txt"), "w", encoding="utf-8") as grade_file:
                    grade_file.write("Grade: 100%\nWrong Inputs:\nTimeouts: 0/1\n")

                create_excels(["Q1"], {"Q1": 100}, penalty=0, slim=True)

                with pd.ExcelFile("final_grades.xlsx") as excel_file:
                    self.assertIn("Sheet1", excel_file.sheet_names)
                    self.assertIn("Student Details", excel_file.sheet_names)
                    self.assertIn("Summary", excel_file.sheet_names)
                    upload_sheet = pd.read_excel(excel_file, sheet_name="Sheet1")
                    details = pd.read_excel(excel_file, sheet_name="Student Details")
                    summary = pd.read_excel(excel_file, sheet_name="Summary", header=None)
                self.assertEqual(list(upload_sheet.columns), ["ID_number", "Name", "Comments", "Final_Grade"])
                self.assertEqual(upload_sheet.loc[0, "Name"], "Student Name")
                self.assertEqual(details.loc[0, "Name"], "Student Name")
                self.assertIn("Grade_Q1_100%", details.columns)
                self.assertIn("Wrong_Inputs_Q1", details.columns)
                self.assertIn("Compilation_Error_Q1", details.columns)
                self.assertTrue(summary.eq("Overall Metrics").any().any())
                self.assertTrue(summary.eq("Per-Question Metrics").any().any())
                self.assertTrue(summary.eq("Top Wrong Inputs").any().any())
            finally:
                os.chdir(original_cwd)

    @staticmethod
    def _grade_df(
        student_id,
        grade,
        wrong_inputs="",
        grade_calculation="",
        timeout_inputs="",
        repair_status="",
        repair_attempts=0,
        repair_penalty=0,
        repair_note="",
        structural_status="",
        structural_penalty=0,
        structural_notes="",
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
                    "Grade_Calculation": grade_calculation,
                    "Timeout_Inputs": timeout_inputs,
                    "Compilation_Repair_Status": repair_status,
                    "Compilation_Repair_Attempts": repair_attempts,
                    "Compilation_Repair_Penalty": repair_penalty,
                    "Compilation_Repair_Note": repair_note,
                    "Structural_Check_Status": structural_status,
                    "Structural_Penalty": structural_penalty,
                    "Structural_Notes": structural_notes,
                }
            ]
        )

    @staticmethod
    def _grade_row(student_id, grade, **overrides):
        row = {
            "ID_number": student_id,
            "Grade": grade,
            "Compilation_Error": False,
            "Original_Compilation_Error": False,
            "Timeouts": 0,
            "Wrong_Inputs": "",
            "Grade_Calculation": "",
            "Timeout_Inputs": "",
            "Compilation_Repair_Status": "",
            "Compilation_Repair_Attempts": 0,
            "Compilation_Repair_Penalty": 0,
            "Compilation_Repair_Note": "",
            "Structural_Check_Status": "",
            "Structural_Penalty": 0,
            "Structural_Notes": "",
        }
        aliases = {
            "compilation_error": "Compilation_Error",
            "original_compilation_error": "Original_Compilation_Error",
            "wrong_inputs": "Wrong_Inputs",
            "timeouts": "Timeouts",
            "timeout_inputs": "Timeout_Inputs",
            "repair_status": "Compilation_Repair_Status",
            "repair_attempts": "Compilation_Repair_Attempts",
            "repair_penalty": "Compilation_Repair_Penalty",
            "repair_note": "Compilation_Repair_Note",
            "structural_status": "Structural_Check_Status",
            "structural_penalty": "Structural_Penalty",
            "structural_notes": "Structural_Notes",
        }
        overrides = {aliases.get(key, key): value for key, value in overrides.items()}
        row.update(overrides)
        if row["Compilation_Repair_Status"]:
            row["Original_Compilation_Error"] = True
        return row


if __name__ == "__main__":
    unittest.main()
