"""Configuration settings for the C Auto Grader."""

import json
import os # Needed for validate_config
import re

# Flag to control file naming pattern
# When True: expects files named as "hw[0-9].c" and treats them as "hw[0-9]_q1.c"
# When False: expects files named as "hw[0-9]_q[0-9].c" (default)
use_simple_naming = False

# Penalty points for submission errors reported in submit_error.txt
penalty = 5

# Flag to determine if penalty is applied per error or once globally per student
# When True: each error gets its own penalty (can accumulate)
# When False: only apply penalty once per student regardless of number of errors
per_error_penalty = False

# Question scoring mode for failed test cases.
# "percentage": grade = ceil(correct_tests / total_tests * 100)
# "per_error_deduction": grade = max(0, 100 - test_error_deduction * failed_tests)
test_scoring_mode = "percentage"
test_error_deduction = 2

# Optional LLM compile-only repair for submissions that fail to compile.
llm_compile_repair_enabled = False
llm_compile_repair_penalty = 10
llm_compile_repair_max_attempts = 3
llm_compile_repair_provider = "Gemini"
llm_compile_repair_model = ""

DEFAULT_GUI_CONFIG_FILENAME = "gui_config.json"

# Flag to enable RAR file extraction support
isRarSupportActive = False

# Path to WinRAR executable for RAR extraction
# Change this to match your WinRAR installation path
winrar_path = r"C:\Program Files\WinRAR\UnRAR.exe"
# If UnRAR.exe is not available, use WinRAR.exe instead:
# winrar_path = r"C:\Program Files\WinRAR\WinRAR.exe"

# Path to Visual Studio environment batch file
vs_path = r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"

QUESTION_FOLDER_PATTERN = re.compile(r"^Q(\d+)$", re.IGNORECASE)


def gui_config_path(root_path=None):
    """Return the local GUI config path for a project folder."""
    return os.path.join(root_path or os.getcwd(), DEFAULT_GUI_CONFIG_FILENAME)


