import os
import tempfile
import unittest
from unittest.mock import patch

from c_tester.checker_assistant import FakeLLMProvider


class TestGuiCompileRepairFlow(unittest.TestCase):
    def test_gui_grading_task_passes_compile_repair_settings(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_minimal_homework()
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui

                app = gui.App()
                app.withdraw()
                try:
                    app.llm_compile_repair_var.set(True)
                    app.llm_compile_repair_provider_var.set("Fake")
                    app.compile_repair_penalty_entry.delete(0, "end")
                    app.compile_repair_penalty_entry.insert(0, "10")
                    app.compile_repair_attempts_entry.delete(0, "end")
                    app.compile_repair_attempts_entry.insert(0, "3")
                    app.apply_gui_configuration()

                    with patch("c_tester.gui.run_tests") as run_tests_mock, patch("c_tester.gui.create_excels") as create_excels_mock:
                        app.task_run_grading_internal()

                    kwargs = run_tests_mock.call_args.kwargs
                    self.assertTrue(kwargs["llm_compile_repair_enabled"])
                    self.assertIsInstance(kwargs["llm_compile_repair_provider"], FakeLLMProvider)
                    self.assertEqual(kwargs["llm_compile_repair_penalty"], 10)
                    self.assertEqual(kwargs["llm_compile_repair_max_attempts"], 3)
                    self.assertEqual(kwargs["vs_path_override"], app.gui_vs_path)
                    create_excels_mock.assert_called_once()
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def _create_minimal_homework(self):
        for question in ["Q1", "Q2"]:
            os.makedirs(os.path.join(question, "C"))
            with open(os.path.join(question, "input.txt"), "w", encoding="utf-8") as input_file:
                input_file.write("1\n")
            with open(os.path.join(question, "original_sol.c"), "w", encoding="utf-8") as sol_file:
                sol_file.write("int main(){return 0;}\n")


if __name__ == "__main__":
    unittest.main()
