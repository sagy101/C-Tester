import os
import tempfile
import unittest

from c_tester.create_excel import (
    extract_compilation_repair_attempts,
    extract_compilation_repair_note,
    extract_compilation_repair_penalty,
    extract_compilation_repair_status,
    extract_original_compilation_error,
    parse_submit_errors,
)


class TestCreateExcelParsing(unittest.TestCase):
    def test_parse_submit_errors_preserves_colons_in_issue_text(self):
        content = (
            "Submissions with processing errors/warnings: 1 submissions with a total of 2 issues:\n"
            "- Student_123456789.zip:  * ID found but has .zip suffix * Files found in subfolder(s), Missing Qs: Q1\n"
        )

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        try:
            errors = parse_submit_errors(temp_path)
        finally:
            os.remove(temp_path)

        self.assertEqual(
            errors["123456789"],
            "ID found but has .zip suffix; Files found in subfolder(s), Missing Qs: Q1",
        )

    def test_extract_compilation_repair_metadata(self):
        text = (
            "Grade: 90%\n"
            "Original Compilation Error: yes\n"
            "Compilation Repair: fixed\n"
            "Compilation Repair Attempts: 2\n"
            "Compilation Repair Penalty: -10\n"
            "Compilation Repair Note: added missing semicolon.\n"
        )

        self.assertTrue(extract_original_compilation_error(text))
        self.assertEqual(extract_compilation_repair_status(text), "fixed")
        self.assertEqual(extract_compilation_repair_attempts(text), 2)
        self.assertEqual(extract_compilation_repair_penalty(text), 10)
        self.assertEqual(extract_compilation_repair_note(text), "added missing semicolon.")


if __name__ == "__main__":
    unittest.main()
