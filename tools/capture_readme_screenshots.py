"""Capture README screenshots from a synthetic public fixture."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

from gui_screenshot_fixture import create_sample_project, capture_widget, settle, write_console


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"


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
            capture_widget(app, DOCS_DIR, "gui.png")

            app.workspace_tabs.set("Scoring Options")
            settle(app)
            capture_widget(app, DOCS_DIR, "gui_scoring_options.png")

            app.workspace_tabs.set("Maintenance")
            settle(app)
            capture_widget(app, DOCS_DIR, "gui_maintenance.png")

            app.workspace_tabs.set("Run")
            app.toggle_console()
            write_console(app, "Console output is available when expanded.\n")
            write_console(app, "Synthetic demo data only. No real student IDs are used.\n")
            settle(app)
            capture_widget(app, DOCS_DIR, "gui_console.png")

            setup = gui.SetupAssistantWindow(app)
            setup.geometry("920x700+80+80")
            setup.refresh()
            settle(app)
            capture_widget(setup, DOCS_DIR, "setup_assistant.png")

            checker = gui.CheckerManagerWindow(app)
            checker.geometry("1100x780+100+50")
            checker.provider_var.set(gui.FAKE_PROVIDER_LABEL)
            checker.update_gemini_key_status()
            settle(app)
            capture_widget(checker, DOCS_DIR, "checker_manager.png")

            review = gui.PostScoringReviewWindow(app)
            review.geometry("1250x820+120+60")
            review.provider_var.set(gui.FAKE_PROVIDER_LABEL)
            review.update_gemini_key_status()
            if review.visible_cases:
                review.show_case(review.visible_cases[0], show_notes=True)
            settle(app)
            capture_widget(review, DOCS_DIR, "post_scoring_review.png")

            review.destroy()
            checker.destroy()
            setup.destroy()
            app.shutdown_for_tests()
            print(f"Saved README screenshots under {DOCS_DIR}")
            return 0
        finally:
            os.chdir(original_cwd)
            os.environ.pop("C_TESTER_SKIP_STARTUP_VALIDATION", None)
            os.environ.pop("C_TESTER_SUPPRESS_TK_BGERRORS", None)

if __name__ == "__main__":
    raise SystemExit(main())
