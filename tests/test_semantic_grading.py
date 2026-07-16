import unittest

from c_tester.semantic_grading import compare_output, compare_output_with_config


class TestSemanticGrading(unittest.TestCase):
    def test_q1_accepts_reference_output(self):
        result = compare_output("Q1", "6", "Divisors of 6 are: 1 2 3 6", "Divisors of 6 are: 1 2 3 6")

        self.assertTrue(result.passed)

    def test_q1_accepts_prompted_divisor_list(self):
        result = compare_output_with_config(
            {"checker": "divisors", "config": {"allow_prompt_numbers": True}},
            "6",
            "Divisors of 6 are: 1 2 3 6",
            "Input: n = 6\nOutput: 1 2 3 6",
        )

        self.assertTrue(result.passed)

    def test_q1_rejects_partial_divisor_list(self):
        result = compare_output("Q1", "6", "Divisors of 6 are: 1 2 3 6", "Divisors: 1 2 3")

        self.assertFalse(result.passed)

    def test_q1_rejects_reordered_divisor_list(self):
        result = compare_output("Q1", "6", "Divisors of 6 are: 1 2 3 6", "Divisors: 6 3 2 1")

        self.assertFalse(result.passed)

    def test_q1_rejects_unrelated_extra_numbers(self):
        result = compare_output("Q1", "6", "Divisors of 6 are: 1 2 3 6", "Count 4: 1 2 3 6")

        self.assertFalse(result.passed)

    def test_q1_zero_requires_no_divisor_message(self):
        config = {"checker": "divisors", "config": {"zero_requires_no_divisors_message": True}}
        passing = compare_output_with_config(config, "0", "0 has no Divisors!", "0 has no divisors")
        failing = compare_output_with_config(config, "0", "0 has no Divisors!", "Input: n = Output:")

        self.assertTrue(passing.passed)
        self.assertFalse(failing.passed)

    def test_q2_accepts_prompted_reverse_output(self):
        result = compare_output(
            "Q2",
            "125",
            "Reverse of the number is: 521",
            "Enter a number to reverse: Reverse of number is: 521",
        )

        self.assertTrue(result.passed)

    def test_q2_rejects_wrong_reverse_output(self):
        result = compare_output("Q2", "125", "Reverse of the number is: 521", "Reverse is: 125")

        self.assertFalse(result.passed)

    def test_q2_rejects_trailing_unrelated_number(self):
        result = compare_output("Q2", "125", "Reverse of the number is: 521", "Reverse is: 521 status 0")

        self.assertFalse(result.passed)

    def test_q2_handles_trailing_zero_reference_behavior(self):
        result = compare_output("Q2", "1200", "Reverse of the number is: 21", "answer: 21")

        self.assertTrue(result.passed)

    def test_input_derived_checkers_can_use_selected_stdin_integer(self):
        divisors_result = compare_output_with_config(
            {
                "checker": "divisors",
                "config": {
                    "allow_prompt_numbers": True,
                    "zero_requires_no_divisors_message": True,
                    "input_integer_index": 1,
                },
            },
            "7 6",
            "Divisors: 1 2 3 6",
            "Choose question\nDivisors: 1 2 3 6",
        )
        reverse_result = compare_output_with_config(
            {"checker": "reverse_integer", "config": {"input_integer_index": 1}},
            "2 125",
            "Reverse is 521",
            "Result = 521",
        )

        self.assertTrue(divisors_result.passed)
        self.assertTrue(reverse_result.passed)

    def test_legacy_input_index_no_longer_overrides_reference_answer(self):
        result = compare_output_with_config(
            {"checker": "reverse_integer", "config": {"input_integer_index": 0}},
            "2 125",
            "Reverse is 521",
            "Result = 521",
        )

        self.assertTrue(result.passed)

    def test_timeout_is_never_semantic_match(self):
        result = compare_output("Q2", "125", "Reverse of the number is: 521", "Timeout")

        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
