import os
import tempfile
import time
import unittest
from unittest.mock import patch

import pandas as pd

from c_tester.checker_assistant import FakeLLMProvider
from c_tester.clear_utils import clear_review_files
from c_tester.post_scoring_review import build_score_review_prompt, load_review_cases, review_cases_with_llm
from tools.privacy_audit import private_matches


class TestPostScoringReview(unittest.TestCase):
    def test_prompt_is_anonymized_and_review_locks_row(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_review_fixture()

                policy = {
                    "test_case_scoring": {
                        "mode": "per_error_deduction",
                        "deduction_per_failed_input": 2,
                        "per_error_deduction_formula": "max(0, 100 - 2 * failed_tests)",
                    },
                    "submission_error_penalty": {
                        "points_per_error": 5,
                        "mode": "cumulative_per_error",
                        "applies_to": "RAR extraction, invalid naming, and nested subfolder submission issues",
                    },
                    "compile_repair": {
                        "enabled": True,
                        "penalty_after_successful_repair": 10,
                        "max_attempts": 3,
                    },
                }
                cases = load_review_cases(["Q1"], grading_policy=policy)
                self.assertEqual(len(cases), 1)
                case = cases[0]
                self.assertEqual(case.anonymized_label, "student_001")
                self.assertEqual(case.code_source, "original")
                self.assertEqual(case.failed_cases[0].input_value, "0")
                self.assertIn("Actual output text", case.student_output_text)
                self.assertIn("Expected output text", case.expected_output_text)

                prompt = build_score_review_prompt(case)
                self.assertIn("review_score_deduction", prompt)
                self.assertIn("student_001", prompt)
                self.assertIn("artifact_guide", prompt)
                self.assertIn("expected_output_by_input", prompt)
                self.assertIn("student_output_by_input", prompt)
                self.assertIn("do not assign a replacement score", prompt)
                self.assertIn("grading_policy", prompt)
                self.assertIn("per_error_deduction", prompt)
                self.assertIn("cumulative_per_error", prompt)
                self.assertIn("RAR extraction", prompt)
                self.assertIn("nested subfolder", prompt)
                self.assertNotIn("123456789", prompt)
                self.assertNotIn('"ID_number"', prompt)

                results = review_cases_with_llm([case], FakeLLMProvider(), max_workers=1)
                self.assertEqual(len(results), 1)
                self.assertTrue(os.path.exists(os.path.join("Q1", "review", "123456789.json")))

                reloaded = load_review_cases(["Q1"])[0]
                self.assertTrue(reloaded.reviewed)
                self.assertIn("summary", reloaded.saved_review["response"])
            finally:
                os.chdir(original_cwd)

    def test_repaired_code_is_preferred_when_repair_report_exists(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_review_fixture()
                os.makedirs(os.path.join("Q1", "llm_fixed", "123456789"), exist_ok=True)
                fixed_path = os.path.join("Q1", "llm_fixed", "123456789", "attempt_1.c")
                with open(fixed_path, "w", encoding="utf-8") as fixed_file:
                    fixed_file.write("int main(){return 0;}\n")
                with open(os.path.join("Q1", "llm_fixed", "123456789", "repair_report.json"), "w", encoding="utf-8") as report_file:
                    report_file.write(
                        '{"status":"fixed","fixed_code_path":"Q1/llm_fixed/123456789/attempt_1.c","repair_note":"fixed entry point"}'
                    )

                case = load_review_cases(["Q1"])[0]

                self.assertEqual(case.code_source, "repaired")
                self.assertIn("return 0;", case.code_text)
                self.assertEqual(case.repair_metadata["repair_note"], "fixed entry point")
            finally:
                os.chdir(original_cwd)

    def test_long_notes_are_preserved_with_single_line_preview(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                long_note = self._create_review_fixture()

                case = load_review_cases(["Q1"])[0]
                self.assertEqual(case.notes, long_note)

                from c_tester import gui

                preview = gui.PostScoringReviewWindow._shorten(case.notes, 90)
                self.assertLessEqual(len(preview), 90)
                self.assertNotIn("\n", preview)
                self.assertTrue(preview.endswith("..."))
            finally:
                os.chdir(original_cwd)

    def test_clear_review_files_and_privacy_audit_pattern(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                os.makedirs(os.path.join("Q1", "review"), exist_ok=True)
                review_path = os.path.join("Q1", "review", "123456789.json")
                with open(review_path, "w", encoding="utf-8") as review_file:
                    review_file.write("{}")

                self.assertEqual(private_matches(["Q1/review/123456789.json"]), ["Q1/review/123456789.json"])
                clear_review_files(["Q1"])
                self.assertFalse(os.path.exists(review_path))
            finally:
                os.chdir(original_cwd)

    def test_gui_enables_and_opens_review_window_after_grading_output_exists(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_review_fixture()
                os.makedirs(os.path.join("Q2", "C"), exist_ok=True)
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui

                with patch("c_tester.gui.get_google_api_key", return_value=None):
                    app = gui.App()
                    app.withdraw()
                    try:
                        app.update_excel_button_state()
                        self.assertEqual(app.score_review_button.cget("state"), "normal")
                        app.gui_test_scoring_mode = "per_error_deduction"
                        app.gui_test_error_deduction = 3
                        app.gui_penalty = 7
                        app.gui_per_error_penalty = True
                        app.gui_llm_compile_repair_enabled = True
                        app.gui_llm_compile_repair_penalty = 11
                        app.gui_llm_compile_repair_max_attempts = 4
                        original_review_window = gui.PostScoringReviewWindow

                        class FakeReviewWindow:
                            def __init__(self, parent):
                                self.parent = parent
                                self.shown = False
                                self.policy = original_review_window.active_grading_policy(self)

                            def winfo_exists(self):
                                return True

                            def show_on_top(self):
                                self.shown = True

                        with patch("c_tester.gui.PostScoringReviewWindow", FakeReviewWindow):
                            app.open_post_scoring_review()
                            self.assertIsInstance(app.score_review_window, FakeReviewWindow)
                            self.assertTrue(app.score_review_window.shown)
                            policy = app.score_review_window.policy
                            self.assertEqual(policy["test_case_scoring"]["mode"], "per_error_deduction")
                            self.assertEqual(policy["test_case_scoring"]["deduction_per_failed_input"], 3)
                            self.assertEqual(policy["submission_error_penalty"]["points_per_error"], 7)
                            self.assertEqual(policy["submission_error_penalty"]["mode"], "cumulative_per_error")
                            self.assertEqual(policy["compile_repair"]["penalty_after_successful_repair"], 11)
                            self.assertEqual(policy["compile_repair"]["max_attempts"], 4)
                    finally:
                        app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_review_window_can_search_by_local_student_id(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_review_fixture()
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui

                with patch("c_tester.gui.get_google_api_key", return_value=None):
                    app = gui.App()
                    app.withdraw()
                    window = gui.PostScoringReviewWindow(app)
                    window.withdraw()
                    try:
                        self.assertEqual(len(window.visible_cases), 1)
                        window.id_search_var.set("4567")
                        window.update()
                        self.assertEqual(len(window.visible_cases), 1)
                        self.assertEqual(window.visible_cases[0].student_id, "123456789")
                        children = window.review_tree.get_children()
                        self.assertEqual(len(children), 1)
                        self.assertEqual(window.review_tree.yview()[0], 0.0)
                        self.assertEqual(window.current_case.student_id, "123456789")
                        window.review_tree.selection_set(children[0])
                        window.copy_selected_student_ids()
                        self.assertEqual(window.clipboard_get(), "123456789")

                        window.id_search_var.set("no-match")
                        window.update()
                        self.assertEqual(window.visible_cases, [])

                        prompt = build_score_review_prompt(window.cases[0])
                        self.assertNotIn("123456789", prompt)
                    finally:
                        window.destroy()
                        app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_review_window_sorts_rows_by_student_id(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_review_fixture()
                self._add_review_student("111111111", grade=97)
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui

                with patch("c_tester.gui.get_google_api_key", return_value=None):
                    app = gui.App()
                    app.withdraw()
                    window = gui.PostScoringReviewWindow(app)
                    window.withdraw()
                    try:
                        self.assertEqual([case.student_id for case in window.visible_cases], ["111111111", "123456789"])
                    finally:
                        window.destroy()
                        app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_review_window_many_rows_filter_and_refresh_stay_fast(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_review_fixture()
                for index in range(80):
                    self._add_review_student(f"demo_{index:03d}", grade=90 + (index % 9))
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui

                with patch("c_tester.gui.get_google_api_key", return_value=None):
                    app = gui.App()
                    app.withdraw()
                    start = time.perf_counter()
                    window = gui.PostScoringReviewWindow(app)
                    first_load_seconds = time.perf_counter() - start
                    window.withdraw()
                    try:
                        self.assertLess(first_load_seconds, 3.0)
                        start = time.perf_counter()
                        window.id_search_var.set("demo_079")
                        window.update()
                        filter_seconds = time.perf_counter() - start
                        self.assertLess(filter_seconds, 1.0)
                        self.assertEqual(len(window.visible_cases), 1)
                        self.assertEqual(window.visible_cases[0].student_id, "demo_079")
                        self.assertEqual(window.review_tree.yview()[0], 0.0)
                    finally:
                        window.destroy()
                        app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def _create_review_fixture(self):
        long_note = (
            "Q1 wrong input 0. This is a deliberately long final comment with preprocessing penalty context, "
            "nested subfolder notes, and enough detail to verify the table shows only a compact preview while "
            "the selected Notes tab preserves the complete text."
        )
        os.makedirs(os.path.join("Q1", "C"), exist_ok=True)
        os.makedirs(os.path.join("Q1", "grade"), exist_ok=True)
        os.makedirs(os.path.join("Q1", "output"), exist_ok=True)
        with open(os.path.join("Q1", "C", "123456789.c"), "w", encoding="utf-8") as source_file:
            source_file.write("#include <stdio.h>\nint main(){printf(\"bad\");return 0;}\n")
        with open(os.path.join("Q1", "output", "123456789.txt"), "w", encoding="utf-8") as output_file:
            output_file.write("Input: 0\nOutput: Actual output text\n")
        with open(os.path.join("Q1", "original_sol_output.txt"), "w", encoding="utf-8") as expected_file:
            expected_file.write("Input: 0\nOutput: Expected output text\n")
        with open(os.path.join("Q1", "grade", "123456789.txt"), "w", encoding="utf-8") as grade_file:
            grade_file.write(
                "Grade: 98%\n"
                "Wrong Inputs: 0\n\n"
                "Discrepancies:\n"
                "Input: 0\n"
                "Expected: 0 has no Divisors!\n"
                "Actual: bad\n"
                "Semantic Reason: zero input must explicitly state there are no divisors\n"
            )
        pd.DataFrame(
            [
                {
                    "ID_number": "123456789",
                    "Grade": 98,
                    "Wrong_Inputs": "0",
                    "Compilation_Error": False,
                    "Timeouts": "",
                    "Comments": long_note,
                }
            ]
        ).to_excel(os.path.join("Q1", "Q1_grades_to_upload.xlsx"), index=False)
        pd.DataFrame(
            [
                {
                    "ID_number": "123456789",
                    "Q1": 98,
                    "Final_Grade": 98,
                    "Comments": long_note,
                }
            ]
        ).to_excel("final_grades.xlsx", index=False)
        return long_note

    def _add_review_student(self, student_id, grade=97):
        with open(os.path.join("Q1", "C", f"{student_id}.c"), "w", encoding="utf-8") as source_file:
            source_file.write("#include <stdio.h>\nint main(){printf(\"also bad\");return 0;}\n")
        with open(os.path.join("Q1", "output", f"{student_id}.txt"), "w", encoding="utf-8") as output_file:
            output_file.write("Input: 0\nOutput: Another actual output\n")
        with open(os.path.join("Q1", "grade", f"{student_id}.txt"), "w", encoding="utf-8") as grade_file:
            grade_file.write(
                f"Grade: {grade}%\n"
                "Wrong Inputs: 0\n\n"
                "Discrepancies:\n"
                "Input: 0\n"
                "Expected: 0 has no Divisors!\n"
                "Actual: also bad\n"
                "Semantic Reason: zero input must explicitly state there are no divisors\n"
            )

        q1_path = os.path.join("Q1", "Q1_grades_to_upload.xlsx")
        q1_df = pd.read_excel(q1_path)
        q1_df = pd.concat(
            [
                q1_df,
                pd.DataFrame(
                    [
                        {
                            "ID_number": student_id,
                            "Grade": grade,
                            "Wrong_Inputs": "0",
                            "Compilation_Error": False,
                            "Timeouts": "",
                            "Comments": "Q1 wrong input 0",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        q1_df.to_excel(q1_path, index=False)

        final_df = pd.read_excel("final_grades.xlsx")
        final_df = pd.concat(
            [
                final_df,
                pd.DataFrame(
                    [
                        {
                            "ID_number": student_id,
                            "Q1": grade,
                            "Final_Grade": grade,
                            "Comments": "Q1 wrong input 0",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        final_df.to_excel("final_grades.xlsx", index=False)


if __name__ == "__main__":
    unittest.main()
