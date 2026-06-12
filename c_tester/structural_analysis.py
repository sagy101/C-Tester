"""Deterministic structural checks for C homework submissions."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any


CONTROL_WORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
}


@dataclass(frozen=True)
class StructuralCheckResult:
    checked: bool
    passed: bool
    penalty: float = 0
    reason: str = ""


def analyze_source_file(path: str, question_name: str, checker_config: dict | None) -> StructuralCheckResult:
    requirements = (checker_config or {}).get("structural_requirements")
    if not isinstance(requirements, dict) or not _is_enabled(requirements):
        return StructuralCheckResult(False, True)

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as source_file:
            source_code = source_file.read()
    except OSError as exc:
        return StructuralCheckResult(True, False, _deduction(requirements), f"Could not read source file: {exc}")

    normalized_requirements = dict(requirements)
    normalized_requirements.setdefault("entry_functions", [_default_entry_function(question_name)])
    return analyze_structural_requirements(source_code, normalized_requirements)


def structural_requirements_errors(question_config: dict | None) -> list[str]:
    requirements = (question_config or {}).get("structural_requirements")
    if not isinstance(requirements, dict) or not _is_enabled(requirements):
        return []

    errors = []
    if not _has_numeric_deduction(requirements):
        errors.append(
            "Structural recursion/loop checking is enabled, but 'structural_requirements.deduction' "
            "is missing or not numeric. Fill this mandatory deduction before saving."
        )
    if requirements.get("requires_recursion") and not requirements.get("entry_functions"):
        errors.append("Structural recursion checking requires 'structural_requirements.entry_functions'.")
    return errors


def analyze_structural_requirements(source_code: str, requirements: dict[str, Any]) -> StructuralCheckResult:
    if not _is_enabled(requirements):
        return StructuralCheckResult(False, True)

    deduction = _deduction(requirements)
    cleaned_source = strip_comments_and_literals(source_code)
    functions = extract_functions(cleaned_source)
    call_graph = build_call_graph(functions)

    entry_functions = [str(name) for name in requirements.get("entry_functions") or [] if str(name).strip()]
    if not entry_functions:
        entry_functions = ["main"]

    failures = []
    reachable = set()
    for entry_function in entry_functions:
        if entry_function not in functions:
            failures.append(
                f"Non-recursive solution check failed: entry function '{entry_function}' was not found."
            )
            continue
        entry_reachable = reachable_functions(call_graph, entry_function)
        reachable.update(entry_reachable)
        if requirements.get("requires_recursion", False) and not _has_required_recursion(
            call_graph,
            entry_function,
            entry_reachable,
            bool(requirements.get("allow_recursive_helpers", True)),
        ):
            failures.append(
                f"Non-recursive solution check failed: no required recursive call was found from '{entry_function}'."
            )

    if requirements.get("forbid_loops", False):
        loop_functions = sorted(name for name in reachable if function_has_loop(functions.get(name, "")))
        if loop_functions:
            failures.append(
                "Non-recursive solution check failed: forbidden loop statement found in "
                f"{', '.join(loop_functions)}."
            )

    if failures:
        return StructuralCheckResult(True, False, deduction, " ".join(failures))
    return StructuralCheckResult(True, True, 0, "Structural requirements satisfied.")


def strip_comments_and_literals(source_code: str) -> str:
    source_code = re.sub(r"/\*.*?\*/", " ", source_code, flags=re.DOTALL)
    source_code = re.sub(r"//.*", " ", source_code)
    source_code = re.sub(r'"(?:\\.|[^"\\])*"', '""', source_code)
    source_code = re.sub(r"'(?:\\.|[^'\\])*'", "''", source_code)
    return source_code


def extract_functions(source_code: str) -> dict[str, str]:
    functions = {}
    pattern = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*\([^;{}()]*\)\s*\{")
    for match in pattern.finditer(source_code):
        name = match.group("name")
        if name in CONTROL_WORDS:
            continue
        body_start = match.end() - 1
        body_end = find_matching_brace(source_code, body_start)
        if body_end == -1:
            continue
        functions[name] = source_code[body_start + 1 : body_end]
    return functions


def find_matching_brace(source_code: str, open_brace_index: int) -> int:
    depth = 0
    for index in range(open_brace_index, len(source_code)):
        if source_code[index] == "{":
            depth += 1
        elif source_code[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def build_call_graph(functions: dict[str, str]) -> dict[str, set[str]]:
    function_names = set(functions)
    graph = {}
    for name, body in functions.items():
        calls = {
            candidate
            for candidate in re.findall(r"\b([A-Za-z_]\w*)\s*\(", body)
            if candidate in function_names and candidate not in CONTROL_WORDS
        }
        graph[name] = calls
    return graph


def reachable_functions(call_graph: dict[str, set[str]], entry_function: str) -> set[str]:
    seen = set()
    stack = [entry_function]
    while stack:
        function = stack.pop()
        if function in seen:
            continue
        seen.add(function)
        stack.extend(call_graph.get(function, set()) - seen)
    return seen


def function_has_loop(body: str) -> bool:
    return bool(re.search(r"\b(for|while)\s*\(", body) or re.search(r"\bdo\b", body))


def _has_required_recursion(
    call_graph: dict[str, set[str]],
    entry_function: str,
    entry_reachable: set[str],
    allow_recursive_helpers: bool,
) -> bool:
    if allow_recursive_helpers:
        return any(_function_reaches_itself(call_graph, function) for function in entry_reachable)
    return _function_reaches_itself(call_graph, entry_function)


def _function_reaches_itself(call_graph: dict[str, set[str]], function: str) -> bool:
    stack = list(call_graph.get(function, set()))
    seen = set()
    while stack:
        current = stack.pop()
        if current == function:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(call_graph.get(current, set()) - seen)
    return False


def _is_enabled(requirements: dict[str, Any]) -> bool:
    return bool(requirements.get("requires_recursion") or requirements.get("forbid_loops"))


def _deduction(requirements: dict[str, Any]) -> float:
    value = requirements.get("deduction", requirements.get("penalty", 0))
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        return 0


def _has_numeric_deduction(requirements: dict[str, Any]) -> bool:
    value = requirements.get("deduction", requirements.get("penalty"))
    if value is None:
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _default_entry_function(question_name: str) -> str:
    match = re.search(r"(\d+)", question_name or "")
    if match:
        return f"q_{match.group(1)}"
    return os.path.splitext(os.path.basename(question_name or ""))[0] or "main"
