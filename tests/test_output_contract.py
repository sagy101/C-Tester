import unittest

from c_tester.output_contract import compile_preset, evaluate_contract, validate_contract
from c_tester.checker_assistant import run_checker_tests
from c_tester.semantic_grading import compare_output_with_config
from c_tester.semantic_grading import checker_config_errors


def trace_contract():
    fields = [
        {"id": "stdin_p", "source": "stdin", "extract": "floats", "select": {"slice": [0, 2]}},
        {"id": "stdin_q", "source": "stdin", "extract": "floats", "select": {"slice": [2, 2]}},
        {"id": "actual_get_p", "source": "actual", "extract": "point", "occurrence": 0},
        {"id": "reference_perimeter", "source": "reference", "extract": "labeled_number", "label": "Perimeter"},
        {"id": "actual_perimeter", "source": "actual", "extract": "labeled_number", "label": "Perimeter"},
        {"id": "reference_area", "source": "reference", "extract": "labeled_number", "label": "Area"},
        {"id": "actual_area", "source": "actual", "extract": "labeled_number", "label": "Area"},
    ]
    right_options = {
        "extract": "boolean",
        "anchor": "Area:",
        "true_aliases": ["right-angled: yes", "is a right-angled triangle"],
        "false_aliases": ["right-angled: no", "isn't a right-angled triangle", "is not a right-angled triangle"],
    }
    fields.extend(
        [
            {"id": "reference_right", "source": "reference", **right_options},
            {"id": "actual_right", "source": "actual", **right_options},
            {"id": "sp_before", "source": "actual", "extract": "points", "anchor": "Before swap_points", "count": 2},
            {"id": "sp_after", "source": "actual", "extract": "points", "anchor": "After swap_points", "count": 2},
            {
                "id": "p_address_changed",
                "source": "actual",
                "extract": "boolean",
                "anchor": "p address",
                "true_aliases": ["has changed"],
                "false_aliases": ["hasn't changed", "has not changed"],
                "window": 40,
            },
            {
                "id": "q_address_changed",
                "source": "actual",
                "extract": "boolean",
                "anchor": "q address",
                "true_aliases": ["has changed"],
                "false_aliases": ["hasn't changed", "has not changed"],
                "window": 40,
            },
            {"id": "ptr_before", "source": "actual", "extract": "points", "anchor": "Before swap_pointers", "count": 2},
            {"id": "ptr_after", "source": "actual", "extract": "points", "anchor": "After swap_pointers", "count": 2},
            {
                "id": "ptr0_address_changed",
                "source": "actual",
                "extract": "boolean",
                "anchor": "points[0] address",
                "true_aliases": ["has changed"],
                "false_aliases": ["hasn't changed", "has not changed"],
                "window": 40,
            },
            {
                "id": "ptr1_address_changed",
                "source": "actual",
                "extract": "boolean",
                "anchor": "points[1] address",
                "true_aliases": ["has changed"],
                "false_aliases": ["hasn't changed", "has not changed"],
                "window": 40,
            },
        ]
    )
    checks = [
        {"id": "get_p", "op": "approx", "left": {"field": "actual_get_p"}, "right": {"field": "stdin_p"}, "tolerance": 0.0001},
        {"id": "perimeter", "op": "approx", "left": {"field": "actual_perimeter"}, "right": {"field": "reference_perimeter"}, "tolerance": 0.011},
        {"id": "area", "op": "approx", "left": {"field": "actual_area"}, "right": {"field": "reference_area"}, "tolerance": 0.011},
        {"id": "right", "op": "equal", "left": {"field": "actual_right"}, "right": {"field": "reference_right"}},
        {"id": "sp_before_p", "op": "approx", "left": {"field": "sp_before"}, "right": {"literal": [(0.0, 0.0), (3.0, 0.0)]}, "tolerance": 0.0001},
        {"id": "sp_exchange", "op": "exchanged", "left": {"field": "sp_before"}, "right": {"field": "sp_after"}, "tolerance": 0.0001},
        {"id": "p_address", "op": "equal", "left": {"field": "p_address_changed"}, "right": {"literal": False}},
        {"id": "q_address", "op": "equal", "left": {"field": "q_address_changed"}, "right": {"literal": False}},
        {"id": "ptr_before_chain", "op": "approx", "left": {"field": "ptr_before"}, "right": {"field": "sp_after"}, "tolerance": 0.0001},
        {"id": "ptr_exchange", "op": "exchanged", "left": {"field": "ptr_before"}, "right": {"field": "ptr_after"}, "tolerance": 0.0001},
        {"id": "ptr0_address", "op": "equal", "left": {"field": "ptr0_address_changed"}, "right": {"literal": True}},
        {"id": "ptr1_address", "op": "equal", "left": {"field": "ptr1_address_changed"}, "right": {"literal": True}},
    ]
    return {"version": 1, "description": "Generic multi-stage numeric state trace.", "fields": fields, "checks": checks}


