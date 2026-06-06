"""Configurable output comparison helpers."""

from dataclasses import dataclass
from functools import lru_cache
import json
import os
import re
from typing import Any


@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    reason: str
    expected_canonical: Any = None
    actual_canonical: Any = None


DEFAULT_CHECKER_CONFIG_PATH = "checker_config.json"

CHECKER_TEMPLATES = {
    "exact": {
        "description": "Compare stdout exactly after whitespace normalization.",
        "config_schema": {},
    },
    "normalized_text": {
        "description": "Compare text after optional case and punctuation normalization.",
        "config_schema": {
            "ignore_case": {"type": "boolean", "default": True},
            "ignore_punctuation": {"type": "boolean", "default": True},
        },
    },
    "last_integer": {
        "description": "Compare the last integer printed by the program.",
        "config_schema": {},
    },
    "integer_list": {
        "description": "Compare an ordered or unordered list of integers extracted from output.",
        "config_schema": {
            "order_matters": {"type": "boolean", "default": True},
            "allow_prompt_numbers": {"type": "boolean", "default": True},
        },
    },
    "divisors": {
        "description": "Compare output to the full divisor list of the integer input.",
        "config_schema": {
            "allow_prompt_numbers": {"type": "boolean", "default": True},
            "zero_requires_no_divisors_message": {"type": "boolean", "default": True},
        },
    },
    "reverse_integer": {
        "description": "Compare output to the integer input reversed like the reference C solution.",
        "config_schema": {
            "answer_position": {"type": "enum", "values": ["last_integer"], "default": "last_integer"},
        },
    },
}

DEFAULT_CHECKER_CONFIG = {
    "questions": {
        "Q1": {
            "checker": "divisors",
            "config": {
                "allow_prompt_numbers": True,
                "zero_requires_no_divisors_message": True,
            },
        },
        "Q2": {
            "checker": "reverse_integer",
            "config": {
                "answer_position": "last_integer",
            },
        },
    }
}


def compare_output(question_name: str, input_value: str, expected_output: str, actual_output: str) -> ComparisonResult:
    """Compare one test case output for a question."""
    return compare_output_with_config(
        get_question_checker_config(question_name),
        input_value,
        expected_output,
        actual_output,
    )


def compare_output_with_config(checker_config: dict, input_value: str, expected_output: str, actual_output: str) -> ComparisonResult:
    """Compare one test case output using a saved checker configuration."""
    expected_clean = _clean_output(expected_output)
    actual_clean = _clean_output(actual_output)

    if _is_non_answer_output(actual_clean):
        return ComparisonResult(False, "runtime, timeout, or empty output", expected_clean, actual_clean)

    checker_name = (checker_config or {}).get("checker", "exact")
    config = (checker_config or {}).get("config", {})

    if checker_name == "exact":
        return _compare_exact(expected_clean, actual_clean)
    if checker_name == "normalized_text":
        return _compare_normalized_text(expected_clean, actual_clean, config)
    if checker_name == "last_integer":
        return _compare_last_integer(expected_clean, actual_clean)
    if checker_name == "integer_list":
        return _compare_integer_list(expected_clean, actual_clean, config)

    numeric_input = _parse_integer_input(input_value)
    if numeric_input is None:
        return ComparisonResult(False, "input is not an integer", expected_clean, actual_clean)

    if checker_name == "divisors":
        return _compare_divisors(numeric_input, actual_clean, config)
    if checker_name == "reverse_integer":
        return _compare_reverse_integer(numeric_input, actual_clean)

    return ComparisonResult(False, f"unknown checker '{checker_name}'", expected_clean, actual_clean)


def get_question_checker_config(question_name: str, config_path: str = DEFAULT_CHECKER_CONFIG_PATH) -> dict:
    all_config = load_checker_config(config_path)
    questions = all_config.get("questions", {})
    return questions.get((question_name or "").upper(), {"checker": "exact", "config": {}})


def load_checker_config(config_path: str = DEFAULT_CHECKER_CONFIG_PATH) -> dict:
    if not os.path.exists(config_path):
        return DEFAULT_CHECKER_CONFIG.copy()
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            loaded = json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CHECKER_CONFIG.copy()
    if not isinstance(loaded, dict):
        return DEFAULT_CHECKER_CONFIG.copy()
    loaded.setdefault("questions", {})
    return loaded


