import json
from contextlib import redirect_stdout
import io
import os
import tempfile
import unittest

from c_tester.llm_eval import EvalFakeProvider, built_in_eval_cases, main, run_eval_suite


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