REFERENCE = """Enter coordinates
(0.00, 0.00)
Triangle Properties:
Perimeter: 12.00
Area: 6.00
The triangle is a right-angled triangle.
Before swap_points: P={0.000000,0.000000} Q={3.000000,0.000000}
After swap_points: P={3.000000,0.000000} Q={0.000000,0.000000}
p address hasn't changed, q address hasn't changed
Before swap_pointers: points[0] points to (3.000000, 0.000000)
Before swap_pointers: points[1] points to (0.000000, 0.000000)
After swap_pointers: points[0] points to (0.000000, 0.000000)
points[0] address has changed
After swap_pointers: points[1] points to (3.000000, 0.000000)
points[1] address has changed
"""

HARMLESS_VARIANT = """Prompts may differ
(0, 0)
Perimeter = 12
Area: 6.0
Right-angled: Yes
Before swap_points: P=(0,0) Q=(3,0)
After swap_points: P=(3,0) Q=(0,0)
p address has not changed, q address hasn't changed
Before swap_pointers: points[0] points to (3,0)
Before swap_pointers: points[1] points to (0,0)
After swap_pointers: points[0] points to (0,0)
points[0] address has changed
After swap_pointers: points[1] points to (3,0)
points[1] address has changed
"""


class OutputContractTests(unittest.TestCase):
    def test_generic_trace_accepts_harmless_formatting(self):
        result = evaluate_contract(trace_contract(), "0 0 3 0 0 4", REFERENCE, HARMLESS_VARIANT)
        self.assertTrue(result.passed, result.reason)

    def test_generic_trace_rejects_wrong_metric(self):
        actual = HARMLESS_VARIANT.replace("Perimeter = 12", "Perimeter = 12.05")
        result = evaluate_contract(trace_contract(), "0 0 3 0 0 4", REFERENCE, actual)
        self.assertFalse(result.passed)
        self.assertIn("perimeter", result.reason)

    def test_generic_trace_rejects_wrong_boolean(self):
        actual = HARMLESS_VARIANT.replace("Right-angled: Yes", "Right-angled: No")
        result = evaluate_contract(trace_contract(), "0 0 3 0 0 4", REFERENCE, actual)
        self.assertFalse(result.passed)
        self.assertIn("right", result.reason)

    def test_generic_trace_rejects_broken_exchange(self):
        actual = HARMLESS_VARIANT.replace("After swap_points: P=(3,0) Q=(0,0)", "After swap_points: P=(0,0) Q=(3,0)")
        result = evaluate_contract(trace_contract(), "0 0 3 0 0 4", REFERENCE, actual)
        self.assertFalse(result.passed)
        self.assertIn("sp_exchange", result.reason)

    def test_contract_rejects_unknown_operations(self):
        contract = trace_contract()
        contract["checks"][0]["op"] = "python_eval"
        self.assertTrue(any("unsupported operator" in error for error in validate_contract(contract)))

    def test_contract_rejects_regex_keys(self):
        contract = trace_contract()
        contract["fields"][0]["regex"] = "(a+)+"
        self.assertTrue(any("unsupported keys" in error for error in validate_contract(contract)))

    def test_labeled_number_can_use_literal_anchor(self):
        contract = {
            "version": 1,
            "fields": [
                {"id": "expected", "source": "reference", "extract": "labeled_number", "anchor": "Average:"},
                {"id": "actual", "source": "actual", "extract": "labeled_number", "anchor": "Average:"},
            ],
            "checks": [
                {
                    "id": "average",
                    "op": "approx",
                    "left": {"field": "actual"},
                    "right": {"field": "expected"},
                    "tolerance": 0.01,
                }
            ],
        }
        result = evaluate_contract(contract, "", "Average: 2.50", "Average: 2.505")
        self.assertTrue(result.passed, result.reason)

    def test_presets_execute_through_contract_engine(self):
        result = compare_output_with_config(
            {"checker": "last_integer", "config": {}},
            "5",
            "Result: 120",
            "The answer is 120",
        )
        self.assertTrue(result.passed, result.reason)
        self.assertEqual(validate_contract(compile_preset("exact")), [])

    def test_normalized_text_collapses_spaces_created_by_punctuation(self):
        result = compare_output_with_config(
            {"checker": "normalized_text", "config": {}},
            "",
            "Hello, world!",
            "hello world",
        )
        self.assertTrue(result.passed, result.reason)

    def test_legacy_divisors_alias_requires_reference_numeric_evidence(self):
        passing = compare_output_with_config(
            {"checker": "divisors", "config": {}},
            "0",
            "0 has no divisors.",
            "0 has no divisors.",
        )
        unsafe = compare_output_with_config(
            {"checker": "divisors", "config": {}},
            "0",
            "There are no divisors.",
            "unrelated garbage",
        )
        numberless = compare_output_with_config(
            {"checker": "divisors", "config": {}},
            "0",
            "There are no divisors.",
            "No divisors exist.",
        )
        self.assertTrue(passing.passed, passing.reason)
        self.assertTrue(numberless.passed, numberless.reason)
        self.assertFalse(unsafe.passed)

    def test_legacy_divisors_alias_rejects_unrelated_numeric_prefix(self):
        result = compare_output_with_config(
            {"checker": "divisors", "config": {"allow_prompt_numbers": True}},
            "6",
            "Divisors of 6: 1 2 3 6",
            "debug 99 Divisors of 6: 1 2 3 6",
        )
        self.assertFalse(result.passed)

    def test_contract_validates_operator_specific_types(self):
        contract = trace_contract()
        contract["fields"][0]["number_type"] = "decimal-ish"
        contract["checks"][0]["ordered"] = "yes"
        errors = validate_contract(contract)
        self.assertTrue(any("number_type" in error for error in errors))
        self.assertTrue(any("ordered must be boolean" in error for error in errors))

    def test_non_object_checker_config_returns_validation_error(self):
        errors = checker_config_errors({"checker": "exact", "config": ["not", "an", "object"]})
        self.assertTrue(errors)
        comparison = compare_output_with_config(["not", "an", "object"], "", "ok", "ok")
        self.assertFalse(comparison.passed)

    def test_draft_tests_require_mutations_to_be_rejected(self):
        rows = run_checker_tests(
            {"checker": "output_contract", "config": {"contract": trace_contract()}},
            [("0 0 3 0 0 4", REFERENCE)],
        )
        self.assertTrue(rows)
        self.assertTrue(
            all(row["test_passed"] for row in rows),
            [row["reason"] for row in rows if not row["test_passed"]],
        )
        self.assertTrue(any(row["variant"].startswith("reject_") for row in rows))
        self.assertTrue(any(row["variant"].startswith("accept_") for row in rows))

    def test_bounded_label_and_anchor_aliases_keep_semantics_strict(self):
        contract = {
            "version": 1,
            "description": "Alias-safe numeric and boolean facts",
            "fields": [
                {
                    "id": "expected_value",
                    "source": "reference",
                    "extract": "labeled_number",
                    "label": "Value:",
                    "labels": ["Result is"],
                },
                {
                    "id": "actual_value",
                    "source": "actual",
                    "extract": "labeled_number",
                    "label": "Value:",
                    "labels": ["Result is"],
                },
                {
                    "id": "expected_ok",
                    "source": "reference",
                    "extract": "boolean",
                    "anchor": "Status:",
                    "anchors": ["Answer:"],
                    "true_aliases": ["yes", "correct"],
                    "false_aliases": ["no", "incorrect"],
                },
                {
                    "id": "actual_ok",
                    "source": "actual",
                    "extract": "boolean",
                    "anchor": "Status:",
                    "anchors": ["Answer:"],
                    "true_aliases": ["yes", "correct"],
                    "false_aliases": ["no", "incorrect"],
                },
            ],
            "checks": [
                {
                    "id": "value",
                    "op": "approx",
                    "left": {"field": "actual_value"},
                    "right": {"field": "expected_value"},
                    "tolerance": 0.001,
                },
                {
                    "id": "ok",
                    "op": "equal",
                    "left": {"field": "actual_ok"},
                    "right": {"field": "expected_ok"},
                },
            ],
        }
        config = {"checker": "output_contract", "config": {"contract": contract}}
        expected = "Value: 12.5\nStatus: yes"
        equivalent = "Result is 12.5\nAnswer: correct"
        wrong = "Result is 13.5\nAnswer: correct"
        self.assertTrue(compare_output_with_config(config, "", expected, equivalent).passed)
        self.assertFalse(compare_output_with_config(config, "", expected, wrong).passed)

    def test_extraction_failures_have_typed_reason(self):
        config = {
            "checker": "output_contract",
            "config": {
                "contract": {
                    "version": 1,
                    "description": "Typed missing label",
                    "fields": [
                        {
                            "id": "expected",
                            "source": "reference",
                            "extract": "labeled_number",
                            "label": "Value:",
                        },
                        {
                            "id": "actual",
                            "source": "actual",
                            "extract": "labeled_number",
                            "label": "Value:",
                        },
                    ],
                    "checks": [
                        {
                            "id": "value",
                            "op": "equal",
                            "left": {"field": "actual"},
                            "right": {"field": "expected"},
                        }
                    ],
                }
            },
        }
        result = compare_output_with_config(config, "", "Value: 4", "Result: 4")
        self.assertFalse(result.passed)
        self.assertIn("[missing_label]", result.reason)

    def test_boolean_alias_followed_by_negation_is_inverted(self):
        # Regression: aliases ["is"] / ["isn't"] misparsed "is not" as True
        # because the negated phrasing was missing from the alias list.
        contract = {
            "version": 1,
            "fields": [
                {
                    "id": "ref_flag",
                    "source": "reference",
                    "extract": "boolean",
                    "anchor": "The triangle",
                    "true_aliases": ["is"],
                    "false_aliases": ["isn't"],
                },
                {
                    "id": "act_flag",
                    "source": "actual",
                    "extract": "boolean",
                    "anchor": "The triangle",
                    "true_aliases": ["is"],
                    "false_aliases": ["isn't"],
                },
            ],
            "checks": [
                {"id": "flag", "op": "equal", "left": {"field": "act_flag"}, "right": {"field": "ref_flag"}},
            ],
        }
        reference = "The triangle isn't a right-angled triangle."
        for equivalent_phrasing in (
            "The triangle is not a right-angled triangle.",
            "The triangle isn't a right-angled triangle.",
            "The triangle isn\u2019t a right-angled triangle.",
            "The triangle isnt a right-angled triangle.",
        ):
            with self.subTest(actual=equivalent_phrasing):
                result = evaluate_contract(contract, "1 2 3", reference, equivalent_phrasing)
                self.assertTrue(result.passed, result.reason)

        positive = evaluate_contract(contract, "1 2 3", reference, "The triangle is a right-angled triangle.")
        self.assertFalse(positive.passed)

    def test_boolean_negation_inversion_applies_after_bare_positive_alias(self):
        contract = {
            "version": 1,
            "fields": [
                {
                    "id": "act_changed",
                    "source": "actual",
                    "extract": "boolean",
                    "anchor": "p address",
                    "true_aliases": ["has"],
                    "false_aliases": ["hasn't"],
                },
            ],
            "checks": [
                {"id": "changed", "op": "equal", "left": {"field": "act_changed"}, "right": {"literal": False}},
            ],
        }
        for wording in ("p address hasn't changed", "p address has not changed", "p address hasnt changed"):
            with self.subTest(actual=wording):
                result = evaluate_contract(contract, "", "unused", wording)
                self.assertTrue(result.passed, result.reason)
        result = evaluate_contract(contract, "", "unused", "p address has changed")
        self.assertFalse(result.passed)

    def test_draft_tests_accept_equivalent_negation_rewording(self):
        rows = run_checker_tests(
            {"checker": "output_contract", "config": {"contract": trace_contract()}},
            [("0 0 3 0 0 4", REFERENCE)],
        )
        rewording_rows = [row for row in rows if row["variant"] == "accept_equivalent_negation"]
        self.assertTrue(rewording_rows)
        self.assertIn("has not changed", rewording_rows[0]["actual_output"])
        self.assertTrue(all(row["expected_pass"] for row in rewording_rows))
        self.assertTrue(
            all(row["test_passed"] for row in rewording_rows),
            [row["reason"] for row in rewording_rows if not row["test_passed"]],
        )

    def test_contraction_expansion_keeps_irregular_contractions_intact(self):
        from c_tester.checker_assistant import _expand_negative_contractions

        self.assertEqual(
            _expand_negative_contractions("It isn't right and the value hasn't changed."),
            "It is not right and the value has not changed.",
        )
        self.assertEqual(
            _expand_negative_contractions("You can't and won't divide; DOESN'T matter."),
            "You can't and won't divide; DOES not matter.",
        )

    def test_zero_answer_draft_wrong_variant_is_still_rejected(self):
        rows = run_checker_tests(
            {"checker": "last_integer", "config": {}},
            [("0", "Result: 0")],
        )
        self.assertTrue(all(row["test_passed"] for row in rows), rows)


if __name__ == "__main__":
    unittest.main()
