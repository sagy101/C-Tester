"""Opt-in real GUI smoke test for Checker Manager workflows."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true", help="Run the full Gemini one-click calibration flow.")
    parser.add_argument("--audit-size", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.calibrate and os.getenv("C_TESTER_RUN_GUI_INTEGRATION") != "1":
        raise SystemExit("Set C_TESTER_RUN_GUI_INTEGRATION=1 to run real Gemini/grading integration.")

    sys.path.insert(0, str(REPO_ROOT))
    os.environ["C_TESTER_SKIP_STARTUP_VALIDATION"] = "1"
    os.environ["C_TESTER_SUPPRESS_TK_BGERRORS"] = "1"

    from c_tester import gui

    app = gui.App()
    checker = gui.CheckerManagerWindow(app)
    checker.audit_size_var.set(str(max(1, args.audit_size)))
    started = time.monotonic()
    last_progress = ""
    try:
        if args.calibrate:
            checker.provider_var.set("Gemini")
            state = {"started": False, "timed_out": False}

            def poll():
                state["started"] = state["started"] or checker._background_running
                progress = str(checker.calibration_progress_label.cget("text"))
                nonlocal last_progress
                if progress != last_progress:
                    print(progress, flush=True)
                    last_progress = progress
                if state["started"] and not checker._background_running:
                    app.quit()
                    return
                if time.monotonic() - started > args.timeout:
                    state["timed_out"] = True
                    app.quit()
                    return
                app.after(100, poll)

            app.after(100, checker.auto_setup_current_question)
            app.after(200, poll)
            app.mainloop()
            if state["timed_out"]:
                raise TimeoutError("Checker Manager calibration smoke test timed out.")
            app.update_idletasks()
        else:
            checker.config_textbox.delete("1.0", "end")
            checker.config_textbox.insert("1.0", json.dumps({"checker": "exact", "config": {}}))
            state = {"started": False, "timed_out": False}

            def poll_test():
                state["started"] = state["started"] or checker._background_running
                if state["started"] and not checker._background_running:
                    app.quit()
                    return
                if time.monotonic() - started > args.timeout:
                    state["timed_out"] = True
                    app.quit()
                    return
                app.after(50, poll_test)

            app.after(100, checker.test_checker)
            app.after(150, poll_test)
            app.mainloop()
            if state["timed_out"]:
                raise TimeoutError("Checker Manager Test Draft smoke test timed out.")
            app.update_idletasks()

        status_text = str(checker.status_label.cget("text"))
        row_count = max(0, checker.test_row_index - 1)
        print(f"status={status_text}")
        print(f"tab={checker.tabview.get()}")
        print(f"test_rows={row_count}")
        print(f"progress={checker.calibration_progress_label.cget('text')}")
        response_text = checker.response_textbox.get("1.0", "end").strip()
        saved_results = []
        if response_text:
            try:
                payload = json.loads(response_text)
                question_results = payload.get("question_results", [])
                for result in question_results:
                    saved_results.append(bool(result.get("saved")))
                    print(f"saved={result.get('saved')} tests_ok={result.get('tests_ok')}")
                    for warning in result.get("warnings", [])[:12]:
                        print(f"warning={warning}")
            except json.JSONDecodeError:
                print(f"response={response_text[:1000]}")
        if row_count == 0:
            print("ERROR: no Test Results rows were rendered.")
            return 1
        if args.calibrate and (not saved_results or not all(saved_results)):
            print("ERROR: one-click calibration did not save every requested checker.")
            return 1
        if not args.calibrate and "passed" not in status_text.lower():
            print("ERROR: Test Draft did not report success.")
            return 1
        return 0
    finally:
        checker.destroy()
        app.shutdown_for_tests()


if __name__ == "__main__":
    raise SystemExit(main())
