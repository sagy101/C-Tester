import os
import tempfile
import unittest

from c_tester.checker_assistant import (
    AssignmentContext,
    AssignmentImage,
    FakeLLMProvider,
    assignment_context_for_question,
    audit_cases_with_llm,
    run_checker_tests,
    suggest_checker,
)
from c_tester.checker_assistant import AuditCase
from c_tester.semantic_grading import load_checker_config, save_checker_config


class RecordingProvider:
    def __init__(self):
        self.prompt = ""
        self.images = []

    def complete_json(self, prompt, images=None):
        self.prompt = prompt
        self.images = list(images or [])
        return {
            "status": "supported",
            "checker": "last_integer",
            "config": {"answer_position": "last_integer"},
            "confidence": 0.8,
            "reason": "recorded",
        }


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

    def test_assignment_context_focuses_selected_question(self):
        context = AssignmentContext(
            text="Intro\nQuestion 1\nPrint divisors.\nQuestion 2\nReverse a number.",
            images=(
                AssignmentImage("page 1", "image/png", b"one", text="Question 1\nPrint divisors."),
                AssignmentImage("page 2", "image/png", b"two", text="Question 2\nReverse a number."),
            ),
        )

        focused = assignment_context_for_question(context, "Q2")

        self.assertIn("Question 2", focused.text)
        self.assertNotIn("Question 1", focused.text)
        self.assertEqual([image.label for image in focused.images], ["page 2"])

    def test_suggest_checker_passes_assignment_images_to_provider(self):
        provider = RecordingProvider()
        image = AssignmentImage("page 1", "image/png", b"image-bytes", text="Question 1")

        suggestion = suggest_checker(
            "Q1",
            "int main(){ printf(\"42\"); }",
            ["1"],
            [("1", "42")],
            provider,
            assignment_text="Question 1\nPrint a number.",
            assignment_images=[image],
        )

        self.assertEqual(suggestion.checker, "last_integer")
        self.assertEqual(provider.images, [image])
        self.assertIn("target_question_number", provider.prompt)


if __name__ == "__main__":
    unittest.main()
