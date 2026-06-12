import os
import tempfile
import unittest
import zipfile

from c_tester import configuration
from c_tester.preprocess import preprocess_submissions


class TestPreprocessSubmissions(unittest.TestCase):
    def test_single_assignment_c_file_is_copied_to_all_questions(self):
        original_cwd = os.getcwd()
        original_simple_naming = configuration.use_simple_naming
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                for question in ["Q1", "Q2", "Q3"]:
                    os.makedirs(os.path.join(question, "C"))

                outer_zip_path = os.path.join(temp_dir, "submissions.zip")
                inner_zip_path = os.path.join(temp_dir, "Student Name_123456789.zip")
                c_code = "int main(){return 0;}\n"

                with zipfile.ZipFile(inner_zip_path, "w") as inner_zip:
                    inner_zip.writestr("hw2.c", c_code)
                    inner_zip.writestr("__MACOSX/._hw2.c", "metadata")

                with zipfile.ZipFile(outer_zip_path, "w") as outer_zip:
                    outer_zip.write(inner_zip_path, "Student Name_123456789.zip")

                configuration.use_simple_naming = False
                preprocess_submissions(outer_zip_path, ["Q1", "Q2", "Q3"])

                for question in ["Q1", "Q2", "Q3"]:
                    copied_path = os.path.join(question, "C", "123456789.c")
                    self.assertTrue(os.path.exists(copied_path), f"{copied_path} should exist")
                    with open(copied_path, "r", encoding="utf-8") as copied_file:
                        self.assertEqual(copied_file.read(), c_code)

                self.assertFalse(os.path.exists("submit_error.txt"))
            finally:
                configuration.use_simple_naming = original_simple_naming
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
