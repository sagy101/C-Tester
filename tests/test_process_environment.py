import os
import subprocess
import unittest
from unittest.mock import patch

from c_tester import process


class VisualStudioEnvironmentTests(unittest.TestCase):
    def test_windows_drive_pseudo_variables_are_skipped(self):
        completed = subprocess.CompletedProcess(
            args="vcvars",
            returncode=0,
            stdout="=C:=C:\\workspace\nPATH=C:\\BuildTools\nINCLUDE=C:\\Include\n",
            stderr="",
        )
        with patch.object(process.subprocess, "run", return_value=completed):
            with patch.dict(os.environ, {}, clear=False):
                self.assertTrue(process.setup_visual_studio_environment("vcvars64.bat"))
                self.assertEqual(os.environ["INCLUDE"], "C:\\Include")
                self.assertNotIn("", os.environ)

    def test_environment_setup_failure_is_reported(self):
        completed = subprocess.CompletedProcess(
            args="vcvars",
            returncode=1,
            stdout="",
            stderr="vcvars failed",
        )
        with patch.object(process.subprocess, "run", return_value=completed):
            self.assertFalse(process.setup_visual_studio_environment("missing.bat"))


if __name__ == "__main__":
    unittest.main()
