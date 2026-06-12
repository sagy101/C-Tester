import os
import tempfile
import unittest

from c_tester.configuration import (
    detect_question_folders,
    distribute_even_weights,
    load_gui_config,
    merge_saved_question_config,
    save_gui_config,
)


class TestConfigurationDefaults(unittest.TestCase):
    def test_detect_question_folders_finds_valid_questions_in_natural_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._create_question(temp_dir, "Q10")
            self._create_question(temp_dir, "Q2")
            self._create_question(temp_dir, "Q1")
            os.mkdir(os.path.join(temp_dir, "Q3"))

            self.assertEqual(detect_question_folders(temp_dir), ["Q1", "Q2", "Q10"])

    def test_distribute_even_weights_sums_to_100(self):
        weights = distribute_even_weights(["Q1", "Q2", "Q3"])

        self.assertEqual(weights, {"Q1": 34, "Q2": 33, "Q3": 33})
        self.assertEqual(sum(weights.values()), 100)

    def test_merge_saved_question_config_preserves_valid_saved_weights(self):
        saved_config = {
            "questions": ["Q1", "Q2"],
            "folder_weights": {"Q1": 60, "Q2": 40},
        }

        questions, weights = merge_saved_question_config(saved_config, ["Q1", "Q2"])

        self.assertEqual(questions, ["Q1", "Q2"])
        self.assertEqual(weights, {"Q1": 60, "Q2": 40})

    def test_merge_saved_question_config_rebalances_when_detected_questions_change(self):
        saved_config = {
            "questions": ["Q1", "Q2"],
            "folder_weights": {"Q1": 50, "Q2": 50},
        }

        questions, weights = merge_saved_question_config(saved_config, ["Q1", "Q2", "Q3"])

        self.assertEqual(questions, ["Q1", "Q2", "Q3"])
        self.assertEqual(weights, {"Q1": 34, "Q2": 33, "Q3": 33})

    def test_save_and_load_gui_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "gui_config.json")
            config = {
                "questions": ["Q1"],
                "folder_weights": {"Q1": 100},
                "penalty": 7,
                "simple_naming": True,
            }

            save_gui_config(config, config_path)

            self.assertEqual(load_gui_config(config_path), config)

    def _create_question(self, root_path, question_name):
        question_path = os.path.join(root_path, question_name)
        os.mkdir(question_path)
        os.mkdir(os.path.join(question_path, "C"))
        for file_name in ("input.txt", "original_sol.c"):
            with open(os.path.join(question_path, file_name), "w", encoding="utf-8") as question_file:
                question_file.write("\n")


if __name__ == "__main__":
    unittest.main()
