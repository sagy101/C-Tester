"""Read-only Git privacy audit for grader repositories."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys


PRIVATE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"\.xlsx$",
        r"\.zip$",
        r"\.rar$",
        r"\.pdf$",
        r"^Q\d+/C/\d{9}\.c$",
        r"^Q\d+/input\.txt$",
        r"^Q\d+/original_sol\.c$",
        r"^Q\d+/original_sol_output\.txt$",
        r"(^|/)llm_fixed(/|$)",
        r"(^|/)llm_fixed_output(/|$)",
        r"(^|/)review(/|$)",
        r"(^|/)submit_error\.txt$",
        r"(^|/)repair_report\.json$",
        r"grades_to_upload",
        r"final_grades",
    ]
]


def run_git(args: list[str]) -> list[str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_allowed_public_example(path: str) -> bool:
    return path.startswith("examples/")


def private_matches(paths: list[str]) -> list[str]:
    matches = []
    for path in paths:
        object_path = path.split(" ", 1)[-1]
        if is_allowed_public_example(object_path):
            continue
        if any(pattern.search(object_path) for pattern in PRIVATE_PATTERNS):
            matches.append(path)
    return matches


def audit_tip(ref: str) -> list[str]:
    return private_matches(run_git(["ls-tree", "-r", "--name-only", ref]))


def audit_history(ref: str) -> list[str]:
    return private_matches(run_git(["rev-list", "--objects", ref]))


def audit_staged() -> list[str]:
    return private_matches(run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMRT"]))


def describe_scope(args: argparse.Namespace) -> tuple[str, str]:
    if args.staged:
        return "staged files", ""
    if args.history:
        return "history", f" in {args.ref}"
    return "tip", f" for {args.ref}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Git refs for private grader artifacts.")
    parser.add_argument("ref", nargs="?", default="HEAD", help="Git ref to audit, e.g. HEAD or origin/master.")
    parser.add_argument("--history", action="store_true", help="Scan all reachable history, not just the tip tree.")
    parser.add_argument("--staged", action="store_true", help="Scan staged paths for pre-commit use.")
    args = parser.parse_args()

    if args.staged:
        matches = audit_staged()
    else:
        matches = audit_history(args.ref) if args.history else audit_tip(args.ref)

    scope, target = describe_scope(args)
    if matches:
        print(f"Private-pattern matches found{target} {scope}:")
        for match in matches:
            print(match)
        return 1

    print(f"Privacy audit OK{target} {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
