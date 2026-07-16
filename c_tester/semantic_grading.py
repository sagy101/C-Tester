"""Configurable output comparison helpers."""

from dataclasses import dataclass
import json
import os
import re
from typing import Any

from .output_contract import ContractConfigError, compile_preset, evaluate_contract, validate_contract


@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    reason: str
    expected_canonical: Any = None
    actual_canonical: Any = None


DEFAULT_CHECKER_CONFIG_PATH = "checker_config.json"

CHECKER_TEMPLATES = {
    "exact": {
        "description": "Generic preset: compare complete stdout after whitespace normalization.",
        "config_schema": {},
    },
    "normalized_text": {
        "description": "Generic preset: compare normalized complete text.",
        "config_schema": {
            "ignore_case": {"type": "boolean", "default": True},
            "ignore_punctuation": {"type": "boolean", "default": True},
        },
    },
    "last_integer": {
        "description": "Generic preset: compare the final integer in reference and actual output.",
        "config_schema": {},
    },
    "integer_list": {
        "description": "Generic preset: compare ordered or unordered integer sequences.",
        "config_schema": {
            "order_matters": {"type": "boolean", "default": True},
            "allow_prompt_numbers": {"type": "boolean", "default": True},
        },
    },
    "divisors": {
        "description": "Legacy alias migrated to the generic reference integer-sequence contract.",
        "config_schema": {
            "allow_prompt_numbers": {"type": "boolean", "default": True},
            "zero_requires_no_divisors_message": {"type": "boolean", "default": True},
            "input_integer_index": {
                "type": "integer",
                "default": -1,
                "description": "Which integer from stdin is the task argument; -1 means last integer.",
            },
        },
    },
    "reverse_integer": {
        "description": "Legacy alias migrated to the generic final-integer contract.",
        "config_schema": {
            "answer_position": {"type": "enum", "values": ["last_integer"], "default": "last_integer"},
            "input_integer_index": {
                "type": "integer",
                "default": -1,
                "description": "Which integer from stdin is the task argument; -1 means last integer.",
            },
        },
    },
    "output_contract": {
        "description": (
            "Generic declarative contract using safe sources, extractors, aliases, tolerances, "
            "and cross-field assertions. No generated code or user regular expressions."
        ),
        "config_schema": {"contract": {"type": "output_contract_v1", "required": True}},
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
    if not isinstance(checker_config, dict):
        return ComparisonResult(
            False,
            "checker configuration must be a JSON object",
            _clean_output(expected_output),
            _clean_output(actual_output),
        )
    checker_name = (checker_config or {}).get("checker", "exact")
    config = (checker_config or {}).get("config", {})
    try:
        contract = compile_preset(checker_name, config)
    except ContractConfigError as exc:
        return ComparisonResult(False, str(exc), _clean_output(expected_output), _clean_output(actual_output))
    result = evaluate_contract(contract, input_value, expected_output, actual_output)
    return ComparisonResult(result.passed, result.reason, result.expected_canonical, result.actual_canonical)


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


def checker_config_errors(checker_config: dict) -> list[str]:
    if not isinstance(checker_config, dict):
        return ["checker configuration must be a JSON object"]
    checker_name = checker_config.get("checker", "exact")
    if checker_name not in CHECKER_TEMPLATES:
        return [f"unknown checker '{checker_name}'"]
    try:
        contract = compile_preset(checker_name, checker_config.get("config", {}))
    except ContractConfigError as exc:
        return [str(exc)]
    return validate_contract(contract)


def _clean_output(output: str) -> str:
    return " ".join(str(output).replace("\r\n", "\n").replace("\r", "\n").split())
