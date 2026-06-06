import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from c_tester.checker_assistant import FakeLLMProvider
from c_tester.create_excel import create_excels
from c_tester.process import process_folder


class TestProcessCompileRepair(unittest.TestCase):
    def test_compile_failure_is_repaired_and_exported_to_excel(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_question()

                def fake_compile(path):
                    normalized = path.replace("\\", "/")
                    if normalized.endswith("original_sol.c") or normalized.endswith("good.c"):
                        return path.replace(".c", ".exe"), None
                    if "/llm_fixed/" in normalized:
                        with open(path, encoding="utf-8") as candidate_file:
                            text = candidate_file.read()
                        if "return 0;" in text:
                            return path.replace(".c", ".exe"), None
                    return None, "missing semicolon"

                with patch("c_tester.process.compile_file", side_effect=fake_compile), patch("c_tester.process.run_executable", return_value="1"):
                    status = process_folder(
                        "Q1",
                        llm_compile_repair_enabled=True,
                        llm_compile_repair_provider=FakeLLMProvider(),
                        llm_compile_repair_penalty=10,
                        llm_compile_repair_max_attempts=3,
                    )

                self.assertEqual(status, "warning")
                with open(os.path.join("Q1", "C", "bad.c"), encoding="utf-8") as original_file:
                    self.assertIn("return 0\n}", original_file.read())
                with open(os.path.join("Q1", "grade", "bad.txt"), encoding="utf-8") as grade_file:
                    repaired_grade = grade_file.read()
                self.assertIn("Grade: 90%", repaired_grade)
                self.assertIn("Original Compilation Error: yes", repaired_grade)
                self.assertIn("Compilation Repair: fixed", repaired_grade)
                self.assertIn("Compilation Repair Penalty: -10", repaired_grade)

                create_excels(["Q1"], {"Q1": 100}, penalty=5, slim=False)
                q_df = pd.read_excel(os.path.join("Q1", "Q1_grades_to_upload.xlsx"), dtype={"ID_number": str}).fillna("")
                repaired_row = q_df[q_df["ID_number"] == "bad"].iloc[0]
                self.assertFalse(bool(repaired_row["Compilation_Error"]))
                self.assertTrue(bool(repaired_row["Original_Compilation_Error"]))
                self.assertEqual(repaired_row["Compilation_Repair_Status"], "fixed")
                self.assertEqual(repaired_row["Compilation_Repair_Penalty"], 10)

                final_df = pd.read_excel("final_grades.xlsx", dtype={"ID_number": str}).fillna("")
                final_row = final_df[final_df["ID_number"] == "bad"].iloc[0]
                self.assertEqual(final_row["Final_Grade"], 90)
                self.assertIn("Compilation Repair: Q1: fixed after 1 attempts (-10)", final_row["Comments"])
            finally:
                os.chdir(original_cwd)

    def _create_question(self):
        os.makedirs(os.path.join("Q1", "C"))
        with open(os.path.join("Q1", "input.txt"), "w", encoding="utf-8") as input_file:
            input_file.write("1\n")
        with open(os.path.join("Q1", "original_sol.c"), "w", encoding="utf-8") as sol_file:
            sol_file.write("int main(){return 0;}\n")
        with open(os.path.join("Q1", "C", "good.c"), "w", encoding="utf-8") as good_file:
            good_file.write("int main(){return 0;}\n")
        with open(os.path.join("Q1", "C", "bad.c"), "w", encoding="utf-8") as bad_file:
            bad_file.write("int main(){\nreturn 0\n}\n")


if __name__ == "__main__":
    unittest.main()