def load_gui_config(config_path=None):
    """Load saved GUI settings, returning an empty dict when unavailable."""
    path = config_path or gui_config_path()
    try:
        with open(path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return {}

    return config if isinstance(config, dict) else {}


def save_gui_config(config, config_path=None):
    """Save GUI settings to the local project config file."""
    path = config_path or gui_config_path()
    with open(path, "w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)
        config_file.write("\n")
    return path


def detect_question_folders(root_path=None):
    """Return valid question folders found in the project root, sorted naturally."""
    if root_path is None:
        root_path = os.getcwd()

    detected = []
    try:
        folder_names = os.listdir(root_path)
    except OSError:
        return detected

    for folder_name in folder_names:
        match = QUESTION_FOLDER_PATTERN.match(folder_name)
        if not match:
            continue

        folder_path = os.path.join(root_path, folder_name)
        if not os.path.isdir(folder_path):
            continue

        if (
            os.path.isdir(os.path.join(folder_path, "C"))
            and os.path.isfile(os.path.join(folder_path, "input.txt"))
            and os.path.isfile(os.path.join(folder_path, "original_sol.c"))
        ):
            detected.append((int(match.group(1)), folder_name))

    return [folder_name for _, folder_name in sorted(detected)]


def distribute_even_weights(question_list):
    """Assign integer weights that are as even as possible and sum to 100."""
    if not question_list:
        return {}

    base_weight, remainder = divmod(100, len(question_list))
    return {
        question: base_weight + (1 if index < remainder else 0)
        for index, question in enumerate(question_list)
    }


def merge_saved_question_config(saved_config, detected_questions=None, fallback_questions=None):
    """Merge saved question settings with currently detected question folders."""
    fallback_questions = list(fallback_questions or ["Q1", "Q2"])
    saved_config = saved_config if isinstance(saved_config, dict) else {}
    detected_questions = list(detected_questions or [])
    saved_questions = [
        question
        for question in saved_config.get("questions", [])
        if isinstance(question, str) and question
    ]

    if detected_questions:
        question_list = detected_questions
    elif saved_questions:
        question_list = saved_questions
    else:
        question_list = fallback_questions

    saved_weights = saved_config.get("folder_weights", {})
    if not isinstance(saved_weights, dict):
        saved_weights = {}

    weights = {}
    for question in question_list:
        saved_weight = saved_weights.get(question)
        if isinstance(saved_weight, (int, float)):
            weights[question] = saved_weight

    if set(weights) != set(question_list) or sum(weights.values()) != 100:
        weights = distribute_even_weights(question_list)

    return question_list, weights


def _saved_value(saved_config, key, current_value, expected_type):
    value = saved_config.get(key)
    return value if isinstance(value, expected_type) else current_value


def _saved_non_empty_string(saved_config, key, current_value):
    value = saved_config.get(key)
    return value if isinstance(value, str) and value else current_value


# List of question folder names (must match actual folder names in the project root)
_saved_gui_config = load_gui_config()
questions, folder_weights = merge_saved_question_config(_saved_gui_config, detect_question_folders())

# Dictionary mapping question folder names to their weight percentage for the final grade
# Ensure keys match the 'questions' list and values sum to 100.
penalty = _saved_value(_saved_gui_config, "penalty", penalty, int)
per_error_penalty = _saved_value(_saved_gui_config, "per_error_penalty", per_error_penalty, bool)
test_scoring_mode = _saved_non_empty_string(_saved_gui_config, "test_scoring_mode", test_scoring_mode)
test_error_deduction = _saved_value(_saved_gui_config, "test_error_deduction", test_error_deduction, (int, float))
llm_compile_repair_enabled = _saved_value(
    _saved_gui_config,
    "llm_compile_repair_enabled",
    llm_compile_repair_enabled,
    bool,
)
llm_compile_repair_penalty = _saved_value(
    _saved_gui_config,
    "llm_compile_repair_penalty",
    llm_compile_repair_penalty,
    (int, float),
)
llm_compile_repair_max_attempts = _saved_value(
    _saved_gui_config,
    "llm_compile_repair_max_attempts",
    llm_compile_repair_max_attempts,
    int,
)
llm_compile_repair_provider = _saved_non_empty_string(
    _saved_gui_config,
    "llm_compile_repair_provider",
    llm_compile_repair_provider,
)
llm_compile_repair_model = _saved_value(_saved_gui_config, "llm_compile_repair_model", llm_compile_repair_model, str)
isRarSupportActive = _saved_value(_saved_gui_config, "rar_support", isRarSupportActive, bool)
use_simple_naming = _saved_value(_saved_gui_config, "simple_naming", use_simple_naming, bool)
vs_path = _saved_non_empty_string(_saved_gui_config, "vs_path", vs_path)
winrar_path = _saved_non_empty_string(_saved_gui_config, "winrar_path", winrar_path)

def validate_config(questions_list, weights_dict):
    """Validates the questions list, weights dict, and folder structure.

    Checks:
    1. Question folders exist.
    2. Each question folder contains C/, input.txt, original_sol.c.
    3. Weight keys match question list exactly.
    4. Weight values sum to 100.
    
    Returns:
        list: A list of error strings. Empty if configuration is valid.
    """
    errors = []
    valid_q_folders_for_weight_check = set()

    # 1 & 2: Validate question folders and their required contents
    for q_folder in questions_list:
        is_valid_entry = True
        if not isinstance(q_folder, str) or not q_folder:
            errors.append(f"Invalid entry in 'questions' list: '{q_folder}'. Must be a non-empty string.")
            is_valid_entry = False
            continue # Skip further checks for this entry
        
        q_folder_path = os.path.abspath(q_folder) # Use absolute path for checks
        
        if not os.path.isdir(q_folder_path):
            errors.append(f"Configuration error: Folder '{q_folder}' not found (Expected path: {q_folder_path}).")
            is_valid_entry = False
            continue # Skip content checks if folder doesn't exist
        else:
            # Folder exists, check contents
            c_dir_path = os.path.join(q_folder_path, "C")
            input_file_path = os.path.join(q_folder_path, "input.txt")
            sol_file_path = os.path.join(q_folder_path, "original_sol.c")
            
            content_errors = []
            if not os.path.isdir(c_dir_path):
                content_errors.append("Missing 'C' subdirectory.")
            if not os.path.isfile(input_file_path):
                content_errors.append("Missing 'input.txt' file.")
            if not os.path.isfile(sol_file_path):
                content_errors.append("Missing 'original_sol.c' file.")
            
            if content_errors:
                errors.append(f"Configuration error in folder '{q_folder}': {', '.join(content_errors)}")
                is_valid_entry = False
        
        # Only add to set for weight check if folder structure is valid
        if is_valid_entry:
             valid_q_folders_for_weight_check.add(q_folder)

    # 3. Validate weights dictionary keys match VALID questions list items
    weights_set = set(weights_dict.keys())

    # Compare weights against only the structurally valid question folders
    if valid_q_folders_for_weight_check != weights_set:
        missing_in_weights = valid_q_folders_for_weight_check - weights_set
        extra_in_weights = weights_set - valid_q_folders_for_weight_check
        if missing_in_weights:
            errors.append(f"Configuration error: Weights missing for valid question folder(s): {', '.join(sorted(missing_in_weights))}")
        if extra_in_weights:
            # Check if the extra weight folder was invalid due to structure vs non-existent
            all_q_entries_set = set(q for q in questions_list if isinstance(q, str) and q)
            truly_non_existent = extra_in_weights - all_q_entries_set
            invalid_structure_folders = extra_in_weights & all_q_entries_set
            if truly_non_existent:
                 errors.append(f"Configuration error: Weights defined for non-existent/unlisted question folder(s): {', '.join(sorted(truly_non_existent))}")
            if invalid_structure_folders:
                 errors.append(f"Configuration error: Weights defined for question folder(s) with invalid structure: {', '.join(sorted(invalid_structure_folders))}")

    # 4. Validate weights sum to 100
    try:
        # Filter out non-numeric weights before summing, handle in validation #2
        numeric_weights = [w for w in weights_dict.values() if isinstance(w, (int, float))]
        if len(numeric_weights) != len(weights_dict):
             errors.append("Configuration error: All folder weights must be numeric values.")
        else:
            total_weight = sum(numeric_weights)
            if total_weight != 100:
                errors.append(f"Configuration error: Folder weights sum to {total_weight}%, but should sum to 100%.")
    except TypeError:
        # This case should ideally be caught by the check above, but keep as fallback
        errors.append("Configuration error: Folder weights must be numeric values.")

    return errors

# --- You can add other configurable parameters below --- 