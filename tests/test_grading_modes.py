import unittest

from c_tester.process import calculate_grade


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


if __name__ == "__main__":
    unittest.main()
