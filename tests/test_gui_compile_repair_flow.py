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
                    app.test_scoring_mode_var.set("per_error_deduction")
                    app.test_error_deduction_entry.configure(state="normal")
                    app.test_error_deduction_entry.delete(0, "end")
                    app.test_error_deduction_entry.insert(0, "4")
                    app.penalty_entry.delete(0, "end")
                    app.penalty_entry.insert(0, "6")
                    app.per_error_penalty_var.set(True)
                    app.slim_output_var.set(True)
                    app.compile_repair_penalty_entry.delete(0, "end")
                    app.compile_repair_penalty_entry.insert(0, "10")
                    app.compile_repair_attempts_entry.delete(0, "end")
                    app.compile_repair_attempts_entry.insert(0, "3")
                    app.apply_gui_configuration()

                    with patch("c_tester.gui.run_tests") as run_tests_mock, patch("c_tester.gui.create_excels") as create_excels_mock:
                        app.task_run_grading_internal()

                    kwargs = run_tests_mock.call_args.kwargs
                    self.assertEqual(run_tests_mock.call_args.args[0], ["Q1", "Q2"])
                    self.assertEqual(kwargs["scoring_mode"], "per_error_deduction")
                    self.assertEqual(kwargs["deduction_per_error"], 4)
                    self.assertTrue(kwargs["llm_compile_repair_enabled"])
                    self.assertIsInstance(kwargs["llm_compile_repair_provider"], FakeLLMProvider)
                    self.assertEqual(kwargs["llm_compile_repair_penalty"], 10)
                    self.assertEqual(kwargs["llm_compile_repair_max_attempts"], 3)
                    self.assertEqual(kwargs["vs_path_override"], app.gui_vs_path)
                    create_excels_mock.assert_called_once_with(
                        ["Q1", "Q2"],
                        {"Q1": 50, "Q2": 50},
                        6,
                        slim=True,
                        per_error_penalty=True,
                    )
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_finishing_background_task_does_not_enable_dirty_grading(self):
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
                    app.mark_config_dirty()
                    app.set_controls_state("normal")

                    self.assertTrue(app.config_dirty)
                    self.assertEqual(app.run_button.cget("state"), "disabled")
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_start_grading_applies_pending_compile_repair_settings(self):
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
                    app.compile_repair_penalty_entry.insert(0, "12")
                    app.mark_config_dirty()

                    with patch.object(app, "run_task") as run_task_mock:
                        app.start_grading()

                    self.assertFalse(app.config_dirty)
                    self.assertTrue(app.gui_llm_compile_repair_enabled)
                    self.assertEqual(app.gui_llm_compile_repair_provider, "Fake")
                    self.assertEqual(app.gui_llm_compile_repair_penalty, 12)
                    run_task_mock.assert_called_once_with(app.task_run_grading_internal)
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_per_failed_test_deduction_only_enabled_for_deduction_mode(self):
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
                    app.test_scoring_mode_var.set("percentage")
                    app.update_test_error_deduction_state()
                    self.assertEqual(app.test_error_deduction_entry.cget("state"), "disabled")

                    app.test_scoring_mode_var.set("per_error_deduction")
                    app.update_test_error_deduction_state()
                    self.assertEqual(app.test_error_deduction_entry.cget("state"), "normal")
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_compile_repair_model_uses_dropdown(self):
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
                    self.assertIsInstance(app.compile_repair_model_menu, gui.ctk.CTkOptionMenu)
                    self.assertIn("gemini-2.0-flash", app.compile_repair_model_menu.cget("values"))
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
