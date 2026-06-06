"""Capture README screenshots from a synthetic public fixture."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile

import pandas as pd
from PIL import ImageGrab


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
DEMO_STUDENT_ID = "demo_student"


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    original_cwd = Path.cwd()
    os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
    os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            os.chdir(temp_dir)
            create_sample_project()

            from c_tester import gui

            app = gui.App()
            app.geometry("1050x760+40+20")
            app.zip_path_var.set(str(Path(temp_dir) / "submissions.zip"))
            app.detect_and_apply_naming(show_dialog=False)
            app.update_setup_readiness_banner()
            settle(app)

            app.workspace_tabs.set("Run")
            settle(app)
            capture_widget(app, "gui.png")

            app.workspace_tabs.set("Scoring Options")
            settle(app)
            capture_widget(app, "gui_scoring_options.png")

            app.workspace_tabs.set("Maintenance")
            settle(app)
            capture_widget(app, "gui_maintenance.png")

            app.workspace_tabs.set("Run")
            app.toggle_console()
            write_console(app, "Console output is available when expanded.\n")
            write_console(app, "Synthetic demo data only. No real student IDs are used.\n")
            settle(app)
            capture_widget(app, "gui_console.png")

            setup = gui.SetupAssistantWindow(app)
            setup.geometry("920x700+80+80")
            setup.refresh()
            settle(app)
            capture_widget(setup, "setup_assistant.png")

            review = gui.PostScoringReviewWindow(app)
            review.geometry("1250x820+120+60")
            review.provider_var.set(gui.FAKE_PROVIDER_LABEL)
            review.update_gemini_key_status()
            if review.visible_cases:
                review.show_case(review.visible_cases[0], show_notes=True)
            settle(app)
            capture_widget(review, "post_scoring_review.png")

            review.destroy()
            setup.destroy()
            app.shutdown_for_tests()
            print(f"Saved README screenshots under {DOCS_DIR}")
            return 0
        finally:
            os.chdir(original_cwd)
            os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
            os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)


def create_sample_project() -> None:
    for question in ["Q1", "Q2"]:
        Path(question, "C").mkdir(parents=True, exist_ok=True)
        Path(question, "grade").mkdir(parents=True, exist_ok=True)
        Path(question, "output").mkdir(parents=True, exist_ok=True)
        Path(question, "input.txt").write_text("0\n1\n2\n", encoding="utf-8")
        Path(question, "original_sol.c").write_text("int main(){return 0;}\n", encoding="utf-8")

    with zipfile.ZipFile("submissions.zip", "w") as submissions_zip:
        submissions_zip.writestr("Example_demo_student/hw1_q1.c", "int main(){return 0;}\n")

    long_note = (
        "Failed Test Cases: Q1: 0, 1, 2. Penalty: Files were submitted in a nested subfolder and one archive "
        "needed manual review. This deliberately long note verifies that the review table preview wraps and the "
        "full note remains readable in the selected-row Notes tab."
    )
    Path("Q1", "C", f"{DEMO_STUDENT_ID}.c").write_text(
        '#include <stdio.h>\nint main(){printf("bad");return 0;}\n',
        encoding="utf-8",
    )
    Path("Q1", "grade", f"{DEMO_STUDENT_ID}.txt").write_text(
        "Grade: 98%\n"
        "Wrong Inputs: 0\n\n"
        "Discrepancies:\n"
        "Input: 0\n"
        "Expected: 0 has no Divisors!\n"
        "Actual: bad\n"
        "Semantic Reason: zero input must explicitly state there are no divisors\n",
        encoding="utf-8",
    )
    Path("Q1", "output", f"{DEMO_STUDENT_ID}.txt").write_text("Input: 0\nOutput: bad\n", encoding="utf-8")
    Path("Q1", "original_sol_output.txt").write_text(
        "Input: 0\nOutput: 0 has no Divisors!\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "ID_number": DEMO_STUDENT_ID,
                "Grade": 98,
                "Wrong_Inputs": "0",
                "Compilation_Error": False,
                "Timeouts": "",
                "Comments": long_note,
            }
        ]
    ).to_excel(Path("Q1", "Q1_grades_to_upload.xlsx"), index=False)
    pd.DataFrame(
        [
            {
                "ID_number": DEMO_STUDENT_ID,
                "Q1": 98,
                "Q2": 100,
                "Final_Grade": 99,
                "Comments": long_note,
            }
        ]
    ).to_excel("final_grades.xlsx", index=False)


def capture_widget(widget, filename: str) -> None:
    widget.deiconify()
    widget.lift()
    widget.focus_force()
    try:
        widget.attributes("-topmost", True)
    except Exception:
        pass
    settle(widget)
    time.sleep(0.4)
    settle(widget)

    x = widget.winfo_rootx()
    y = widget.winfo_rooty()
    width = widget.winfo_width()
    height = widget.winfo_height()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(DOCS_DIR / filename)

    try:
        widget.attributes("-topmost", False)
    except Exception:
        pass


def write_console(app, text: str) -> None:
    app.log_textbox.configure(state="normal")
    app.log_textbox.insert("end", text)
    app.log_textbox.configure(state="disabled")


def settle(root) -> None:
    for _ in range(8):
        root.update_idletasks()
        root.update()


if __name__ == "__main__":
    raise SystemExit(main())
