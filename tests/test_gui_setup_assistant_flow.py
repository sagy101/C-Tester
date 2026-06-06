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

    def _create_minimal_homework(self):
        for question in ["Q1", "Q2"]:
            os.makedirs(os.path.join(question, "C"))
            with open(os.path.join(question, "input.txt"), "w", encoding="utf-8") as input_file:
                input_file.write("1\n")
            with open(os.path.join(question, "original_sol.c"), "w", encoding="utf-8") as sol_file:
                sol_file.write("int main(){return 0;}\n")


if __name__ == "__main__":
    unittest.main()
