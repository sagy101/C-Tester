"""Shared synthetic GUI screenshot fixtures and capture helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
import zipfile

import pandas as pd
from PIL import ImageChops, ImageGrab, ImageStat, Image


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_STUDENT_ID = "demo_student_001"


def create_sample_project(row_count: int = 36) -> None:
    for question in ["Q1", "Q2"]:
        Path(question, "C").mkdir(parents=True, exist_ok=True)
        Path(question, "grade").mkdir(parents=True, exist_ok=True)
        Path(question, "output").mkdir(parents=True, exist_ok=True)
        Path(question, "input.txt").write_text("0\n1\n2\n", encoding="utf-8")
        Path(question, "original_sol.c").write_text("int main(){return 0;}\n", encoding="utf-8")
        Path(question, "original_sol_output.txt").write_text(
            "Input: 0\nOutput: 0 has no Divisors!\nInput: 1\nOutput: 1 has no Divisors!\n",
            encoding="utf-8",
        )

    with zipfile.ZipFile("submissions.zip", "w") as submissions_zip:
        submissions_zip.writestr("Example_demo_student/hw1_q1.c", "int main(){return 0;}\n")

    q1_rows = []
    q2_rows = []
    final_rows = []
    for index in range(row_count):
        student_id = f"demo_student_{index + 1:03d}"
        q1_grade = 100 if index % 6 == 0 else 98 - (index % 5)
        q2_grade = 100 if index % 5 == 0 else 96 - (index % 7)
        note = (
            f"Failed Test Cases: Q1: 0, 1. Demo row {index + 1} has a long note that verifies "
            "single-line previews, filtered search results, and selected-row detail rendering."
        )
        _write_student_artifacts("Q1", student_id, "bad", q1_grade, note)
        _write_student_artifacts("Q2", student_id, "24", q2_grade, note)
        q1_rows.append(_question_row(student_id, q1_grade, note, repaired=index == 2))
        q2_rows.append(_question_row(student_id, q2_grade, note, repaired=index == 3))
        final_rows.append(
            {
                "ID_number": student_id,
                "Q1": q1_grade,
                "Q2": q2_grade,
                "Final_Grade": round((q1_grade + q2_grade) / 2, 2),
                "Comments": note,
            }
        )
    pd.DataFrame(q1_rows).to_excel(Path("Q1", "Q1_grades_to_upload.xlsx"), index=False)
    pd.DataFrame(q2_rows).to_excel(Path("Q2", "Q2_grades_to_upload.xlsx"), index=False)
    pd.DataFrame(final_rows).to_excel("final_grades.xlsx", index=False)
    _write_review_json("Q1", "demo_student_004")
    _write_repair_report("Q1", "demo_student_003")
    _write_repair_report("Q2", "demo_student_004")
    _write_checker_config()


def _write_student_artifacts(question: str, student_id: str, output: str, grade: float, note: str) -> None:
    Path(question, "C", f"{student_id}.c").write_text(
        f'#include <stdio.h>\nint main(){{printf("{output}");return 0;}}\n',
        encoding="utf-8",
    )
    Path(question, "grade", f"{student_id}.txt").write_text(
        f"Grade: {grade}%\n"
        "Wrong Inputs: 0, 1\n\n"
        "Discrepancies:\n"
        "Input: 0\n"
        "Expected: 0 has no Divisors!\n"
        f"Actual: {output}\n"
        "Semantic Reason: zero input must explicitly state there are no divisors\n",
        encoding="utf-8",
    )
    Path(question, "output", f"{student_id}.txt").write_text(f"Input: 0\nOutput: {output}\n", encoding="utf-8")


def _question_row(student_id: str, grade: float, note: str, repaired: bool = False) -> dict:
    row = {
        "ID_number": student_id,
        "Grade": grade,
        "Wrong_Inputs": "0, 1",
        "Compilation_Error": False,
        "Timeouts": "",
        "Comments": note,
    }
    if repaired:
        row.update(
            {
                "Compilation_Repair_Status": "fixed",
                "Compilation_Repair_Attempts": 1,
                "Compilation_Repair_Penalty": 15,
                "Compilation_Repair_Note": "added missing semicolon without changing logic",
            }
        )
    return row


def _write_review_json(question: str, student_id: str) -> None:
    review_dir = Path(question, "review")
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / f"{student_id}.json").write_text(
        json.dumps(
            {
                "student_id": student_id,
                "anonymized_label": "student_004",
                "question": question,
                "question_score": 95,
                "final_grade": 96,
                "response": {
                    "summary": "Reviewed demo row.",
                    "deduction_is_plausible": True,
                    "root_causes": [],
                    "inline_comments": [],
                    "fix_to_full_score": "Match the expected text.",
                    "risk_note": "",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_repair_report(question: str, student_id: str) -> None:
    repair_dir = Path(question, "llm_fixed", student_id)
    repair_dir.mkdir(parents=True, exist_ok=True)
    fixed_path = repair_dir / "attempt_1.c"
    fixed_path.write_text("int main(){return 0;}\n", encoding="utf-8")
    (repair_dir / "repair_report.json").write_text(
        json.dumps(
            {
                "status": "fixed",
                "attempts": 1,
                "fixed_code_path": str(fixed_path),
                "repair_note": "added missing semicolon without changing logic",
                "repair_penalty": 15,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_checker_config() -> None:
    Path("checker_config.json").write_text(
        json.dumps(
            {
                "questions": {
                    "Q1": {
                        "checker": "divisors",
                        "config": {"allow_prompt_numbers": True, "zero_requires_no_divisors_message": True},
                        "metadata": {"saved": True, "test_status": "passed", "audit_status": "passed"},
                    },
                    "Q2": {
                        "checker": "reverse_integer",
                        "config": {"answer_position": "last_integer"},
                        "metadata": {"saved": True, "test_status": "passed", "audit_status": "skipped"},
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def capture_widget(widget, output_dir: Path, filename: str) -> None:
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
    output_dir.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(output_dir / filename)
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


def compare_image_dirs(before_dir: Path, after_dir: Path, manifest_path: Path) -> list[dict]:
    results = []
    for after_path in sorted(after_dir.glob("*.png")):
        before_path = before_dir / after_path.name
        if not before_path.exists():
            results.append({"file": after_path.name, "status": "new"})
            continue
        result = compare_images(before_path, after_path)
        result["file"] = after_path.name
        results.append(result)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def compare_images(before_path: Path, after_path: Path) -> dict:
    before_hash = sha256_file(before_path)
    after_hash = sha256_file(after_path)
    result = {
        "status": "identical" if before_hash == after_hash else "changed",
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "before_size": before_path.stat().st_size,
        "after_size": after_path.stat().st_size,
    }
    if before_hash == after_hash:
        result["pixel_difference_percent"] = 0.0
        return result
    with Image.open(before_path) as before_image, Image.open(after_path) as after_image:
        result["before_dimensions"] = before_image.size
        result["after_dimensions"] = after_image.size
        if before_image.size != after_image.size:
            result["pixel_difference_percent"] = 100.0
            return result
        diff = ImageChops.difference(before_image.convert("RGB"), after_image.convert("RGB"))
        stat = ImageStat.Stat(diff)
        changed = sum(1 for pixel in diff.getdata() if pixel != (0, 0, 0))
        total = before_image.size[0] * before_image.size[1]
        result["pixel_difference_percent"] = round((changed / total) * 100, 4)
        result["mean_channel_delta"] = [round(value, 4) for value in stat.mean]
        return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
