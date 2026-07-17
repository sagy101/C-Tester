import os
import tempfile
import unittest
import json

import pandas as pd

from c_tester.checker_assistant import (
    AssignmentContext,
    AssignmentImage,
    FakeLLMProvider,
    GeminiProvider,
    MAX_AUDIT_TEXT_CHARS,
    _compact_audit_text,
    assignment_context_for_question,
    audit_cases_with_llm,
    build_audit_prompt,
    build_suggestion_prompt,
    gemini_response_schema,
    parse_json_object,
    run_checker_tests,
    select_audit_cases,
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
    def test_gemini_provider_sends_response_schema(self):
        from unittest.mock import patch

        captured_payload = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"candidates": [{"content": {"parts": [{"text": "{\"ok\": true}"}]}}]}
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            del timeout
            captured_payload.update(json.loads(request.data.decode("utf-8")))
            return FakeResponse()

        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        }

        with patch("urllib.request.urlopen", fake_urlopen):
            response = GeminiProvider(api_key="test-key", model="gemini-test").complete_json("{}", response_schema=schema)

        self.assertEqual(response, {"ok": True})
        self.assertEqual(captured_payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(captured_payload["generationConfig"]["responseSchema"], schema)

    def test_gemini_response_schema_strips_unsupported_keywords(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": False},
                }
            },
        }

        sanitized = gemini_response_schema(schema)

        self.assertNotIn("additionalProperties", json.dumps(sanitized))
        self.assertEqual(sanitized["properties"]["items"]["items"]["type"], "object")

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

        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(any(row["variant"].startswith("accept_") for row in rows))
        self.assertTrue(any(row["variant"].startswith("reject_") for row in rows))
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
        self.assertEqual(results[0].status, "uncertain")

    def test_audit_retries_malformed_json_once(self):
        class FlakyAuditProvider:
            def __init__(self):
                self.calls = 0

            def complete_json(self, prompt, images=None):
                self.calls += 1
                if self.calls == 1:
                    raise ValueError("bad json")
                return {"verdict": "looks_correct", "risk": "low", "reason": "Recovered"}

        case = AuditCase(
            student_id="123456789",
            question="Q1",
            score=100,
            grade_text="Grade: 100%",
            output_text="Output: 1",
            excel_fields={"ID_number": "123456789", "Grade": 100},
            final_fields={"ID_number": "123456789", "Final_Grade": 100},
        )
        provider = FlakyAuditProvider()

        results = audit_cases_with_llm([case], {"Q1": {"checker": "last_integer", "config": {}}}, provider)

        self.assertEqual(provider.calls, 2)
        self.assertEqual(results[0].status, "passed")

    def test_select_audit_cases_covers_every_configured_question(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                for question in ["Q1", "Q2", "Q3"]:
                    os.makedirs(question)
                    pd.DataFrame(
                        [
                            {"ID_number": f"{question}_perfect", "Grade": 100},
                            {"ID_number": f"{question}_partial", "Grade": 45},
                        ]
                    ).to_excel(os.path.join(question, f"{question}_grades_to_upload.xlsx"), index=False)
                pd.DataFrame(
                    [
                        {"ID_number": f"{question}_{kind}", "Final_Grade": 100}
                        for question in ["Q1", "Q2", "Q3"]
                        for kind in ["perfect", "partial"]
                    ]
                ).to_excel("final_grades.xlsx", index=False)

                cases = select_audit_cases(["Q1", "Q2", "Q3"], max_cases=3)

                self.assertEqual({case.question for case in cases}, {"Q1", "Q2", "Q3"})
            finally:
                os.chdir(original_cwd)

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

    def test_assignment_context_keeps_global_preamble_rules(self):
        context = AssignmentContext(
            text=(
                "All solutions must use recursion. Non-recursive solution gets 0.\n"
                "Question 1\nConvert decimal to binary.\n"
                "Question 2\nCompute digit root."
            )
        )

        focused = assignment_context_for_question(context, "Q2")

        self.assertIn("Global assignment instructions", focused.text)
        self.assertIn("Non-recursive solution gets 0", focused.text)
        self.assertIn("Question 2", focused.text)
        self.assertNotIn("Convert decimal to binary", focused.text)

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

    def test_suggest_checker_parses_structural_requirements(self):
        class StructuralProvider(RecordingProvider):
            def complete_json(self, prompt, images=None):
                super().complete_json(prompt, images)
                return {
                    "status": "supported",
                    "checker": "last_integer",
                    "config": {},
                    "structural_requirements": {
                        "requires_recursion": True,
                        "entry_functions": ["q_2"],
                        "allow_recursive_helpers": True,
                        "forbid_loops": True,
                        "deduction": 100,
                        "deduction_required": True,
                    },
                    "confidence": 0.9,
                    "reason": "numeric answer with recursion requirement",
                }

        suggestion = suggest_checker(
            "Q2",
            "int q_2(int n){return n;}",
            ["2 10"],
            [("2 10", "Result = 1")],
            StructuralProvider(),
            assignment_text="Question 2 must use recursion. Non-recursive solution gets 0.",
        )

        self.assertEqual(suggestion.checker, "last_integer")
        self.assertTrue(suggestion.structural_requirements["requires_recursion"])
        self.assertEqual(suggestion.structural_requirements["deduction"], 100)
        self.assertFalse(suggestion.structural_requirements["deduction_required"])

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
        self.assertIn("floating point answer requiring tolerance output_contract", edge_text)
        self.assertIn("multi-column table", edge_text)
        self.assertIn("selected_question_only", edge_text)
        self.assertEqual(payload["target_question_number"], 2)
        self.assertIn("no_supported_checker", payload["decision_guidance"])
        self.assertIn("structural_requirements", payload["response_schema"])
        self.assertIn("deduction_required", payload["response_schema"]["structural_requirements"])

    def test_suggestion_prompt_warns_about_menu_style_stdin_checker_choice(self):
        prompt = build_suggestion_prompt(
            "Q2",
            "int main(){ int q,n; scanf(\"%d%d\", &q, &n); printf(\"Result = %d\", n); }",
            ["2 376", "2 12345"],
            [("2 376", "Result = 7"), ("2 12345", "Result = 6")],
            assignment_text="Question 2: compute the repeated digit sum recursively.",
        )
        payload = json.loads(prompt)

        self.assertIn("full stdin", payload["instructions"])
        self.assertIn("routing/menu fields", payload["instructions"])
        self.assertIn("input_integer_index", payload["instructions"])
        self.assertIn("menu/routing-style stdin", payload["decision_guidance"]["last_integer"])
        self.assertIn("digit-sum/digit-reduction tasks", payload["decision_guidance"]["reverse_integer"])
        self.assertIn("input_integer_index", payload["decision_guidance"]["reverse_integer"])
        self.assertIn("input_integer_index", payload["decision_guidance"]["divisors"])

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
            excel_fields={
                "ID_number": "123456789",
                "Grade": 85,
                "Wrong_Inputs": "3",
                "Structural_Check_Status": "failed",
                "Structural_Penalty": 15,
                "Structural_Notes": "Forbidden loop statement found in q_2.",
            },
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
        self.assertIn("Structural recursion/loop checks", looks_correct_text)
        self.assertIn("Submission penalties", looks_correct_text)
        self.assertIn("Assigned score conflicts", flagged_text)
        self.assertIn("Final weighted grade", flagged_text)
        self.assertIn("Structural check status", flagged_text)
        self.assertIn("Checker configuration is unsupported", flagged_text)
        self.assertIn("Reference context is insufficient", uncertain_text)
        self.assertEqual(payload["target_question_number"], 2)
        self.assertIn("structural recursion/loop check fields", payload["instructions"])
        self.assertEqual(payload["per_question_excel_fields"]["Structural_Check_Status"], "failed")

    def test_audit_prompt_requires_semantic_fairness_review_of_deductions(self):
        case = AuditCase(
            student_id="123456789",
            question="Q1",
            score=16,
            grade_text="Grade: 16%\nDiscrepancies:\nExpected: isn't\nActual: is not",
            output_text="The triangle is not a right-angled triangle.",
            excel_fields={"Grade": 16},
            final_fields={"Final_Grade": 16},
        )
        payload = json.loads(build_audit_prompt(case, {"checker": "output_contract", "config": {}}))

        flagged_text = " ".join(payload["eval_cases"]["flagged_when"])
        self.assertIn("semantically equivalent", flagged_text)
        self.assertIn("checker defect", flagged_text)
        self.assertIn("Audit fairness as well as bookkeeping", payload["instructions"])
        self.assertIn("judge on the merits", payload["instructions"])
        self.assertIn("every output-comparison deduction", payload["instructions"])
        self.assertIn("genuine content mistake", payload["instructions"])

    def test_long_audit_evidence_preserves_start_and_end_with_explicit_metadata(self):
        source = "SOURCE_START\n" + ("middle-data\n" * 200) + "SOURCE_END"
        evidence = _compact_audit_text(source, max_chars=500)

        self.assertLessEqual(len(evidence["text"]), 500)
        self.assertTrue(evidence["text"].startswith("SOURCE_START"))
        self.assertTrue(evidence["text"].endswith("SOURCE_END"))
        self.assertIn("not student-side truncation", evidence["text"])
        self.assertTrue(evidence["metadata"]["application_compacted"])
        self.assertGreater(evidence["metadata"]["omitted_middle_character_count"], 0)

    def test_audit_evidence_honors_cap_at_boundaries(self):
        complete = _compact_audit_text("x" * MAX_AUDIT_TEXT_CHARS)
        self.assertFalse(complete["metadata"]["application_compacted"])
        self.assertEqual(len(complete["text"]), MAX_AUDIT_TEXT_CHARS)

        for source_length in (MAX_AUDIT_TEXT_CHARS + 1, MAX_AUDIT_TEXT_CHARS + 825):
            with self.subTest(source_length=source_length):
                evidence = _compact_audit_text("A" + ("x" * (source_length - 2)) + "Z")
                self.assertLessEqual(len(evidence["text"]), MAX_AUDIT_TEXT_CHARS)
                self.assertTrue(evidence["text"].startswith("A"))
                self.assertTrue(evidence["text"].endswith("Z"))

    def test_audit_prompt_labels_application_compaction_as_not_student_truncation(self):
        long_output = "OUTPUT_START\n" + ("x" * (MAX_AUDIT_TEXT_CHARS + 500)) + "\nOUTPUT_END"
        case = AuditCase(
            student_id="123456789",
            question="Q1",
            score=100,
            grade_text="Grade: 100%",
            output_text=long_output,
            excel_fields={"Grade": 100},
            final_fields={"Final_Grade": 100},
        )

        payload = json.loads(build_audit_prompt(case, {"checker": "exact", "config": {}}))

        self.assertTrue(payload["student_output_evidence"]["application_compacted"])
        self.assertTrue(payload["student_output"].startswith("OUTPUT_START"))
        self.assertTrue(payload["student_output"].endswith("OUTPUT_END"))
        self.assertIn("not evidence that the student's program crashed", payload["instructions"])

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
