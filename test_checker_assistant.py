import os
import tempfile
import unittest

from checker_assistant import FakeLLMProvider, audit_cases_with_llm, run_checker_tests, suggest_checker
from checker_assistant import AuditCase
from semantic_grading import load_checker_config, save_checker_config


class TestCheckerAssistant(unittest.TestCase):
    def test_save_and_load_checker_config(self):
        config = {
            "questions": {
                "Q1": {
                    "checker": "integer_list",
                    "config": {"order_matters": True, "allow_prompt_numbers": True},
                }
            }
        }
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            save_checker_config(config, temp_path)
            self.assertEqual(load_checker_config(temp_path), config)
        finally:
            os.remove(temp_path)

    def test_fake_llm_suggests_divisor_checker(self):
        suggestion = suggest_checker(
            "Q1",
            "int main(){/* divisors */}",
            ["6"],
            [("6", "Divisors of 6 are: 1 2 3 6")],
            FakeLLMProvider(),
            assignment_text="Print all divisors.",
        )

        self.assertEqual(suggestion.status, "supported")
        self.assertEqual(suggestion.checker, "divisors")
        self.assertGreaterEqual(suggestion.confidence, 0.9)

    def test_run_checker_tests_marks_wrong_variant_false(self):
        rows = run_checker_tests(
            {"checker": "reverse_integer", "config": {"answer_position": "last_integer"}},
            [("125", "Reverse of the number is: 521")],
        )
        wrong_rows = [row for row in rows if row["variant"] == "wrong"]

        self.assertEqual(len(rows), 3)
        self.assertFalse(wrong_rows[0]["passed"])

    def test_fake_llm_audit_cases(self):
        case = AuditCase(
            student_id="123456789",
            question="Q1",
            score=100,
            grade_text="Grade: 100%",
            output_text="Input: 6\nOutput: 1 2 3 6",
            excel_fields={"ID_number": "123456789", "Grade": 100},
            final_fields={"ID_number": "123456789", "Final_Grade": 100},
        )

        results = audit_cases_with_llm([case], {"Q1": {"checker": "divisors", "config": {}}}, FakeLLMProvider())

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "passed")


if __name__ == "__main__":
    unittest.main()
