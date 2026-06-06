import json
from contextlib import redirect_stdout
import io
import os
import tempfile
import unittest

from c_tester.llm_eval import EvalFakeProvider, build_judge_prompt, built_in_eval_cases, main, run_eval_suite


class BrokenCompileProvider:
    def complete_json(self, prompt, images=None):
        return {
            "status": "too_bad",
            "too_bad": True,
            "fixed_code": "",
            "compile_issue": "refused",
            "fix_reason": "refused",
            "changes_made": "",
            "risk_note": "bad",
        }


class FailingProvider:
    def __init__(self, fail_times=2):
        self.fail_times = fail_times
        self.calls = 0

    def complete_json(self, prompt, images=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ValueError("malformed json")
        return {
            "status": "fixed_candidate",
            "too_bad": False,
            "fixed_code": "int main(){\nreturn 0;\n}\n",
            "compile_issue": "missing semicolon",
            "fix_reason": "added a missing semicolon",
            "changes_made": "semicolon",
            "risk_note": "",
        }


class CountingJudge:
    def __init__(self):
        self.calls = 0

    def complete_json(self, prompt, images=None):
        self.calls += 1
        return {"passed": True, "risk": "low", "reason": "ok"}


class TestLLMEval(unittest.TestCase):
    def test_fake_eval_suite_passes_all_builtin_cases(self):
        summary = run_eval_suite(EvalFakeProvider(), provider_name="fake")

        self.assertTrue(summary.ok)
        self.assertGreaterEqual(summary.total, 20)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(summary.passed, summary.total)

    def test_endpoint_filter_runs_only_requested_cases(self):
        summary = run_eval_suite(EvalFakeProvider(), provider_name="fake", endpoints={"compile_fix"})

        self.assertTrue(summary.ok)
        self.assertTrue(summary.outcomes)
        self.assertEqual({outcome.endpoint for outcome in summary.outcomes}, {"compile_fix"})

    def test_deterministic_failure_skips_llm_judge_to_save_cost(self):
        first_compile_case = next(case for case in built_in_eval_cases() if case.endpoint == "compile_fix")
        judge = CountingJudge()

        summary = run_eval_suite(
            BrokenCompileProvider(),
            provider_name="broken",
            case_ids={first_compile_case.id},
            include_llm_judge=True,
            judge_provider=judge,
            judge_provider_name="counting",
        )

        self.assertFalse(summary.ok)
        self.assertEqual(judge.calls, 0)
        self.assertTrue(summary.outcomes[0].gates[-1].skipped)

    def test_provider_errors_retry_then_pass(self):
        first_compile_case = next(case for case in built_in_eval_cases() if case.id == "compile_missing_semicolon")
        provider = FailingProvider(fail_times=1)

        summary = run_eval_suite(provider, provider_name="flaky", case_ids={first_compile_case.id})

        self.assertTrue(summary.ok)
        self.assertEqual(provider.calls, 2)

    def test_provider_errors_are_reported_without_crashing_suite(self):
        first_compile_case = next(case for case in built_in_eval_cases() if case.id == "compile_missing_semicolon")
        provider = FailingProvider(fail_times=3)

        summary = run_eval_suite(provider, provider_name="broken", case_ids={first_compile_case.id})

        self.assertFalse(summary.ok)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.outcomes[0].gates[0].name, "provider_response")

    def test_judge_prompt_includes_case_input_and_redacts_ids(self):
        review_case = next(case for case in built_in_eval_cases() if case.id == "review_integer_division")

        prompt = build_judge_prompt(review_case, review_case.fake_response)
        payload = json.loads(prompt)

        self.assertIn("case_input", payload)
        self.assertIn("code_text", payload["case_input"])
        self.assertNotIn("123456789", prompt)
        self.assertIn("semantically equivalent", payload["instructions"])

    def test_cli_writes_json_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = os.path.join(temp_dir, "llm_eval_report.json")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--provider", "fake", "--endpoint", "suggest_checker", "--json-output", report_path])

            self.assertEqual(exit_code, 0)
            with open(report_path, encoding="utf-8") as report_file:
                report = json.load(report_file)
            self.assertEqual(report["failed"], 0)
            self.assertTrue(report["outcomes"])
            self.assertEqual({outcome["endpoint"] for outcome in report["outcomes"]}, {"suggest_checker"})


if __name__ == "__main__":
    unittest.main()
