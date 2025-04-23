"""Configuration settings for the C Auto Grader."""

import os # Needed for validate_config

# Penalty points for submission errors reported in submit_error.txt
penalty = 15

# List of question folder names (must match actual folder names in the project root)
questions = ["Q1", "Q2"]

# Dictionary mapping question folder names to their weight percentage for the final grade
# Ensure keys match the 'questions' list and values sum to 100.
folder_weights = {
    questions[0]: 50,
    questions[1]: 50
}

def validate_config(questions_list, weights_dict):
    """Validates the questions list and folder_weights dictionary.

    Checks:
    1. Question folders exist.
    2. Weight keys match question list exactly.
    3. Weight values sum to 100.
    
    Returns:
        list: A list of error strings. Empty if configuration is valid.
    """
    errors = []
    # 1. Validate question folders exist
    for q_folder in questions_list:
        if not isinstance(q_folder, str) or not q_folder:
            errors.append(f"Invalid entry in 'questions' list: '{q_folder}'. Must be a non-empty string.")
            continue # Skip os.path.isdir check if entry is invalid
        # Use os.path.abspath to ensure check is relative to script location if needed
        # Assuming folders are relative to where script is run from
        if not os.path.isdir(q_folder):
            errors.append(f"Configuration error: Folder '{q_folder}' listed in 'questions' not found in the current directory.")

    # 2. Validate weights dictionary keys match questions list
    # Convert questions_list to set for comparison
    questions_set = set(q for q in questions_list if isinstance(q, str) and q) # Exclude potentially invalid entries from set
    weights_set = set(weights_dict.keys())

    if questions_set != weights_set:
        missing_in_weights = questions_set - weights_set
        extra_in_weights = weights_set - questions_set
        if missing_in_weights:
            errors.append(f"Configuration error: Weights missing for question folder(s): {', '.join(sorted(missing_in_weights))}")
        if extra_in_weights:
            errors.append(f"Configuration error: Weights defined for non-existent/unlisted question folder(s): {', '.join(sorted(extra_in_weights))}")

    # 3. Validate weights sum to 100
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