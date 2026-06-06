"""Capture real GUI layout screenshots from synthetic public fixtures."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

from gui_screenshot_fixture import create_sample_project, capture_widget, settle, write_console


REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = REPO_ROOT / "docs" / "visual_smoke"


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
            capture_widget(app, SCREENSHOT_DIR, "main.png")

            app.workspace_tabs.set("Scoring Options")
            settle(app)
            capture_widget(app, SCREENSHOT_DIR, "main_scoring_options.png")

            app.workspace_tabs.set("Maintenance")
            settle(app)
            capture_widget(app, SCREENSHOT_DIR, "main_maintenance.png")

            app.workspace_tabs.set("Run")
            app.toggle_console()
            write_console(app, "Visual smoke console output.\n")
            settle(app)
            capture_widget(app, SCREENSHOT_DIR, "main_console_expanded.png")

            setup = gui.SetupAssistantWindow(app)
            setup.geometry("920x700+80+80")
            setup.refresh()
            settle(app)
            capture_widget(setup, SCREENSHOT_DIR, "setup_assistant.png")

            checker = gui.CheckerManagerWindow(app)
            checker.geometry("1100x780+100+50")
            checker.provider_var.set(gui.FAKE_PROVIDER_LABEL)
            checker.update_gemini_key_status()
            checker.show_on_top()
            settle(checker)
            for tab_name, filename in [
                ("Configure", "checker_configure.png"),
                ("Test Results", "checker_test_results.png"),
                ("Audit", "checker_audit.png"),
                ("Prompt / Response", "checker_prompt_response.png"),
            ]:
                checker.tabview.set(tab_name)
                settle(app)
                capture_widget(checker, SCREENSHOT_DIR, filename)

            review = gui.PostScoringReviewWindow(app)
            review.geometry("1250x820+120+90")
            review.provider_var.set(gui.FAKE_PROVIDER_LABEL)
            review.update_gemini_key_status()
            if review.visible_cases:
                review.show_case(review.visible_cases[0], show_notes=True)
            settle(app)
            capture_widget(review, SCREENSHOT_DIR, "post_scoring_review.png")

            review.id_search_var.set("demo_student_036")
            settle(app)
            capture_widget(review, SCREENSHOT_DIR, "post_scoring_review_search_single.png")

            if review.review_tree.get_children():
                first = review.review_tree.get_children()[0]
                review.review_tree.selection_set(first)
                review.review_tree.focus(first)
                review.detail_tabview.set("Notes")
                settle(app)
                capture_widget(review, SCREENSHOT_DIR, "post_scoring_review_selected_notes.png")

            review.id_search_var.set("demo_student_004")
            review.detail_tabview.set("Review")
            settle(app)
            capture_widget(review, SCREENSHOT_DIR, "post_scoring_review_reviewed_row.png")

            review.destroy()
            checker.destroy()
            setup.destroy()
            app.shutdown_for_tests()
            print(f"Saved visual smoke screenshots under {SCREENSHOT_DIR}")
            return 0
        finally:
            os.chdir(original_cwd)
            os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
            os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)

if __name__ == "__main__":
    raise SystemExit(main())
