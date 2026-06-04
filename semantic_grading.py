"""Question-specific output comparison helpers.

The student-facing assignment did not require an exact output format, so these
helpers compare the semantic answer for each question while staying conservative
about ambiguous output.
"""

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Any, Callable


@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    reason: str
    expected_canonical: Any = None
    actual_canonical: Any = None


def compare_output(question_name: str, input_value: str, expected_output: str, actual_output: str) -> ComparisonResult:
    """Compare one test case output for a question."""
    expected_clean = _clean_output(expected_output)
    actual_clean = _clean_output(actual_output)
    if actual_clean == expected_clean:
        return ComparisonResult(True, "exact output match", expected_clean, actual_clean)

    if _is_non_answer_output(actual_clean):
        return ComparisonResult(False, "runtime, timeout, or empty output", expected_clean, actual_clean)

    checker = _CHECKERS.get((question_name or "").upper())
    if checker is None:
        return ComparisonResult(False, "no semantic checker for question", expected_clean, actual_clean)

    try:
        numeric_input = int(str(input_value).strip())
    except ValueError:
        return ComparisonResult(False, "input is not an integer", expected_clean, actual_clean)

    return checker(numeric_input, actual_clean)


def _clean_output(output: str) -> str:
    return " ".join(str(output).replace("\r\n", "\n").replace("\r", "\n").split())


def _is_non_answer_output(output: str) -> bool:
    if not output:
        return True
    lowered = output.lower()
    return lowered == "timeout" or lowered.startswith("runtime error:") or lowered.startswith("error:")


def _extract_ints(output: str) -> list[int]:
    return [int(match) for match in re.findall(r"-?\d+", output)]


@lru_cache(maxsize=None)
def _divisors(number: int) -> tuple[int, ...]:
    if number <= 0:
        return ()
    return tuple(candidate for candidate in range(1, number + 1) if number % candidate == 0)


def _compare_q1(input_number: int, actual_output: str) -> ComparisonResult:
    expected = _divisors(input_number)

    if input_number == 0:
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

    if any(number != input_number for number in prefix_numbers):
        return ComparisonResult(False, "extra numeric output is not only the prompted input", expected, actual_numbers)

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


def _compare_q2(input_number: int, actual_output: str) -> ComparisonResult:
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


_CHECKERS: dict[str, Callable[[int, str], ComparisonResult]] = {
    "Q1": _compare_q1,
    "Q2": _compare_q2,
}
