import unittest
import os
import tempfile

from c_tester.process import calculate_grade, write_grade
from c_tester.structural_analysis import StructuralCheckResult


class TestGradingModes(unittest.TestCase):
    def test_percentage_mode_ceilings_current_behavior(self):
        grade, explanation = calculate_grade(
            correct_count=60,
            total=61,
            discrepancies=[("0", "expected", "actual")],
        )

        self.assertEqual(grade, 99)
        self.assertIn("98.36%", explanation)

    def test_per_error_deduction_mode_caps_at_zero(self):
        discrepancies = [("1", "expected", "actual")] * 60
        grade, explanation = calculate_grade(
            correct_count=1,
            total=61,
            discrepancies=discrepancies,
            scoring_mode="per_error_deduction",
            deduction_per_error=2,
        )

        self.assertEqual(grade, 0)
        self.assertIn("deducted 2 point(s) x 60 failed test case(s)", explanation)

    def test_per_error_deduction_mode_allows_partial_deductions(self):
        discrepancies = [("1", "expected", "actual"), ("2", "expected", "actual")]
        grade, _ = calculate_grade(
            correct_count=59,
            total=61,
            discrepancies=discrepancies,
            scoring_mode="per_error_deduction",
            deduction_per_error=1.5,
        )

        self.assertEqual(grade, 97)

    def test_write_grade_applies_structural_penalty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            grade_path = os.path.join(temp_dir, "student.txt")
            write_grade(
                grade_path,
                correct_count=5,
                total=5,
                discrepancies=[],
                compile_error=None,
                structural_result=StructuralCheckResult(
                    checked=True,
                    passed=False,
                    penalty=100,
                    reason="Non-recursive solution check failed: no required recursive call was found.",
                ),
            )

            with open(grade_path, "r", encoding="utf-8") as grade_file:
                text = grade_file.read()

        self.assertIn("Grade: 0%", text)
        self.assertIn("Structural Check: failed", text)
        self.assertIn("Structural Penalty: -100", text)
        self.assertIn("Non-recursive solution check failed", text)
        self.assertIn("Structural check adjusted grade: 100 - 100 = 0%", text)


if __name__ == "__main__":
    unittest.main()
