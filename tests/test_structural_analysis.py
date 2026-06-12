import unittest

from c_tester.structural_analysis import analyze_structural_requirements


class TestStructuralAnalysis(unittest.TestCase):
    def test_recursive_helper_satisfies_recursion_requirement(self):
        code = """
        int helper(int n) {
            if (n < 10) return n;
            return helper(n / 10);
        }

        int q_2(int num) {
            return helper(num);
        }
        """

        result = analyze_structural_requirements(
            code,
            {
                "requires_recursion": True,
                "entry_functions": ["q_2"],
                "allow_recursive_helpers": True,
                "forbid_loops": True,
                "deduction": 100,
            },
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.penalty, 0)

    def test_loop_without_recursion_fails_requirement(self):
        code = """
        int q_2(int num) {
            int sum = 0;
            while (num > 0) {
                sum += num % 10;
                num /= 10;
            }
            return sum;
        }
        """

        result = analyze_structural_requirements(
            code,
            {
                "requires_recursion": True,
                "entry_functions": ["q_2"],
                "allow_recursive_helpers": True,
                "forbid_loops": True,
                "deduction": 100,
            },
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.penalty, 100)
        self.assertIn("Non-recursive solution check failed", result.reason)
        self.assertIn("no required recursive call", result.reason)
        self.assertIn("forbidden loop", result.reason)

    def test_hw2_style_solution_with_prototypes_and_helpers_is_analyzed_quickly(self):
        code = """
        #include <stdio.h>
        int q_1(int num);
        int q_2(int num);
        int q_3(int num);
        int main(){ return q_1(10) + q_2(376) + q_3(9); }
        int q_1(int num){ if(num == 0) return 0; return q_1(num / 2) * 10 + num % 2; }
        int q_2(int num){ if(num < 10) return num; return q_2((num % 10) + q_2(num / 10)); }
        int q_3_helper(int num, int sign){ if(num == 0) return 0; return sign * num * num + q_3_helper(num - 1, -sign); }
        int q_3(int num){ return q_3_helper(num, 1); }
        """

        for entry_function in ["q_1", "q_2", "q_3"]:
            with self.subTest(entry_function=entry_function):
                result = analyze_structural_requirements(
                    code,
                    {
                        "requires_recursion": True,
                        "entry_functions": [entry_function],
                        "allow_recursive_helpers": True,
                        "forbid_loops": True,
                        "deduction": 100,
                    },
                )

                self.assertTrue(result.passed)

    def test_mutual_recursion_satisfies_requirement(self):
        code = """
        int odd(int n);
        int even(int n) { if (n == 0) return 1; return odd(n - 1); }
        int odd(int n) { if (n == 0) return 0; return even(n - 1); }
        int q_1(int n) { return even(n); }
        """

        result = analyze_structural_requirements(
            code,
            {
                "requires_recursion": True,
                "entry_functions": ["q_1"],
                "allow_recursive_helpers": True,
                "forbid_loops": True,
                "deduction": 100,
            },
        )

        self.assertTrue(result.passed)

    def test_unreachable_recursive_helper_does_not_satisfy_entry_requirement(self):
        code = """
        int helper(int n) { if (n == 0) return 0; return helper(n - 1); }
        int q_1(int n) { return n; }
        """

        result = analyze_structural_requirements(
            code,
            {
                "requires_recursion": True,
                "entry_functions": ["q_1"],
                "allow_recursive_helpers": True,
                "forbid_loops": True,
                "deduction": 100,
            },
        )

        self.assertFalse(result.passed)
        self.assertIn("non-recursive solution", result.reason.lower())
        self.assertIn("no required recursive call", result.reason)

    def test_loops_in_comments_strings_and_unreachable_helpers_do_not_fail(self):
        code = r'''
        int unused(int n) { while (n > 0) { n--; } return n; }
        int q_1(int n) {
            // while (n > 0) should not count
            char *text = "for (int i = 0; i < n; i++)";
            if (n == 0) return 0;
            return q_1(n - 1);
        }
        '''

        result = analyze_structural_requirements(
            code,
            {
                "requires_recursion": True,
                "entry_functions": ["q_1"],
                "allow_recursive_helpers": True,
                "forbid_loops": True,
                "deduction": 100,
            },
        )

        self.assertTrue(result.passed)

    def test_function_pointer_call_does_not_count_as_proven_recursion(self):
        code = """
        int q_1(int n) {
            int (*again)(int) = q_1;
            if (n == 0) return 0;
            return again(n - 1);
        }
        """

        result = analyze_structural_requirements(
            code,
            {
                "requires_recursion": True,
                "entry_functions": ["q_1"],
                "allow_recursive_helpers": True,
                "forbid_loops": True,
                "deduction": 100,
            },
        )

        self.assertFalse(result.passed)
        self.assertIn("non-recursive solution", result.reason.lower())
        self.assertIn("no required recursive call", result.reason)


if __name__ == "__main__":
    unittest.main()