def save_checker_config(config: dict, config_path: str = DEFAULT_CHECKER_CONFIG_PATH):
    with open(config_path, "w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2, sort_keys=True)


def available_checker_templates() -> dict:
    return CHECKER_TEMPLATES.copy()


def _clean_output(output: str) -> str:
    return " ".join(str(output).replace("\r\n", "\n").replace("\r", "\n").split())


def _is_non_answer_output(output: str) -> bool:
    if not output:
        return True
    lowered = output.lower()
    return lowered == "timeout" or lowered.startswith("runtime error:") or lowered.startswith("error:")


def _extract_ints(output: str) -> list[int]:
    return [int(match) for match in re.findall(r"-?\d+", output)]


def _parse_integer_input(input_value: str) -> int | None:
    try:
        return int(str(input_value).strip())
    except ValueError:
        return None


def _compare_exact(expected_output: str, actual_output: str) -> ComparisonResult:
    return ComparisonResult(
        expected_output == actual_output,
        "exact output match" if expected_output == actual_output else "exact output mismatch",
        expected_output,
        actual_output,
    )


def _normalize_text(text: str, config: dict) -> str:
    normalized = text.lower() if config.get("ignore_case", True) else text
    if config.get("ignore_punctuation", True):
        normalized = re.sub(r"[^\w\s-]", " ", normalized)
    return " ".join(normalized.split())


def _compare_normalized_text(expected_output: str, actual_output: str, config: dict) -> ComparisonResult:
    expected = _normalize_text(expected_output, config)
    actual = _normalize_text(actual_output, config)
    return ComparisonResult(
        expected == actual,
        "normalized text matches" if expected == actual else "normalized text mismatch",
        expected,
        actual,
    )


def _compare_last_integer(expected_output: str, actual_output: str) -> ComparisonResult:
    expected_numbers = _extract_ints(expected_output)
    actual_numbers = _extract_ints(actual_output)
    if not expected_numbers:
        return ComparisonResult(False, "expected output has no integer answer", expected_numbers, actual_numbers)
    if not actual_numbers:
        return ComparisonResult(False, "actual output has no integer answer", expected_numbers[-1], actual_numbers)
    expected = expected_numbers[-1]
    actual = actual_numbers[-1]
    return ComparisonResult(
        expected == actual,
        "last printed integer matches" if expected == actual else "last printed integer mismatch",
        expected,
        actual,
    )


def _compare_integer_list(expected_output: str, actual_output: str, config: dict) -> ComparisonResult:
    expected = _extract_ints(expected_output)
    actual_numbers = _extract_ints(actual_output)
    if not expected:
        return ComparisonResult(False, "expected output has no integer list", expected, actual_numbers)
    if len(actual_numbers) < len(expected):
        return ComparisonResult(False, "not enough integers in actual output", expected, actual_numbers)

    allow_prompt_numbers = config.get("allow_prompt_numbers", True)
    actual = actual_numbers[-len(expected):] if allow_prompt_numbers else actual_numbers
    if config.get("order_matters", True):
        passed = actual == expected
    else:
        passed = sorted(actual) == sorted(expected)
    return ComparisonResult(
        passed,
        "integer list matches" if passed else "integer list mismatch",
        expected,
        actual,
    )


@lru_cache(maxsize=None)
def _divisors(number: int) -> tuple[int, ...]:
    if number <= 0:
        return ()
    return tuple(candidate for candidate in range(1, number + 1) if number % candidate == 0)


def _compare_divisors(input_number: int, actual_output: str, config: dict) -> ComparisonResult:
    expected = _divisors(input_number)

    if input_number == 0:
        if not config.get("zero_requires_no_divisors_message", True):
            actual_numbers = _extract_ints(actual_output)
            return ComparisonResult(not actual_numbers or actual_numbers == [0], "zero divisor fallback", "no divisors", actual_numbers)
        lowered = actual_output.lower()
        passed = "no" in lowered and "divis" in lowered
        return ComparisonResult(
            passed,
            "zero input must explicitly state that there are no divisors",
            "no divisors",
            actual_output,
        )

    actual_numbers = _extract_ints(actual_output)
    if len(actual_numbers) < len(expected):
        return ComparisonResult(False, "not enough numbers for full divisor list", expected, actual_numbers)

    actual_answer = tuple(actual_numbers[-len(expected):])
    prefix_numbers = actual_numbers[:-len(expected)]
    if actual_answer != expected:
        return ComparisonResult(False, "divisor list does not match expected answer", expected, actual_answer)

    if config.get("allow_prompt_numbers", True) and any(number != input_number for number in prefix_numbers):
        return ComparisonResult(False, "extra numeric output is not only the prompted input", expected, actual_numbers)
    if not config.get("allow_prompt_numbers", True) and prefix_numbers:
        return ComparisonResult(False, "extra numeric output before answer", expected, actual_numbers)

    return ComparisonResult(True, "divisor list matches", expected, actual_answer)


def _reverse_like_reference(input_number: int) -> int:
    if input_number <= 0:
        return 0
    reversed_number = 0
    remaining = input_number
    while remaining > 0:
        reversed_number = (reversed_number * 10) + (remaining % 10)
        remaining //= 10
    return reversed_number


def _compare_reverse_integer(input_number: int, actual_output: str) -> ComparisonResult:
    expected = _reverse_like_reference(input_number)
    actual_numbers = _extract_ints(actual_output)
    if not actual_numbers:
        return ComparisonResult(False, "no numeric answer found", expected, actual_numbers)

    actual_answer = actual_numbers[-1]
    return ComparisonResult(
        actual_answer == expected,
        "last printed integer is the reversed number" if actual_answer == expected else "last printed integer is not the reversed number",
        expected,
        actual_answer,
    )
