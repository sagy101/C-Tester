import os
import tempfile
import unittest

from CreateExcel import parse_submit_errors


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


if __name__ == "__main__":
    unittest.main()
