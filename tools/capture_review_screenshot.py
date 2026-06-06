"""Capture a real post-scoring review window screenshot for README docs."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

import pandas as pd
from PIL import ImageGrab


REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_PATH = REPO_ROOT / "docs" / "post_scoring_review.png"


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    original_cwd = Path.cwd()
    os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            os.chdir(temp_dir)
            create_sample_grading_artifacts()

            from c_tester import gui

            app = gui.App()
            app.geometry("1200x900+40+40")
            app.update()

            window = gui.PostScoringReviewWindow(app)
            window.geometry("1250x820+80+80")
            window.provider_var.set(gui.FAKE_PROVIDER_LABEL)
            window.update_gemini_key_status()
            if window.visible_cases:
                window.show_case(window.visible_cases[0])

            window.lift()
            window.focus_force()
            for _ in range(8):
                app.update()

            x = window.winfo_rootx()
            y = window.winfo_rooty()
            width = window.winfo_width()
            height = window.winfo_height()
            image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
            SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            image.save(SCREENSHOT_PATH)
            print(f"Saved {SCREENSHOT_PATH}")

            window.destroy()
            app.shutdown_for_tests()
            return 0
        finally:
            os.chdir(original_cwd)
            os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)


def create_sample_grading_artifacts() -> None:
    for question in ["Q1", "Q2"]:
        Path(question, "C").mkdir(parents=True, exist_ok=True)
        Path(question, "grade").mkdir(parents=True, exist_ok=True)
        Path(question, "output").mkdir(parents=True, exist_ok=True)
        Path(question, "input.txt").write_text("0\n1\n2\n", encoding="utf-8")
        Path(question, "original_sol.c").write_text("int main(){return 0;}\n", encoding="utf-8")

    Path("Q1", "C", "123456789.c").write_text(
        '#include <stdio.h>\nint main(){printf("bad");return 0;}\n',
        encoding="utf-8",
    )
    Path("Q1", "grade", "123456789.txt").write_text(
        "Grade: 98%\n"
        "Wrong Inputs: 0\n\n"
        "Discrepancies:\n"
        "Input: 0\n"
        "Expected: 0 has no Divisors!\n"
        "Actual: bad\n"
        "Semantic Reason: zero input must explicitly state there are no divisors\n",
        encoding="utf-8",
    )
    Path("Q1", "output", "123456789.txt").write_text("Input: 0\nOutput: bad\n", encoding="utf-8")
    Path("Q1", "original_sol_output.txt").write_text(
        "Input: 0\nOutput: 0 has no Divisors!\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "ID_number": "123456789",
                "Grade": 98,
                "Wrong_Inputs": "0",
                "Compilation_Error": False,
                "Timeouts": "",
                "Comments": "Wrong input 0",
            }
        ]
    ).to_excel(Path("Q1", "Q1_grades_to_upload.xlsx"), index=False)
    pd.DataFrame(
        [
            {
                "ID_number": "123456789",
                "Q1": 98,
                "Final_Grade": 98,
                "Comments": "Q1 wrong input 0",
            }
        ]
    ).to_excel("final_grades.xlsx", index=False)


if __name__ == "__main__":
    raise SystemExit(main())
