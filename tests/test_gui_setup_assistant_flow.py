import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch


class TestGuiSetupAssistantFlow(unittest.TestCase):
    def test_setup_readiness_tracks_assignment_zip_and_api_requirements(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                self._create_minimal_homework()
                os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
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
                    app.destroy()
            finally:
                os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
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
