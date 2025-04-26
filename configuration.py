"""Configuration settings for the C Auto Grader."""

import os # Needed for validate_config

# Penalty points for submission errors reported in submit_error.txt
penalty = 5

# Flag to determine if penalty is applied per error or once globally per student
# When True: each error gets its own penalty (can accumulate)
# When False: only apply penalty once per student regardless of number of errors
per_error_penalty = False

# List of question folder names (must match actual folder names in the project root)
questions = ["Q1", "Q2"]

# Dictionary mapping question folder names to their weight percentage for the final grade
# Ensure keys match the 'questions' list and values sum to 100.
folder_weights = {
    questions[0]: 50,
    questions[1]: 50
}

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