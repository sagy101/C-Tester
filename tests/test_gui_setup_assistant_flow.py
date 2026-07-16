import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch


class TestGuiSetupAssistantFlow(unittest.TestCase):
    def test_startup_validation_does_not_show_modal_for_missing_private_files(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui
                from c_tester.checker_assistant import AuditResult

                with patch("c_tester.gui.messagebox.showwarning") as showwarning_mock, patch("c_tester.gui.messagebox.showerror") as showerror_mock:
                    app = gui.App()
                    app.withdraw()
                    try:
                        self.assertFalse(app.config_valid)
                        showwarning_mock.assert_not_called()
                        showerror_mock.assert_not_called()
                    finally:
                        app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_main_and_setup_layout_have_no_known_overlaps(self):
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
                    self.assertEqual(int(app.log_frame.grid_rowconfigure(0)["weight"]), 0)
                    self.assertEqual(int(app.log_frame.grid_rowconfigure(1)["weight"]), 0)
                    self.assertTrue(app.console_collapsed)
                    app.toggle_console()
                    self.assertGreaterEqual(int(app.log_frame.grid_rowconfigure(1)["weight"]), 1)
                    self.assertFalse(app.console_collapsed)
                    self.assertEqual(str(app.compile_repair_frame.master), str(app.scoring_options_frame))
                    self.assertEqual(str(app.clear_frame.master), str(app.maintenance_frame))
                    self.assertEqual(app.global_apply_config_button.cget("text"), "Apply Config")

                    setup = gui.SetupAssistantWindow(app)
                    setup.withdraw()
                    try:
                        self.assertEqual(int(setup.title_label.grid_info()["row"]), 0)
                        self.assertEqual(int(setup.subtitle_label.grid_info()["row"]), 1)
                        self.assertEqual(int(setup.global_status_frame.grid_info()["row"]), 2)
                        self.assertTrue(setup.global_status_label.cget("text"))
                    finally:
                        setup.destroy()
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_setup_readiness_tracks_assignment_zip_and_api_requirements(self):
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
                    readiness = app.get_setup_readiness()
                    self.assertTrue(readiness["packages"])
                    self.assertTrue(readiness["assignment"])
                    self.assertTrue(readiness["checker"])
                    self.assertFalse(readiness["submissions_zip"])
                    self.assertFalse(readiness["preprocess"])

                    zip_path = os.path.join(temp_dir, "submissions.zip")
                    with zipfile.ZipFile(zip_path, "w") as submissions_zip:
                        submissions_zip.writestr("Student_123456789.zip", "")
                    app.zip_path_var.set(zip_path)
                    readiness = app.get_setup_readiness()
                    self.assertTrue(readiness["submissions_zip"])

                    app.llm_compile_repair_var.set(True)
                    app.llm_compile_repair_provider_var.set("Gemini")
                    previous_api_key = os.environ.pop("GOOGLE_API_KEY", None)
                    try:
                        with patch("c_tester.gui.get_google_api_key", return_value=None):
                            self.assertFalse(app.get_setup_readiness()["gemini_api"])
                            self.assertFalse(app.get_setup_readiness()["compile_repair_api"])
                            app.llm_compile_repair_provider_var.set("Fake")
                            self.assertTrue(app.get_setup_readiness()["compile_repair_api"])
                    finally:
                        if previous_api_key is not None:
                            os.environ["GOOGLE_API_KEY"] = previous_api_key
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_startup_setup_assistant_skips_when_ready_or_existing_grades_can_be_reviewed(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui

                app = gui.App()
                app.withdraw()
                try:
                    with patch.object(app, "open_setup_assistant") as open_setup_mock:
                        app.maybe_show_setup_assistant()
                        open_setup_mock.assert_called_once()

                    with open("final_grades.xlsx", "w", encoding="utf-8") as grades_file:
                        grades_file.write("placeholder")
                    with patch.object(app, "open_setup_assistant") as open_setup_mock:
                        app.maybe_show_setup_assistant()
                        open_setup_mock.assert_not_called()
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

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
                    with patch.object(app, "open_setup_assistant") as open_setup_mock:
                        app.maybe_show_setup_assistant()
                        open_setup_mock.assert_not_called()
                finally:
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_checker_auto_setup_all_keeps_per_question_failures(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_minimal_homework()
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui
                from c_tester.checker_assistant import AssignmentContext, SuggestionResult

                app = gui.App()
                app.withdraw()
                window = gui.CheckerManagerWindow(app)
                window.withdraw()
                success_result = {
                    "question": "Q2",
                    "suggestion": SuggestionResult("supported", "Q2", "exact", {}, 1.0, "ok"),
                    "question_config": {"checker": "exact", "config": {}},
                    "test_rows": [{"variant": "exact", "passed": True}],
                    "tests_ok": True,
                    "warnings": [],
                    "saved": True,
                    "error": "",
                }

                def fake_auto_configure(question, *_args, **_kwargs):
                    if question == "Q1":
                        raise RuntimeError("Expecting ';' delimiter")
                    return success_result

                try:
                    with patch.object(window, "make_provider", return_value=object()), \
                        patch("c_tester.gui.parse_assignment_context", return_value=AssignmentContext()), \
                        patch.object(window, "auto_configure_question", side_effect=fake_auto_configure), \
                        patch.object(
                            window,
                            "run_calibration_rounds",
                            return_value={"overall": {"status": "skipped", "reviewed": 0}, "questions": []},
                        ):
                        window._auto_setup_all_worker()
                        app.update()

                    self.assertIn("Q1: auto setup failed", window.response_textbox.get("1.0", "end"))
                    self.assertIn("Auto setup saved 1/2 checker(s); failed: Q1", window.status_label.cget("text"))
                finally:
                    window.destroy()
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_checker_audit_grading_uses_applied_gui_settings(self):
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
                window = gui.CheckerManagerWindow(app)
                window.withdraw()
                try:
                    app.gui_test_scoring_mode = "per_error_deduction"
                    app.gui_test_error_deduction = 3
                    app.gui_llm_compile_repair_enabled = True
                    app.gui_llm_compile_repair_provider = "Fake"
                    app.gui_llm_compile_repair_penalty = 11
                    app.gui_llm_compile_repair_max_attempts = 4
                    app.gui_penalty = 7
                    app.gui_per_error_penalty = True
                    app.slim_output_var.set(True)

                    with patch.object(window, "has_grade_outputs", return_value=False), \
                        patch("c_tester.gui.run_tests") as run_tests_mock, \
                        patch("c_tester.gui.create_excels") as create_excels_mock:
                        window.ensure_grade_outputs_for_audit(["Q1", "Q2"])

                    kwargs = run_tests_mock.call_args.kwargs
                    self.assertEqual(kwargs["scoring_mode"], "per_error_deduction")
                    self.assertEqual(kwargs["deduction_per_error"], 3)
                    self.assertTrue(kwargs["llm_compile_repair_enabled"])
                    self.assertIsInstance(kwargs["llm_compile_repair_provider"], gui.FakeLLMProvider)
                    self.assertEqual(kwargs["llm_compile_repair_penalty"], 11)
                    self.assertEqual(kwargs["llm_compile_repair_max_attempts"], 4)
                    self.assertEqual(kwargs["vs_path_override"], app.gui_vs_path)
                    create_excels_mock.assert_called_once_with(
                        ["Q1", "Q2"],
                        {"Q1": 50, "Q2": 50},
                        7,
                        slim=True,
                        per_error_penalty=True,
                    )
                finally:
                    window.destroy()
                    app.shutdown_for_tests()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
                os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)
                os.chdir(original_cwd)

    def test_checker_status_marks_saved_and_audited_questions(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_minimal_homework()
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
                os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"
                from c_tester import gui
                from c_tester.checker_assistant import AuditResult

                app = gui.App()
                app.withdraw()
                window = gui.CheckerManagerWindow(app)
                window.withdraw()
                try:
                    checker_config = {"checker": "exact", "config": {}}
                    window.mark_checker_saved("Q1", checker_config, test_status="passed")
                    window.record_audit_results(
                        [AuditResult("demo_student", "Q1", "passed", "looks_correct", "low", "consistent")],
                        "passed",
                    )
                    app.update()

                    self.assertEqual(
                        window.checker_config["questions"]["Q1"]["metadata"]["audit_status"],
                        "passed",
                    )
                    status_texts = " ".join(child.cget("text") for child in window.checker_state_frame.winfo_children())
                    self.assertIn("Q1: audited", status_texts)
                    self.assertEqual({int(child.grid_info()["row"]) for child in window.checker_state_frame.winfo_children()}, {0})
                    self.assertIn("audited: Q1", app.checker_status_summary())
                    app.update_setup_readiness_banner()
                    self.assertIn("audited: Q1", app.checker_status_label.cget("text"))
                finally:
                    window.destroy()
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
