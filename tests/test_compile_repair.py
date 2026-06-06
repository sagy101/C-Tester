import os
import tempfile
import unittest

from c_tester.checker_assistant import FakeLLMProvider
from c_tester.compile_repair import (
    TOO_BAD_EXCEL_NOTE,
    CompileRepairAttempt,
    build_compile_fix_prompt,
    repair_compilation_failure,
)


class AlwaysBadProvider:
    def complete_json(self, _prompt, images=None):
        return {
            "status": "too_bad",
            "too_bad": True,
            "fixed_code": "",
            "compile_issue": "missing structure",
            "fix_reason": TOO_BAD_EXCEL_NOTE,
            "changes_made": "",
            "risk_note": "unsafe",
        }


class NeverCompilesProvider:
    def complete_json(self, prompt, images=None):
        return {
            "status": "fixed_candidate",
            "too_bad": False,
            "fixed_code": "int main(){ return 0 }",
            "compile_issue": "missing semicolon",
            "fix_reason": "attempted semicolon repair.",
            "changes_made": "edited return statement",
            "risk_note": "",
        }


class TestCompileRepair(unittest.TestCase):
    def test_prompt_excludes_student_and_question_metadata(self):
        attempt = CompileRepairAttempt(
            attempt=1,
            candidate_path="attempt_1.c",
            candidate_code="int main(){return 0}",
            compile_error="C2143",
            compile_issue="missing semicolon",
            fix_reason="added syntax",
            changes_made="semicolon",
            risk_note="",
            compiled=False,
        )

        prompt = build_compile_fix_prompt("int main(){return 0}", "C2143", [attempt])

        self.assertIn("original_code", prompt)
        self.assertIn("current_compile_error", prompt)
        self.assertIn("attempt_history", prompt)
        self.assertNotIn("student_id", prompt)
        self.assertNotIn("question", prompt.lower())
        self.assertNotIn("reference", prompt.lower())
        self.assertNotIn("expected_outputs", prompt)

    def test_fake_provider_fix_compiles_on_first_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "123.c")
            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write("int main(){\nreturn 0\n}\n")

            def compile_func(path):
                with open(path, encoding="utf-8") as candidate_file:
                    text = candidate_file.read()
                if "return 0;" in text:
                    return path.replace(".c", ".exe"), None
                return None, "missing semicolon"

            result = repair_compilation_failure(
                source_path,
                "missing semicolon",
                FakeLLMProvider(),
                compile_func,
                max_attempts=3,
                repair_penalty=10,
            )

            self.assertEqual(result.status, "fixed")
            self.assertEqual(result.attempts, 1)
            self.assertTrue(os.path.exists(result.fixed_code_path))
            self.assertEqual(result.repair_penalty, 10)

    def test_too_bad_stops_without_attempt_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "123.c")
            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write("/* TOO_BAD */\n")

            result = repair_compilation_failure(
                source_path,
                "ambiguous missing logic",
                AlwaysBadProvider(),
                lambda _path: (None, "still broken"),
                max_attempts=3,
            )

            self.assertEqual(result.status, "too_bad")
            self.assertEqual(result.attempts, 1)
            self.assertEqual(result.repair_note, TOO_BAD_EXCEL_NOTE)
            self.assertEqual(result.attempts_history, ())

    def test_retry_loop_caps_at_max_attempts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "123.c")
            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write("int main(){ return 0 }\n")

            result = repair_compilation_failure(
                source_path,
                "missing semicolon",
                NeverCompilesProvider(),
                lambda _path: (None, "still missing semicolon"),
                max_attempts=3,
            )

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.attempts, 3)
            self.assertEqual(len(result.attempts_history), 3)


if __name__ == "__main__":
    unittest.main()
