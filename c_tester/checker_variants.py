"""Pure bidirectional test-case generation for deterministic checkers."""

from __future__ import annotations

import re
from typing import Any

from .output_contract import ContractConfigError, compile_preset, extract_contract_field


_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def generate_checker_variants(checker_config: dict, expected_output: str) -> list[tuple[str, str, bool]]:
    """Return semantic-preserving accepts and semantic-breaking rejects."""
    checker_name = (checker_config or {}).get("checker", "exact")
    try:
        contract = compile_preset(checker_name, (checker_config or {}).get("config", {}))
    except ContractConfigError:
        return []

    if checker_name != "output_contract":
        return _preset_variants(checker_name, expected_output)

    checked_actual_ids = {
        check.get(side, {}).get("field")
        for check in contract.get("checks", [])
        for side in ("left", "right")
    }
    actual_fields = [
        field
        for field in contract.get("fields", [])
        if field.get("source") == "actual" and field.get("id") in checked_actual_ids
    ]
    variants: list[tuple[str, str, bool]] = []
    seen = {expected_output}

    if actual_fields and all(field.get("extract") != "text" for field in actual_fields):
        for name, transformed in _safe_format_variants(expected_output):
            _append_unique(variants, seen, name, transformed, True)
        for field in actual_fields:
            for name, transformed in _configured_alias_variants(expected_output, field):
                _append_unique(variants, seen, name, transformed, True)

    for field in actual_fields:
        mutated = _mutate_field(expected_output, field)
        if mutated and _field_value_changed(field, expected_output, mutated):
            _append_unique(variants, seen, f"reject_{field['id']}", mutated, False)
        removed = _remove_field_value(expected_output, field)
        if removed and _field_invalidated(field, expected_output, removed):
            _append_unique(variants, seen, f"reject_missing_{field['id']}", removed, False)
        if sum(1 for _, _, expected_pass in variants if not expected_pass) >= 16:
            break

    if len(expected_output) > 20:
        _append_unique(
            variants,
            seen,
            "reject_truncated",
            expected_output[: len(expected_output) // 2],
            False,
        )
    return variants


def _preset_variants(checker_name: str, output: str) -> list[tuple[str, str, bool]]:
    variants: list[tuple[str, str, bool]] = []
    seen = {output}
    if checker_name == "normalized_text":
        for name, transformed in _safe_format_variants(output):
            _append_unique(variants, seen, name, transformed, True)
    elif checker_name in {"last_integer", "reverse_integer", "integer_list", "divisors"}:
        _append_unique(variants, seen, "accept_prompt_text", f"Result: {output}", True)
        numbers = list(_NUMBER_RE.finditer(output))
        if numbers:
            match = numbers[-1]
            changed = output[: match.start()] + str(int(float(match.group())) + 1) + output[match.end():]
            _append_unique(variants, seen, "reject_wrong_numeric_answer", changed, False)
    return variants


def _safe_format_variants(output: str) -> list[tuple[str, str]]:
    return [
        ("accept_case_variant", output.swapcase()),
        ("accept_line_layout", " ".join(output.split())),
        (
            "accept_coordinate_spacing",
            re.sub(r"(?<=\d)\s*,\s*(?=[+-]?(?:\d|\.\d))", ",", output),
        ),
        ("accept_equivalent_negation", _expand_negative_contractions(output)),
        ("accept_unicode_apostrophe", output.replace("'", "\u2019")),
    ]


def _configured_alias_variants(output: str, field: dict) -> list[tuple[str, str]]:
    variants = []
    for singular, plural, prefix in (
        ("label", "labels", "label"),
        ("anchor", "anchors", "anchor"),
    ):
        options = _options(field, singular, plural)
        if len(options) < 2:
            continue
        source = next((option for option in options if option.lower() in output.lower()), None)
        if source is None:
            continue
        for alternative in options:
            if alternative == source:
                continue
            variants.append(
                (
                    f"accept_{prefix}_alias_{field.get('id', 'field')}",
                    _replace_first_case_insensitive(output, source, alternative),
                )
            )
            break
    return variants


def _mutate_field(output: str, field: dict) -> str | None:
    extractor = field.get("extract")
    start, scoped = _scope(output, field)
    if scoped is None:
        return None
    if extractor == "labeled_number":
        match = _labeled_number_match(scoped, field)
        if not match:
            return None
        value_group = match.lastindex or 0
        old = match.group(value_group)
        replacement = f"{float(old) + 1:g}"
        return output[: start + match.start(value_group)] + replacement + output[start + match.end(value_group):]
    if extractor == "boolean":
        pairs = [
            (old, new)
            for old_values, new_values in (
                (field.get("true_aliases", []), field.get("false_aliases", [])),
                (field.get("false_aliases", []), field.get("true_aliases", [])),
            )
            for old in old_values
            for new in new_values[:1]
        ]
        for old, new in pairs:
            position = scoped.lower().find(str(old).lower())
            if position >= 0:
                absolute = start + position
                return output[:absolute] + str(new) + output[absolute + len(str(old)):]
        return None
    if extractor in {"point", "points", "integers", "floats"}:
        match = _NUMBER_RE.search(scoped)
        if not match:
            return None
        replacement = f"{float(match.group()) + 1:g}"
        return output[: start + match.start()] + replacement + output[start + match.end():]
    if extractor == "text":
        return output + "\n__unexpected_semantic_value__"
    return None


def _remove_field_value(output: str, field: dict) -> str | None:
    if field.get("extract") == "boolean":
        anchors = _options(field, "anchor", "anchors")
        anchor_positions = [
            (output.lower().find(anchor.lower()), anchor)
            for anchor in anchors
            if output.lower().find(anchor.lower()) >= 0
        ]
        if anchor_positions:
            position, _ = min(anchor_positions)
            line_start = output.rfind("\n", 0, position) + 1
            line_end = output.find("\n", position)
            if line_end < 0:
                line_end = len(output)
            else:
                line_end += 1
            return output[:line_start] + output[line_end:]
    start, scoped = _scope(output, field)
    if scoped is None:
        return None
    extractor = field.get("extract")
    match = _labeled_number_match(scoped, field) if extractor == "labeled_number" else None
    if match:
        value_group = match.lastindex or 0
        return output[: start + match.start(value_group)] + output[start + match.end(value_group):]
    if extractor in {"point", "points", "integers", "floats"}:
        match = _NUMBER_RE.search(scoped)
    elif extractor == "boolean":
        aliases = [*field.get("true_aliases", []), *field.get("false_aliases", [])]
        positions = [
            (scoped.lower().find(str(alias).lower()), str(alias))
            for alias in aliases
            if scoped.lower().find(str(alias).lower()) >= 0
        ]
        if not positions:
            return None
        position, alias = min(positions)
        return output[: start + position] + output[start + position + len(alias):]
    if not match:
        return None
    return output[: start + match.start()] + output[start + match.end():]


def _scope(output: str, field: dict) -> tuple[int, str | None]:
    anchors = _options(field, "anchor", "anchors")
    if not anchors:
        return 0, output
    candidates = [
        (output.lower().find(anchor.lower()), anchor)
        for anchor in anchors
        if output.lower().find(anchor.lower()) >= 0
    ]
    if not candidates:
        return 0, None
    position, anchor = min(candidates)
    start = position + len(anchor)
    return start, output[start:start + int(field.get("window", 4096))]


def _labeled_number_match(scoped: str, field: dict) -> re.Match | None:
    for label in _options(field, "label", "labels"):
        match = re.search(
            rf"{re.escape(label)}\s*[:=]?\s*({_NUMBER_RE.pattern})",
            scoped,
            re.IGNORECASE,
        )
        if match:
            return match
    if not _options(field, "label", "labels"):
        return _NUMBER_RE.search(scoped)
    return None


def _field_value_changed(field: dict, original: str, mutated: str) -> bool:
    try:
        return extract_contract_field(field, original) != extract_contract_field(field, mutated)
    except (TypeError, ValueError):
        return False


def _field_invalidated(field: dict, original: str, mutated: str) -> bool:
    try:
        original_value = extract_contract_field(field, original)
    except (TypeError, ValueError):
        return False
    try:
        mutated_value = extract_contract_field(field, mutated)
    except (TypeError, ValueError):
        return True
    return original_value != mutated_value


def _expand_negative_contractions(text: str) -> str:
    def replace(match: re.Match) -> str:
        word = match.group(0)
        if word[:-3].lower() in {"ca", "wo", "sha", "ai"}:
            return word
        return f"{word[:-3]} not"

    return re.sub(r"[A-Za-z]+n't\b", replace, text, flags=re.IGNORECASE)


def _replace_first_case_insensitive(text: str, old: str, new: str) -> str:
    match = re.search(re.escape(old), text, re.IGNORECASE)
    return text if match is None else text[:match.start()] + new + text[match.end():]


def _options(field: dict, singular: str, plural: str) -> list[str]:
    values: list[str] = []
    if isinstance(field.get(singular), str):
        values.append(field[singular])
    for value in field.get(plural, []):
        if isinstance(value, str) and value not in values:
            values.append(value)
    return values


def _append_unique(
    variants: list[tuple[str, str, bool]],
    seen: set[str],
    name: str,
    output: str,
    expected_pass: bool,
) -> None:
    if output and output not in seen:
        variants.append((name, output, expected_pass))
        seen.add(output)
