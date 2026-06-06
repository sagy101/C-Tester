import os
import tempfile
import unittest

import pandas as pd

from c_tester.checker_assistant import FakeLLMProvider, audit_cases_with_llm, run_checker_tests, select_audit_cases, suggest_checker
from c_tester.create_excel import create_excels
from c_tester.semantic_grading import load_checker_config, save_checker_config


class TestDummyHomeworkVerification(unittest.TestCase):
    def test_dummy_homework_checker_and_audit_flow(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_dummy_homework()

                provider = FakeLLMProvider()
                suggestion = suggest_checker(
                    "Q1",
                    "int main(){ /* print divisors */ }",
                    ["6", "10"],
                    [("6", "Divisors of 6 are: 1 2 3 6"), ("10", "Divisors of 10 are: 1 2 5 10")],
                    provider,
                    assignment_text="Print all divisors of the input number.",
                )
                self.assertEqual(suggestion.status, "supported")
                self.assertEqual(suggestion.checker, "divisors")

                checker_config = {
                    "questions": {
                        "Q1": {"checker": suggestion.checker, "config": suggestion.config},
                        "Q2": {"checker": "last_integer", "config": {}},
                    }
                }
                save_checker_config(checker_config)
                self.assertEqual(load_checker_config(), checker_config)

                test_rows = run_checker_tests(
                    checker_config["questions"]["Q1"],
                    [("6", "Divisors of 6 are: 1 2 3 6")],
                )
                self.assertTrue(any(row["variant"] == "exact" and row["passed"] for row in test_rows))
                self.assertTrue(any(row["variant"] == "wrong" and not row["passed"] for row in test_rows))

                create_excels(["Q1", "Q2"], {"Q1": 50, "Q2": 50}, penalty=5, slim=False)

                final_df = pd.read_excel("final_grades.xlsx", dtype={"ID_number": str}).fillna("")
                self.assertEqual(len(final_df), 20)
                self.assertIn("Penalty Applied", final_df.columns)
                self.assertGreater(final_df["Penalty Applied"].astype(str).str.len().gt(0).sum(), 0)

                cases = select_audit_cases(["Q1", "Q2"], max_cases=15)
                self.assertGreaterEqual(len(cases), 10)
                sampled_scores = {case.score for case in cases}
                self.assertTrue(any(score == 100 for score in sampled_scores))
                self.assertTrue(any(50 <= score < 100 for score in sampled_scores))
                self.assertTrue(any(0 < score < 50 for score in sampled_scores))
                self.assertTrue(any(score == 0 for score in sampled_scores))

                audit_results = audit_cases_with_llm(cases, checker_config["questions"], provider, max_workers=4)
                self.assertEqual(len(audit_results), len(cases))
                self.assertTrue(all(result.status == "passed" for result in audit_results))
            finally:
                os.chdir(original_cwd)

    def _create_dummy_homework(self):
        for question in ["Q1", "Q2"]:
            os.makedirs(os.path.join(question, "grade"))
            os.makedirs(os.path.join(question, "output"))
            os.makedirs(os.path.join(question, "C"))
            with open(os.path.join(question, "input.txt"), "w", encoding="utf-8") as input_file:
                input_file.write("1\n2\n3\n4\n")
            with open(os.path.join(question, "original_sol.c"), "w", encoding="utf-8") as sol_file:
                sol_file.write("int main(){return 0;}\n")

        grades = [100, 100, 95, 90, 85, 80, 75, 70, 60, 55, 50, 40, 30, 20, 10, 1, 0, 0, 100, 65]
        for index, grade in enumerate(grades, start=1):
            student_id = f"300000{index:03d}"
            for question in ["Q1", "Q2"]:
                self._write_grade_file(question, student_id, grade, compile_error=(index == 18 and question == "Q2"))
                with open(os.path.join(question, "output", f"{student_id}.txt"), "w", encoding="utf-8") as output_file:
                    output_file.write(f"Input: 4\nOutput: dummy answer for {student_id}\n")

        with open("submit_error.txt", "w", encoding="utf-8") as error_file:
            error_file.write("Submissions with processing errors/warnings: 2 submissions with a total of 2 issues:\n")
            error_file.write("- Dummy Student_300000003.zip:  * ID found but has .zip suffix\n")
            error_file.write("- Another Dummy_300000012:  * Files found in subfolder(s), Missing Qs: Q1\n")

    def _write_grade_file(self, question, student_id, grade, compile_error=False):
        grade_path = os.path.join(question, "grade", f"{student_id}.txt")
        with open(grade_path, "w", encoding="utf-8") as grade_file:
            if compile_error:
                grade_file.write("Grade: 0%\nCompilation error: simulated compile failure\n")
                return
            grade_file.write(f"Grade: {grade}%\n")
            grade_file.write(f"(Calculated grade is: {float(grade):.2f}%)\n")
            if grade < 100:
                grade_file.write("Wrong Inputs: 2, 3\n")
                grade_file.write("\nDiscrepancies:\n")
                grade_file.write("Input: 2\nExpected: expected\nActual: actual\n\n")
            if question == "Q2" and grade == 0:
                grade_file.write("\nTimeouts: 1/4\nTimeout Inputs: 4\n")


if __name__ == "__main__":
    unittest.main()
