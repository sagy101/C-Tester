import os
import tempfile
import unittest
import json

from c_tester.checker_assistant import (
    AssignmentContext,
    AssignmentImage,
    FakeLLMProvider,
    assignment_context_for_question,
    audit_cases_with_llm,
    build_audit_prompt,
    build_suggestion_prompt,
    parse_json_object,
    run_checker_tests,
    suggest_checker,
)
from c_tester.checker_assistant import AuditCase
from c_tester.semantic_grading import compare_output_with_config
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

    def test_suggestion_prompt_covers_common_and_edge_checker_eval_cases(self):
        prompt = build_suggestion_prompt(
            "Q2",
            "int main(){ return 0; }",
            ["6", "125"],
            [("6", "1 2 3 6"), ("125", "521")],
            assignment_text="Question 1\nPrint divisors.\nQuestion 2\nReverse a number.",
        )
        payload = json.loads(prompt)
        eval_cases = payload["eval_cases"]

        supported_text = " ".join(item["task_shape"] + " " + item["expected_checker"] for item in eval_cases["common_supported"])
        edge_text = " ".join(item["task_shape"] + " " + item["expected_checker"] for item in eval_cases["edge_or_unsupported"])
        self.assertIn("last_integer", supported_text)
        self.assertIn("integer_list", supported_text)
        self.assertIn("divisors", supported_text)
        self.assertIn("reverse_integer", supported_text)
        self.assertIn("normalized_text", supported_text)
        self.assertIn("floating point answer requiring tolerance no_supported_checker", edge_text)
        self.assertIn("multi-column table", edge_text)
        self.assertIn("selected_question_only", edge_text)
        self.assertEqual(payload["target_question_number"], 2)
        self.assertIn("no_supported_checker", payload["decision_guidance"])

    def test_common_checker_templates_accept_prompted_answers_and_reject_wrong(self):
        cases = [
            (
                {"checker": "last_integer", "config": {}},
                "5",
                "Factorial is 120",
                "Input: 5\nAnswer: 120",
                "Input: 5\nAnswer: 121",
            ),
            (
                {"checker": "integer_list", "config": {"order_matters": True, "allow_prompt_numbers": True}},
                "5",
                "1 1 2 3 5",
                "Fibonacci: 1 1 2 3 5",
                "Fibonacci: 1 1 2 5 3",
            ),
            (
                {"checker": "divisors", "config": {"allow_prompt_numbers": True, "zero_requires_no_divisors_message": True}},
                "6",
                "Divisors of 6 are: 1 2 3 6",
                "Input: 6\nDivisors: 1 2 3 6",
                "Input: 6\nDivisors: 1 2 6",
            ),
            (
                {"checker": "reverse_integer", "config": {"answer_position": "last_integer"}},
                "125",
                "Reverse of the number is: 521",
                "Input: 125\nReverse: 521",
                "Input: 125\nReverse: 512",
            ),
            (
                {"checker": "normalized_text", "config": {"ignore_case": True, "ignore_punctuation": True}},
                "7",
                "Prime Number",
                "prime number!",
                "not prime",
            ),
        ]

        for checker_config, input_value, expected, prompted, wrong in cases:
            with self.subTest(checker=checker_config["checker"]):
                self.assertTrue(compare_output_with_config(checker_config, input_value, expected, prompted).passed)
                self.assertFalse(compare_output_with_config(checker_config, input_value, expected, wrong).passed)

    def test_audit_prompt_covers_common_and_edge_audit_eval_cases(self):
        case = AuditCase(
            student_id="123456789",
            question="Q2",
            score=85,
            grade_text="Grade: 85%\nWrong Inputs: 3\nCompile Repair: fixed with 15 point penalty",
            output_text="Input: 125\nOutput: 521",
            excel_fields={"ID_number": "123456789", "Grade": 85, "Wrong_Inputs": "3"},
            final_fields={"ID_number": "123456789", "Final_Grade": 85},
        )
        prompt = build_audit_prompt(
            case,
            {"checker": "reverse_integer", "config": {"answer_position": "last_integer"}},
            assignment_text="Question 1\nPrint divisors.\nQuestion 2\nReverse a number.",
        )
        payload = json.loads(prompt)
        eval_cases = payload["eval_cases"]

        looks_correct_text = " ".join(eval_cases["looks_correct_when"])
        flagged_text = " ".join(eval_cases["flagged_when"])
        uncertain_text = " ".join(eval_cases["uncertain_when"])
        self.assertIn("Perfect score", looks_correct_text)
        self.assertIn("Wrong-input count", looks_correct_text)
        self.assertIn("Compile repair succeeded", looks_correct_text)
        self.assertIn("Submission penalties", looks_correct_text)
        self.assertIn("Assigned score conflicts", flagged_text)
        self.assertIn("Final weighted grade", flagged_text)
        self.assertIn("Checker configuration is unsupported", flagged_text)
        self.assertIn("Reference context is insufficient", uncertain_text)
        self.assertEqual(payload["target_question_number"], 2)

    def test_parse_json_object_accepts_trailing_text(self):
        parsed = parse_json_object('{"summary": "ok", "deduction_is_plausible": true}\nExtra explanation')

        self.assertEqual(parsed["summary"], "ok")
        self.assertTrue(parsed["deduction_is_plausible"])

    def test_parse_json_object_accepts_fenced_json_with_extra_object(self):
        parsed = parse_json_object(
            '```json\n{"summary": "ok", "risk_note": "brace in string } stays"}\n```\n{"ignored": true}'
        )

        self.assertEqual(parsed["summary"], "ok")
        self.assertEqual(parsed["risk_note"], "brace in string } stays")


if __name__ == "__main__":
    unittest.main()
