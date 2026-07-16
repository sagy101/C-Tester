"""Safe, deterministic interpreter for declarative stdout contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


CONTRACT_VERSION = 1
MAX_OUTPUT_CHARS = 65536
MAX_FIELDS = 48
MAX_CHECKS = 48
MAX_TEXT_OPTION_LENGTH = 96
MAX_WINDOW = 4096
MAX_NUMERIC_TOLERANCE = 0.011

_FLOAT_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_POINT_PATTERN = re.compile(
    rf"[\(\{{]\s*({_FLOAT_PATTERN})\s*,\s*({_FLOAT_PATTERN})\s*[\)\}}]",
    re.IGNORECASE,
)
_INTEGER_PATTERN = re.compile(r"-?\d+")
_FLOAT_RE = re.compile(_FLOAT_PATTERN)

_NORMALIZERS = {"collapse_whitespace", "lowercase", "strip_punctuation", "normalize_apostrophe"}
_EXTRACTORS = {"text", "integers", "floats", "labeled_number", "point", "points", "boolean"}
_CHECK_OPERATORS = {
    "equal",
    "approx",
    "sequence_equal",
    "tail_equal",
    "sequence_or_text_tokens",
    "exchanged",
}
_FIELD_KEYS = {
    "id",
    "source",
    "extract",
    "normalize",
    "select",
    "label",
    "number_type",
    "anchor",
    "occurrence",
    "count",
    "window",
    "true_aliases",
    "false_aliases",
    "allow_empty",
}
_CHECK_KEYS = {
    "id",
    "op",
    "left",
    "right",
    "allowed_prefix",
    "fallback",
    "required_tokens",
    "tolerance",
    "ordered",
    "message",
}
_CONTRACT_KEYS = {"version", "description", "fields", "checks"}


@dataclass(frozen=True)
class ContractResult:
    passed: bool
    reason: str
    expected_canonical: Any = None
    actual_canonical: Any = None


class ContractConfigError(ValueError):
    """Raised when a contract uses unsupported or unsafe syntax."""


class ContractExtractionError(ValueError):
    """Raised when a required field cannot be extracted."""


def validate_contract(contract: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(contract, dict):
        return ["contract must be a JSON object"]
    unknown_top = set(contract) - _CONTRACT_KEYS
    if unknown_top:
        errors.append(f"unsupported contract keys: {', '.join(sorted(unknown_top))}")
    if contract.get("version") != CONTRACT_VERSION:
        errors.append(f"contract version must be {CONTRACT_VERSION}")

    fields = contract.get("fields")
    checks = contract.get("checks")
    if not isinstance(fields, list) or not fields:
        errors.append("contract fields must be a non-empty list")
        fields = []
    if not isinstance(checks, list) or not checks:
        errors.append("contract checks must be a non-empty list")
        checks = []
    if len(fields) > MAX_FIELDS:
        errors.append(f"contract has more than {MAX_FIELDS} fields")
    if len(checks) > MAX_CHECKS:
        errors.append(f"contract has more than {MAX_CHECKS} checks")

    field_ids: set[str] = set()
    for index, field in enumerate(fields):
        prefix = f"field {index + 1}"
        if not isinstance(field, dict):
            errors.append(f"{prefix} must be an object")
            continue
        unknown = set(field) - _FIELD_KEYS
        if unknown:
            errors.append(f"{prefix} has unsupported keys: {', '.join(sorted(unknown))}")
        field_id = field.get("id")
        if not _valid_identifier(field_id):
            errors.append(f"{prefix} id must contain only letters, numbers, underscores, dots, or hyphens")
        elif field_id in field_ids:
            errors.append(f"duplicate field id '{field_id}'")
        else:
            field_ids.add(field_id)
        if field.get("source") not in {"stdin", "reference", "actual"}:
            errors.append(f"{prefix} source must be stdin, reference, or actual")
        if field.get("extract") not in _EXTRACTORS:
            errors.append(f"{prefix} uses unsupported extractor '{field.get('extract')}'")
        normalizers = field.get("normalize", [])
        if not isinstance(normalizers, list) or any(item not in _NORMALIZERS for item in normalizers):
            errors.append(f"{prefix} contains an unsupported normalizer")
        for key in ("label", "anchor"):
            value = field.get(key)
            if value is not None and (not isinstance(value, str) or not value or len(value) > MAX_TEXT_OPTION_LENGTH):
                errors.append(f"{prefix} {key} must be 1-{MAX_TEXT_OPTION_LENGTH} characters")
        window = field.get("window", MAX_WINDOW)
        if not isinstance(window, int) or not 1 <= window <= MAX_WINDOW:
            errors.append(f"{prefix} window must be between 1 and {MAX_WINDOW}")
        for alias_key in ("true_aliases", "false_aliases"):
            aliases = field.get(alias_key, [])
            if not isinstance(aliases, list) or len(aliases) > 12:
                errors.append(f"{prefix} {alias_key} must be a list with at most 12 values")
            elif any(not isinstance(alias, str) or not alias or len(alias) > MAX_TEXT_OPTION_LENGTH for alias in aliases):
                errors.append(f"{prefix} {alias_key} contains an invalid value")
        if field.get("extract") == "boolean" and (
            not field.get("true_aliases") or not field.get("false_aliases")
        ):
            errors.append(f"{prefix} boolean extraction requires true_aliases and false_aliases")
        if field.get("extract") == "labeled_number" and not (field.get("label") or field.get("anchor")):
            errors.append(f"{prefix} labeled_number extraction requires label or anchor")
        if "allow_empty" in field and not isinstance(field["allow_empty"], bool):
            errors.append(f"{prefix} allow_empty must be boolean")
        if "number_type" in field and field["number_type"] not in {"integer", "float"}:
            errors.append(f"{prefix} number_type must be integer or float")
        if "ordered" in field:
            errors.append(f"{prefix} ordered is only valid on checks")
        if "select" in field and not _valid_selector(field["select"]):
            errors.append(f"{prefix} has an invalid select value")
        occurrence = field.get("occurrence", 0)
        count = field.get("count", 1)
        if not isinstance(occurrence, int) or occurrence < 0 or occurrence > 100:
            errors.append(f"{prefix} occurrence must be an integer between 0 and 100")
        if not isinstance(count, int) or count < 1 or count > 16:
            errors.append(f"{prefix} count must be an integer between 1 and 16")

    check_ids: set[str] = set()
    for index, check in enumerate(checks):
        prefix = f"check {index + 1}"
        if not isinstance(check, dict):
            errors.append(f"{prefix} must be an object")
            continue
        unknown = set(check) - _CHECK_KEYS
        if unknown:
            errors.append(f"{prefix} has unsupported keys: {', '.join(sorted(unknown))}")
        check_id = check.get("id")
        if not _valid_identifier(check_id):
            errors.append(f"{prefix} has an invalid id")
        elif check_id in check_ids:
            errors.append(f"duplicate check id '{check_id}'")
        else:
            check_ids.add(check_id)
        if check.get("op") not in _CHECK_OPERATORS:
            errors.append(f"{prefix} uses unsupported operator '{check.get('op')}'")
        for side in ("left", "right"):
            value = check.get(side)
            if not isinstance(value, dict) or set(value) not in ({"field"}, {"literal"}):
                errors.append(f"{prefix} {side} must contain exactly one field or literal")
            elif "field" in value and value["field"] not in field_ids:
                errors.append(f"{prefix} references unknown field '{value['field']}'")
        allowed_prefix = check.get("allowed_prefix")
        if allowed_prefix is not None:
            if not isinstance(allowed_prefix, dict) or set(allowed_prefix) != {"field"}:
                errors.append(f"{prefix} allowed_prefix must contain exactly one field")
            elif allowed_prefix["field"] not in field_ids:
                errors.append(f"{prefix} references unknown allowed-prefix field '{allowed_prefix['field']}'")
        fallback = check.get("fallback")
        if fallback is not None:
            if not isinstance(fallback, dict) or set(fallback) != {"field"}:
                errors.append(f"{prefix} fallback must contain exactly one field")
            elif fallback["field"] not in field_ids:
                errors.append(f"{prefix} references unknown fallback field '{fallback['field']}'")
        required_tokens = check.get("required_tokens", [])
        if (
            not isinstance(required_tokens, list)
            or len(required_tokens) > 8
            or any(not isinstance(token, str) or not token or len(token) > 32 for token in required_tokens)
        ):
            errors.append(f"{prefix} required_tokens must contain at most 8 short strings")
        if check.get("op") == "sequence_or_text_tokens" and (not fallback or not required_tokens):
            errors.append(f"{prefix} sequence_or_text_tokens requires fallback and required_tokens")
        tolerance = check.get("tolerance", 0)
        if not isinstance(tolerance, (int, float)) or tolerance < 0 or tolerance > MAX_NUMERIC_TOLERANCE:
            errors.append(f"{prefix} tolerance must be between 0 and {MAX_NUMERIC_TOLERANCE}")
        message = check.get("message")
        if message is not None and (not isinstance(message, str) or not message or len(message) > 200):
            errors.append(f"{prefix} message must be 1-200 characters")
        if "ordered" in check and not isinstance(check["ordered"], bool):
            errors.append(f"{prefix} ordered must be boolean")
    return errors


def evaluate_contract(
    contract: dict,
    input_value: str,
    reference_output: str,
    actual_output: str,
) -> ContractResult:
    errors = validate_contract(contract)
    if errors:
        return ContractResult(False, f"invalid checker contract: {'; '.join(errors)}")

    sources = {
        "stdin": str(input_value)[:MAX_OUTPUT_CHARS],
        "reference": str(reference_output)[:MAX_OUTPUT_CHARS],
        "actual": str(actual_output)[:MAX_OUTPUT_CHARS],
    }
    actual_clean = " ".join(sources["actual"].split())
    if not actual_clean or actual_clean.lower() == "timeout" or actual_clean.lower().startswith(("runtime error:", "error:")):
        return ContractResult(False, "runtime, timeout, or empty output")

    values: dict[str, Any] = {}
    field_sources: dict[str, str] = {}
    for field in contract["fields"]:
        try:
            values[field["id"]] = _extract_field(field, sources[field["source"]])
            field_sources[field["id"]] = field["source"]
        except ContractExtractionError as exc:
            expected = {key: value for key, value in values.items() if field_sources.get(key) != "actual"}
            actual = {key: value for key, value in values.items() if field_sources.get(key) == "actual"}
            return ContractResult(False, f"field {field['id']}: {exc}", expected, actual)

    for check in contract["checks"]:
        left = _resolve_value(check["left"], values)
        right = _resolve_value(check["right"], values)
        passed, compared_left, compared_right = _apply_check(check, left, right, values)
        if not passed:
            reason = check.get("message") or f"check {check['id']} failed"
            return ContractResult(
                False,
                f"{check['id']}: {reason}",
                {"check": check["id"], "value": compared_right},
                {"check": check["id"], "value": compared_left},
            )

    expected = {key: value for key, value in values.items() if field_sources.get(key) != "actual"}
    actual = {key: value for key, value in values.items() if field_sources.get(key) == "actual"}
    return ContractResult(True, "all declarative checker assertions passed", expected, actual)


def compile_preset(checker_name: str, config: dict | None = None) -> dict:
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ContractConfigError("checker config must be a JSON object")
    if checker_name == "output_contract":
        contract = config.get("contract")
        if not isinstance(contract, dict):
            raise ContractConfigError("output_contract requires config.contract")
        return contract
    if checker_name == "exact":
        return _text_contract(["collapse_whitespace"])
    if checker_name == "normalized_text":
        normalizers = ["collapse_whitespace"]
        if config.get("ignore_case", True):
            normalizers.append("lowercase")
        if config.get("ignore_punctuation", True):
            normalizers.append("strip_punctuation")
        return _text_contract(normalizers)
    if checker_name in {"last_integer", "reverse_integer"}:
        return _last_number_contract("integer")
    if checker_name in {"integer_list", "divisors"}:
        return _number_list_contract(
            order_matters=config.get("order_matters", True),
            allow_prompt_numbers=config.get("allow_prompt_numbers", True),
            prefix_from_stdin=checker_name == "divisors",
        )
    raise ContractConfigError(f"unknown checker preset '{checker_name}'")


def _text_contract(normalizers: list[str]) -> dict:
    return {
        "version": CONTRACT_VERSION,
        "description": "Compare normalized reference and actual text.",
        "fields": [
            {"id": "expected", "source": "reference", "extract": "text", "normalize": normalizers},
            {"id": "actual", "source": "actual", "extract": "text", "normalize": normalizers},
        ],
        "checks": [
            {
                "id": "text",
                "op": "equal",
                "left": {"field": "actual"},
                "right": {"field": "expected"},
                "message": "normalized output mismatch",
            }
        ],
    }


def _last_number_contract(number_type: str) -> dict:
    extractor = "integers" if number_type == "integer" else "floats"
    return {
        "version": CONTRACT_VERSION,
        "description": "Compare the final numeric answer in reference and actual output.",
        "fields": [
            {"id": "expected", "source": "reference", "extract": extractor, "select": "last"},
            {"id": "actual", "source": "actual", "extract": extractor, "select": "last"},
        ],
        "checks": [
            {
                "id": "answer",
                "op": "equal",
                "left": {"field": "actual"},
                "right": {"field": "expected"},
                "message": "final numeric answer mismatch",
            }
        ],
    }


def _number_list_contract(order_matters: bool, allow_prompt_numbers: bool, prefix_from_stdin: bool = False) -> dict:
    fields = [
        {
            "id": "expected",
            "source": "reference",
            "extract": "integers",
            "select": "all",
            "allow_empty": prefix_from_stdin,
        },
        {
            "id": "actual",
            "source": "actual",
            "extract": "integers",
            "select": "all",
            "allow_empty": prefix_from_stdin,
        },
    ]
    if prefix_from_stdin:
        fields.extend(
            [
                {
                "id": "stdin_values",
                "source": "stdin",
                "extract": "integers",
                "select": "all",
                "allow_empty": True,
                },
                {
                    "id": "actual_text",
                    "source": "actual",
                    "extract": "text",
                    "normalize": ["lowercase", "strip_punctuation", "collapse_whitespace"],
                },
            ]
        )
    sequence_check = {
        "id": "sequence",
        "op": "tail_equal" if allow_prompt_numbers else "sequence_equal",
        "left": {"field": "actual"},
        "right": {"field": "expected"},
        "ordered": bool(order_matters),
        "message": "integer sequence mismatch",
    }
    if prefix_from_stdin:
        sequence_check["op"] = "sequence_or_text_tokens"
        sequence_check["fallback"] = {"field": "actual_text"}
        sequence_check["required_tokens"] = ["no", "divis"]
        if allow_prompt_numbers:
            sequence_check["allowed_prefix"] = {"field": "stdin_values"}
    return {
        "version": CONTRACT_VERSION,
        "description": "Compare an integer sequence extracted from reference and actual output.",
        "fields": fields,
        "checks": [sequence_check],
    }


def _extract_field(field: dict, raw_text: str) -> Any:
    text = _normalize(raw_text, field.get("normalize", []))
    scoped = _scope_text(text, field)
    extractor = field["extract"]
    if extractor == "text":
        return scoped
    if extractor == "integers":
        return _select_values(
            [int(value) for value in _INTEGER_PATTERN.findall(scoped)],
            field.get("select", "all"),
            field.get("allow_empty", False),
        )
    if extractor == "floats":
        return _select_values(
            [float(value) for value in _FLOAT_RE.findall(scoped)],
            field.get("select", "all"),
            field.get("allow_empty", False),
        )
    if extractor == "labeled_number":
        label = field.get("label")
        if label:
            number_match = re.search(
                rf"{re.escape(label)}\s*[:=]?\s*({_FLOAT_PATTERN})",
                scoped,
                re.IGNORECASE,
            )
        elif field.get("anchor"):
            number_match = _FLOAT_RE.search(scoped)
        else:
            raise ContractExtractionError("labeled_number requires label or anchor")
        if not number_match:
            raise ContractExtractionError(f"could not find labeled value '{label or field.get('anchor')}'")
        numeric_text = number_match.group(1) if label else number_match.group(0)
        return int(float(numeric_text)) if field.get("number_type") == "integer" else float(numeric_text)
    if extractor in {"point", "points"}:
        matches = [(float(x), float(y)) for x, y in _POINT_PATTERN.findall(scoped)]
        occurrence = field.get("occurrence", 0)
        count = field.get("count", 1 if extractor == "point" else 2)
        if not isinstance(occurrence, int) or not isinstance(count, int) or occurrence < 0 or count < 1 or count > 16:
            raise ContractExtractionError("point occurrence/count is invalid")
        selected = matches[occurrence:occurrence + count]
        if len(selected) != count:
            raise ContractExtractionError("required point value was not found")
        return selected[0] if extractor == "point" else selected
    if extractor == "boolean":
        true_aliases = field.get("true_aliases", [])
        false_aliases = field.get("false_aliases", [])
        candidates = []
        lowered = scoped.lower()
        for value, aliases in ((True, true_aliases), (False, false_aliases)):
            for alias in aliases:
                position = lowered.find(alias.lower())
                if position >= 0:
                    candidates.append((position, -len(alias), value))
        if not candidates:
            raise ContractExtractionError("none of the configured boolean aliases were found")
        return min(candidates)[2]
    raise ContractExtractionError(f"unsupported extractor '{extractor}'")


def _scope_text(text: str, field: dict) -> str:
    anchor = field.get("anchor")
    if not anchor:
        return text
    position = text.lower().find(anchor.lower())
    if position < 0:
        raise ContractExtractionError(f"anchor '{anchor}' was not found")
    start = position + len(anchor)
    return text[start:start + field.get("window", MAX_WINDOW)]


def _normalize(text: str, normalizers: list[str]) -> str:
    normalized = text
    for operation in normalizers:
        if operation == "normalize_apostrophe":
            normalized = normalized.replace("’", "'")
        elif operation == "collapse_whitespace":
            normalized = " ".join(normalized.replace("\r\n", "\n").replace("\r", "\n").split())
        elif operation == "lowercase":
            normalized = normalized.lower()
        elif operation == "strip_punctuation":
            normalized = re.sub(r"[^\w\s-]", " ", normalized)
            normalized = " ".join(normalized.split())
    return normalized


def _select_values(values: list, selector: Any, allow_empty: bool = False) -> Any:
    if selector in (None, "all"):
        if not values and not allow_empty:
            raise ContractExtractionError("no numeric values were found")
        return values
    if selector == "last":
        if not values:
            raise ContractExtractionError("no numeric value was found")
        return values[-1]
    if isinstance(selector, dict) and set(selector) == {"index"} and isinstance(selector["index"], int):
        try:
            return values[selector["index"]]
        except IndexError as exc:
            raise ContractExtractionError("numeric index is out of range") from exc
    if isinstance(selector, dict) and set(selector) == {"slice"}:
        slice_value = selector["slice"]
        if (
            not isinstance(slice_value, list)
            or len(slice_value) != 2
            or not all(isinstance(item, int) for item in slice_value)
            or slice_value[1] < 1
            or slice_value[1] > 32
        ):
            raise ContractExtractionError("numeric slice must be [start, positive_count]")
        selected = values[slice_value[0]:slice_value[0] + slice_value[1]]
        if len(selected) != slice_value[1]:
            raise ContractExtractionError("numeric slice is out of range")
        return selected
    raise ContractExtractionError("unsupported numeric selector")


def _resolve_value(spec: dict, values: dict[str, Any]) -> Any:
    return values[spec["field"]] if "field" in spec else spec["literal"]


def _apply_check(check: dict, left: Any, right: Any, values: dict[str, Any]) -> tuple[bool, Any, Any]:
    op = check["op"]
    if op == "equal":
        return left == right, left, right
    if op == "approx":
        tolerance = float(check.get("tolerance", 0))
        return _approximately_equal(left, right, tolerance), left, right
    if op == "sequence_or_text_tokens" and right == []:
        fallback = _resolve_value(check["fallback"], values)
        required_tokens = check.get("required_tokens", [])
        passed = isinstance(fallback, str) and all(token.lower() in fallback.lower() for token in required_tokens)
        return passed, fallback, required_tokens
    if op in {"sequence_equal", "tail_equal", "sequence_or_text_tokens"}:
        if not isinstance(left, list) or not isinstance(right, list):
            return False, left, right
        uses_tail = op in {"tail_equal", "sequence_or_text_tokens"}
        compared_left = left[-len(right):] if uses_tail and len(left) >= len(right) else left
        if uses_tail and check.get("allowed_prefix") and len(left) >= len(right):
            allowed_values = _resolve_value(check["allowed_prefix"], values)
            prefix = left[:-len(right)] if right else left
            if not isinstance(allowed_values, list) or any(value not in allowed_values for value in prefix):
                return False, left, right
        if not check.get("ordered", True):
            compared_left = sorted(compared_left)
            right = sorted(right)
        return compared_left == right, compared_left, right
    if op == "exchanged":
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != 2 or len(right) != 2:
            return False, right, [left[1], left[0]] if isinstance(left, list) and len(left) == 2 else left
        tolerance = float(check.get("tolerance", 0))
        expected_after = [left[1], left[0]]
        return _approximately_equal(right, expected_after, tolerance), right, expected_after
    return False, left, right


def _approximately_equal(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)) and len(left) == len(right):
        return all(_approximately_equal(a, b, tolerance) for a, b in zip(left, right))
    return left == right


def _valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", value))


def _valid_selector(selector: Any) -> bool:
    if isinstance(selector, str) and selector in {"all", "last"}:
        return True
    if not isinstance(selector, dict):
        return False
    if set(selector) == {"index"}:
        return isinstance(selector["index"], int) and -100 <= selector["index"] <= 100
    if set(selector) != {"slice"}:
        return False
    value = selector["slice"]
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, int) for item in value)
        and -100 <= value[0] <= 100
        and 1 <= value[1] <= 32
    )
