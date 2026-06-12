import math
import os
import re
import pandas as pd
from .utils import log
from .configuration import penalty

ID_COLUMN = "ID_number"
COMMENTS_COLUMN = "Comments"
FINAL_GRADE_COLUMN = "Final_Grade"
PENALTY_APPLIED_COLUMN = "Penalty Applied"
WEIGHTED_SUBTOTAL_COLUMN = "_Weighted_Subtotal"
SUBMISSION_PENALTY_AMOUNT_COLUMN = "_Submission_Penalty_Amount"
SUBMISSION_PENALTY_COUNT_COLUMN = "_Submission_Penalty_Count"


def delete_existing_excel_files(directory):
    """
    Deletes all .xlsx files in the given directory.
    """
    if os.path.isdir(directory):
        for file in os.listdir(directory):
            if file.lower().endswith(".xlsx"):
                file_path = os.path.join(directory, file)
                try:
                    os.remove(file_path)
                    log(f"Deleted existing file: {file_path}", level="success", verbosity=2)
                except Exception as e:
                    log(f"Failed to delete {file_path}: {e}", level="error", verbosity=1)


def extract_grade(text):
    """
    Extracts the grade percentage from a block of text in the form:
        Grade: XX%
    Returns it as a float, or None if not found.
    """
    match = re.search(r'Grade:\s*(\d+(?:\.\d+)?)%', text)
    if match:
        return float(match.group(1))
    return None


def extract_compilation_error(text):
    """
    Checks if the text indicates a compilation error.
    Returns True if a compilation error is found, False otherwise.
    """
    return "Compilation error:" in text


def extract_original_compilation_error(text):
    return "Original Compilation Error: yes" in text or extract_compilation_error(text)


def extract_compilation_repair_status(text):
    match = re.search(r'^Compilation Repair:\s*(.*)$', text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def extract_compilation_repair_attempts(text):
    match = re.search(r'^Compilation Repair Attempts:\s*(\d+)', text, re.MULTILINE)
    if match:
        return int(match.group(1))
    return 0


def extract_compilation_repair_penalty(text):
    match = re.search(r'^Compilation Repair Penalty:\s*-?(\d+(?:\.\d+)?)', text, re.MULTILINE)
    if match:
        return float(match.group(1))
    return 0


def extract_compilation_repair_note(text):
    match = re.search(r'^Compilation Repair Note:\s*(.*)$', text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def extract_structural_check_status(text):
    match = re.search(r'^Structural Check:\s*(.*)$', text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def extract_structural_penalty(text):
    match = re.search(r'^Structural Penalty:\s*-?(\d+(?:\.\d+)?)', text, re.MULTILINE)
    if match:
        return float(match.group(1))
    return 0


def extract_structural_notes(text):
    match = re.search(r'^Structural Notes:\s*(.*)$', text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def extract_timeouts(text):
    """
    Extracts the number of timeouts from the text.
    Looks for a pattern like 'Timeouts: X/Y' and returns X as an integer.
    Returns 0 if no timeouts are found.
    """
    match = re.search(r'Timeouts:\s*(\d+)/\d+', text)
    if match:
        return int(match.group(1))
    return 0


def extract_wrong_inputs(text):
    """Extracts the list of wrong inputs from the text.
    Looks for a pattern like 'Wrong Inputs: input1, input2, ...'
    Returns the string content after the colon, or None if not found.
    """
    match = re.search(r'^Wrong Inputs:\s*(.*)$' , text, re.MULTILINE)
    if match:
        return match.group(1).strip() # Return the comma-separated string
    return None # Return None if the line doesn't exist


def extract_grade_calculation(text):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("(Calculated grade is:"):
            return stripped[1:-1] if stripped.endswith(")") else stripped
    return None


def extract_timeout_inputs(text):
    """Extracts the list of timeout inputs from the text.
    Looks for a pattern like 'Timeout Inputs: input1, input2, ...'
    Returns the string content after the colon, or None if not found.
    """
    match = re.search(r'^Timeout Inputs:\s*(.*)$', text, re.MULTILINE)
    if match:
        return match.group(1).strip()  # Return the comma-separated string
    return None  # Return None if the line doesn't exist


def normalize_id(id_str):
    """
    Normalize an ID string by removing non-digit characters and leading zeros.
    This helps match IDs across different formats.
    """
    # Keep only the digits
    digits_only = ''.join(c for c in str(id_str) if c.isdigit())
    # Remove leading zeros
    return digits_only.lstrip('0') if digits_only else ''


def write_text_columns(worksheet, df, columns):
    """Force selected columns to Excel text cells to preserve IDs and input lists."""
    for column_name in columns:
        if column_name not in df.columns:
            continue
        column_index = df.columns.get_loc(column_name)
        for row_index, value in enumerate(df[column_name], start=1):
            if pd.isna(value) or value == "":
                worksheet.write_blank(row_index, column_index, None)
            else:
                worksheet.write_string(row_index, column_index, str(value))


def format_grade_number(value, decimals=2):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals == 0 or numeric.is_integer():
        return f"{numeric:.0f}"
    return f"{numeric:.{decimals}f}"


def parse_grade_column_name(column_name):
    match = re.match(r"^Grade_(.+)_(\d+(?:\.\d+)?)%$", column_name)
    if not match:
        return None, None
    return match.group(1), float(match.group(2))


def calculate_submission_penalty(reason, penalty_value, per_error_penalty):
    if not reason:
        return 0, 0, ""
    if per_error_penalty:
        error_count = len([issue for issue in reason.split("; ") if issue.strip()])
        total_penalty = penalty_value * error_count
        penalty_text = f"{reason} (-{format_grade_number(penalty_value)}% x {error_count} = -{format_grade_number(total_penalty)}%)"
        return error_count, total_penalty, penalty_text
    penalty_text = f"{reason} (-{format_grade_number(penalty_value)}%)"
    return 1, penalty_value, penalty_text


def build_grade_calculation_comment(
    row,
    grade_columns,
    repair_penalty_columns,
    structural_penalty_columns,
    weighted_subtotal,
    final_grade,
):
    lines = ["Grade Calculation:"]
    for grade_column in grade_columns:
        question_name, weight = parse_grade_column_name(grade_column)
        if question_name is None:
            continue
        grade_value = float(row[grade_column])
        contribution = grade_value * weight / 100
        notes = [
            note
            for note in [
                repair_calculation_note(row, question_name, repair_penalty_columns),
                structural_calculation_note(row, question_name, structural_penalty_columns),
            ]
            if note
        ]
        note_text = f" ({'; '.join(notes)})" if notes else ""
        lines.append(
            f"{question_name}: {format_grade_number(grade_value)} x {format_grade_number(weight)}% = "
            f"{contribution:.2f}{note_text}"
        )

    penalty_amount = float(row.get(SUBMISSION_PENALTY_AMOUNT_COLUMN, 0) or 0)
    penalty_count = int(row.get(SUBMISSION_PENALTY_COUNT_COLUMN, 0) or 0)
    lines.append(f"Weighted subtotal: {float(weighted_subtotal):.2f}")
    if penalty_amount:
        if penalty_count > 1:
            per_issue_penalty = penalty_amount / penalty_count
            lines.append(
                f"Submission penalty: -{format_grade_number(per_issue_penalty)} x {penalty_count} = "
                f"-{format_grade_number(penalty_amount)}"
            )
        else:
            lines.append(f"Submission penalty: -{format_grade_number(penalty_amount)}")
    post_penalty = max(0, float(weighted_subtotal) - penalty_amount)
    lines.append(f"Final grade: ceil(max(0, {post_penalty:.2f})) = {format_grade_number(final_grade, decimals=0)}")
    return "\n".join(lines)


def repair_calculation_note(row, question_name, repair_penalty_columns):
    penalty_column = f"Compilation_Repair_Penalty_{question_name}"
    if penalty_column not in repair_penalty_columns:
        return ""
    repair_penalty_value = float(row.get(penalty_column, 0) or 0)
    if repair_penalty_value <= 0:
        return ""
    return f"includes compile repair penalty -{format_grade_number(repair_penalty_value)}"


def structural_calculation_note(row, question_name, structural_penalty_columns):
    penalty_column = f"Structural_Penalty_{question_name}"
    if penalty_column not in structural_penalty_columns:
        return ""
    structural_penalty_value = float(row.get(penalty_column, 0) or 0)
    if structural_penalty_value <= 0:
        return ""
    return f"includes structural penalty -{format_grade_number(structural_penalty_value)}"


def parse_submit_errors(error_file="submit_error.txt") -> dict[str, str]:
    """
    Reads the submit_error.txt file and returns a dict mapping student ID to error reason.
    New format (single line per submission):
    - submission_name:  * error1 * error2
    """
    errors = {}
    if not os.path.exists(error_file):
        log(f"'{error_file}' not found. Assuming no preprocessing errors.", "info")
        return errors

    try:
        with open(error_file, 'r', encoding="utf-8") as f:
            lines = f.readlines()
            
            # Skip the header line
            start_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("Submissions with processing errors/warnings:"):
                    start_idx = i + 1
                    break
            
            # Process each line (one submission per line)
            for i in range(start_idx, len(lines)):
                line = lines[i].strip()
                
                # Lines starting with "- " are submission entries
                if line.startswith("- "):
                    # Split the line into submission name and issues
                    parts = line[2:].split(":", 1)  # Remove "- " and split at the submission/issues separator
                    
                    if len(parts) < 2:
                        log(f"Invalid line format (missing colon): {line}", "warning")
                        continue
                        
                    submission_name = parts[0].strip()
                    issues_part = parts[1].strip()
                    
                    # Extract ID from submission name
                    # Try multiple ID extraction patterns
                    # Pattern 1: Standard "_123456" at the end
                    match = re.search(r'_(\d{5,12})(?:\.(?:zip|rar))?$', submission_name)
                    
                    # Pattern 2: Look for submission ID patterns like 633190_assignsubmission_file_HW1_315406280
                    if not match:
                        match = re.search(r'(\d{5,12})(?:\.(?:zip|rar|c))?$', submission_name)
                    
                    # Pattern 3: More aggressive - find any 5+ digit number that could be an ID
                    if not match:
                        match = re.search(r'_(\d{5,12})', submission_name)
                    
                    if match:
                        current_id = match.group(1)
                        # Normalize the ID
                        normalized_id = normalize_id(current_id)
                        if normalized_id:
                            # Extract all issues by splitting on "* " and removing empty entries
                            issues = [issue.strip() for issue in issues_part.split("* ") if issue.strip()]
                            
                            # Join all issues with semicolons
                            errors[normalized_id] = "; ".join(issues)
                            
                            log(f"Found ID {current_id} from submission: {submission_name}", "info", verbosity=2)
                            if issues:
                                log(f"  Issues: {', '.join(issues)}", "info", verbosity=3)
                    else:
                        log(f"Could not parse student ID from line: {line}", "warning")
                
    except Exception as e:
        log(f"Error reading or parsing '{error_file}': {e}", "error")

    # Debug output to see what IDs were extracted
    if errors:
        log(f"Parsed {len(errors)} entries from '{error_file}' for penalty application.", "info")
        log(f"IDs with errors: {', '.join(sorted(errors.keys()))}", "info", verbosity=2)
    else:
        log("No errors parsed from submit_error.txt", "warning")
    
    return errors


def create_excel_for_grades(parent_folders):
    """
    For each folder in parent_folders, reads text files from the folder/grade subfolder,
    extracts student ID from the filename, the grade from file contents, and additional
    details (compilation error flag and timeout count). It then creates an Excel file in
    that same folder for uploading to Moodle.
    Returns a dictionary mapping folder names to DataFrames containing the extracted details.
    """
    folder_data = {}
    for parent in parent_folders:
        # Delete existing .xlsx files in the parent folder
        delete_existing_excel_files(parent)

        grade_folder = os.path.join(parent, "grade")

        # Skip if the folder doesn't exist or isn't a directory
        if not os.path.isdir(grade_folder):
            log(f"Skipping '{grade_folder}' - not found or not a directory.", level="warning")
            continue

        rows = []

        for filename in os.listdir(grade_folder):
            # Process only .txt files AND skip example_student.txt
            if not filename.lower().endswith(".txt") or filename == "example_student.txt":
                continue

            # Example: filename = "id1_id2.txt" => "id1_id2"
            base_name, _ = os.path.splitext(filename)
            student_id = base_name  # use the entire base name as the student ID
            
            # Read file text
            file_path = os.path.join(grade_folder, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

            grade_value = extract_grade(text)
            compilation_error = extract_compilation_error(text)
            original_compilation_error = extract_original_compilation_error(text)
            timeouts = extract_timeouts(text)
            wrong_inputs_str = extract_wrong_inputs(text)
            grade_calculation = extract_grade_calculation(text)
            timeout_inputs_str = extract_timeout_inputs(text)  # Extract the new timeout inputs
            repair_status = extract_compilation_repair_status(text)
            repair_attempts = extract_compilation_repair_attempts(text)
            repair_penalty = extract_compilation_repair_penalty(text)
            repair_note = extract_compilation_repair_note(text)
            structural_status = extract_structural_check_status(text)
            structural_penalty = extract_structural_penalty(text)
            structural_notes = extract_structural_notes(text)
            
            rows.append([
                student_id,
                grade_value,
                compilation_error,
                original_compilation_error,
                timeouts,
                wrong_inputs_str,
                grade_calculation,
                timeout_inputs_str,
                repair_status,
                repair_attempts,
                repair_penalty,
                repair_note,
                structural_status,
                structural_penalty,
                structural_notes,
            ])

        # Create a DataFrame with the new column
        df = pd.DataFrame(rows, columns=[
            "ID_number",
            "Grade",
            "Compilation_Error",
            "Original_Compilation_Error",
            "Timeouts",
            "Wrong_Inputs",
            "Grade_Calculation",
            "Timeout_Inputs",
            "Compilation_Repair_Status",
            "Compilation_Repair_Attempts",
            "Compilation_Repair_Penalty",
            "Compilation_Repair_Note",
            "Structural_Check_Status",
            "Structural_Penalty",
            "Structural_Notes",
        ])

        # Write the per-question Excel
        output_excel = os.path.join(parent, f"{parent}_grades_to_upload.xlsx")
        with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
            worksheet = writer.sheets['Sheet1']
            write_text_columns(worksheet, df, [
                "ID_number",
                "Wrong_Inputs",
                "Grade_Calculation",
                "Timeout_Inputs",
                "Compilation_Repair_Status",
                "Compilation_Repair_Note",
                "Structural_Check_Status",
                "Structural_Notes",
            ])
        log(f"Created file: {output_excel} with {len(df)} records.", level="success")

        folder_data[parent] = df

    return folder_data


def compute_final_grades(folder_data, folder_weights, penalty: int, slim=True, per_error_penalty=False):
    """
    Given a dictionary mapping folder names to DataFrames (which now include extra columns)
    and corresponding weight percentages, computes the final weighted grade for each student.
    This function also renames extra columns so that they are unique per folder.
    In the final Excel, the grade column headers now include the folder weight (e.g. "Grade_Q1_25%").
    Returns a final DataFrame containing the final grade and (optionally) all additional details.
    """
    # Parse preprocessing errors for penalty application
    submission_errors = parse_submit_errors()
    
    # Debug output: list all IDs in the final_df
    all_student_ids = set()
    normalized_id_mapping = {}  # Maps normalized ID to original ID
    
    for folder, df in folder_data.items():
        for student_id in df["ID_number"]:
            str_id = str(student_id)
            normalized_id = normalize_id(str_id)
            all_student_ids.add(str_id)
            normalized_id_mapping[normalized_id] = str_id
            
    log(f"Found {len(all_student_ids)} unique student IDs in grade files", "info")
    log(f"Sample student IDs: {', '.join(sorted(all_student_ids)[:5])}...", "info", verbosity=2)
    
    # Check if any student IDs match the submission errors after normalization
    matching_ids = set()
    id_mapping = {}  # Maps original grade file ID to matching error ID
    
    for error_id in submission_errors.keys():
        normalized_error_id = normalize_id(error_id)
        if normalized_error_id in normalized_id_mapping:
            matching_student_id = normalized_id_mapping[normalized_error_id]
            matching_ids.add(matching_student_id)
            id_mapping[matching_student_id] = error_id
    
    log(f"Found {len(matching_ids)} matching IDs between grade files and submission errors", "info")
    if matching_ids:
        log(f"Matching IDs: {', '.join(sorted(matching_ids)[:5])}...", "info", verbosity=2)
    else:
        log("No matching IDs found between grade files and submission errors!", "warning")
    
    final_df = None
    # Merge the DataFrames on 'ID_number'
    for folder, df in folder_data.items():
        weight = folder_weights.get(folder, "")
        # Rename columns to indicate the folder and include weight in the Grade column header
        df_temp = df.copy().rename(columns={
            "Grade": f"Grade_{folder}_{weight}%",
            "Compilation_Error": f"Compilation_Error_{folder}",
            "Original_Compilation_Error": f"Original_Compilation_Error_{folder}",
            "Timeouts": f"Timeouts_{folder}",
            "Wrong_Inputs": f"Wrong_Inputs_{folder}",
            "Grade_Calculation": f"Grade_Calculation_{folder}",
            "Timeout_Inputs": f"Timeout_Inputs_{folder}",
            "Compilation_Repair_Status": f"Compilation_Repair_Status_{folder}",
            "Compilation_Repair_Attempts": f"Compilation_Repair_Attempts_{folder}",
            "Compilation_Repair_Penalty": f"Compilation_Repair_Penalty_{folder}",
            "Compilation_Repair_Note": f"Compilation_Repair_Note_{folder}",
            "Structural_Check_Status": f"Structural_Check_Status_{folder}",
            "Structural_Penalty": f"Structural_Penalty_{folder}",
            "Structural_Notes": f"Structural_Notes_{folder}",
        })
        if final_df is None:
            final_df = df_temp
        else:
            final_df = pd.merge(final_df, df_temp, on="ID_number", how="outer", validate="one_to_one")

    # Fill missing values with 0 for numeric columns and False for compilation errors.
    grade_columns = [col for col in final_df.columns if col.startswith("Grade_")]
    timeout_columns = [col for col in final_df.columns if col.startswith("Timeouts_")]
    compile_columns = [col for col in final_df.columns if col.startswith("Compilation_Error_")]
    original_compile_columns = [col for col in final_df.columns if col.startswith("Original_Compilation_Error_")]
    wrong_input_columns = [col for col in final_df.columns if col.startswith("Wrong_Inputs_")]
    grade_calculation_columns = [col for col in final_df.columns if col.startswith("Grade_Calculation_")]
    timeout_input_columns = [col for col in final_df.columns if col.startswith("Timeout_Inputs_")]  # Add new column type
    repair_status_columns = [col for col in final_df.columns if col.startswith("Compilation_Repair_Status_")]
    repair_attempt_columns = [col for col in final_df.columns if col.startswith("Compilation_Repair_Attempts_")]
    repair_penalty_columns = [col for col in final_df.columns if col.startswith("Compilation_Repair_Penalty_")]
    repair_note_columns = [col for col in final_df.columns if col.startswith("Compilation_Repair_Note_")]
    structural_status_columns = [col for col in final_df.columns if col.startswith("Structural_Check_Status_")]
    structural_penalty_columns = [col for col in final_df.columns if col.startswith("Structural_Penalty_")]
    structural_note_columns = [col for col in final_df.columns if col.startswith("Structural_Notes_")]

    final_df[grade_columns] = final_df[grade_columns].fillna(0)
    final_df[timeout_columns] = final_df[timeout_columns].fillna(0)
    final_df[repair_attempt_columns] = final_df[repair_attempt_columns].fillna(0)
    final_df[repair_penalty_columns] = final_df[repair_penalty_columns].fillna(0)
    final_df[structural_penalty_columns] = final_df[structural_penalty_columns].fillna(0)
    for col in compile_columns:
        final_df[col] = final_df[col].where(final_df[col].notna(), False).astype(bool)
    for col in original_compile_columns:
        final_df[col] = final_df[col].where(final_df[col].notna(), False).astype(bool)
    for col in wrong_input_columns:
        final_df[col] = final_df[col].fillna("")  # Fill missing wrong inputs with empty string
    for col in grade_calculation_columns:
        final_df[col] = final_df[col].fillna("")
    for col in timeout_input_columns:
        final_df[col] = final_df[col].fillna("")  # Fill missing timeout inputs with empty string
    for col in repair_status_columns + repair_note_columns:
        final_df[col] = final_df[col].fillna("")
    for col in structural_status_columns + structural_note_columns:
        final_df[col] = final_df[col].fillna("")

    # Calculate initial final weighted grade
    final_df["Final_Grade"] = 0
    for folder, weight in folder_weights.items():
        grade_column = f"Grade_{folder}_{weight}%"
        if grade_column in final_df.columns:
            final_df["Final_Grade"] += final_df[grade_column] * weight / 100
    final_df[WEIGHTED_SUBTOTAL_COLUMN] = final_df[FINAL_GRADE_COLUMN]

    # Apply Penalty
    final_df[PENALTY_APPLIED_COLUMN] = "" # Initialize empty column
    final_df[SUBMISSION_PENALTY_AMOUNT_COLUMN] = 0.0
    final_df[SUBMISSION_PENALTY_COUNT_COLUMN] = 0
    penalty_applied_count = 0

    for index, row in final_df.iterrows():
        student_id = str(row["ID_number"]) # Ensure comparison as string
        
        # Check if this ID has a matching error ID through normalization
        if student_id in id_mapping:
            error_id = id_mapping[student_id]
            reason = submission_errors[error_id]
            penalty_applied_count += 1
            original_grade = row["Final_Grade"]
            error_count, total_penalty, penalty_text = calculate_submission_penalty(reason, penalty, per_error_penalty)
            penalized_grade = max(0, original_grade - total_penalty)
            log(
                f"Applied penalty ({format_grade_number(total_penalty)}%) to ID {student_id} "
                f"(matched to error ID {error_id}). Original: {original_grade:.2f}, "
                f"Penalized: {penalized_grade:.2f}",
                "info",
                verbosity=2,
            )
            
            final_df.loc[index, "Final_Grade"] = penalized_grade
            final_df.loc[index, PENALTY_APPLIED_COLUMN] = penalty_text
            final_df.loc[index, SUBMISSION_PENALTY_AMOUNT_COLUMN] = total_penalty
            final_df.loc[index, SUBMISSION_PENALTY_COUNT_COLUMN] = error_count
        
        # Traditional matching (backward compatibility)
        elif student_id in submission_errors:
            reason = submission_errors[student_id]
            penalty_applied_count += 1
            original_grade = row["Final_Grade"]
            error_count, total_penalty, penalty_text = calculate_submission_penalty(reason, penalty, per_error_penalty)
            penalized_grade = max(0, original_grade - total_penalty)
            log(
                f"Applied penalty ({format_grade_number(total_penalty)}%) to ID {student_id}. "
                f"Original: {original_grade:.2f}, Penalized: {penalized_grade:.2f}",
                "info",
                verbosity=2,
            )
            
            final_df.loc[index, "Final_Grade"] = penalized_grade
            final_df.loc[index, PENALTY_APPLIED_COLUMN] = penalty_text
            final_df.loc[index, SUBMISSION_PENALTY_AMOUNT_COLUMN] = total_penalty
            final_df.loc[index, SUBMISSION_PENALTY_COUNT_COLUMN] = error_count

    if penalty_applied_count > 0:
        log(f"Applied submission error penalty to {penalty_applied_count} students.", "warning")
    else:
        log("No penalties were applied to any students", "warning")

    # Round the final grade
    final_df[FINAL_GRADE_COLUMN] = final_df[FINAL_GRADE_COLUMN].apply(math.ceil)

    # --- Create comprehensive Comments column with all information --- 
    final_df[COMMENTS_COLUMN] = ""
    for index, row in final_df.iterrows():
        comments_parts = [
            build_grade_calculation_comment(
                row,
                grade_columns,
                repair_penalty_columns,
                structural_penalty_columns,
                row[WEIGHTED_SUBTOTAL_COLUMN],
                row[FINAL_GRADE_COLUMN],
            )
        ]
        
        # 1. Add Failed Test Cases
        failed_cases_list = []
        for col_name in wrong_input_columns:
            wrong_inputs_str = row[col_name]
            if wrong_inputs_str:
                q_name_match = re.match(r'Wrong_Inputs_(Q\d+)', col_name)
                if q_name_match:
                    q_name = q_name_match.group(1)
                    calculation = row.get(f"Grade_Calculation_{q_name}", "")
                    timeouts = row.get(f"Timeouts_{q_name}", 0)
                    timeout_inputs = row.get(f"Timeout_Inputs_{q_name}", "")
                    failure_summary = failed_inputs_summary(wrong_inputs_str, calculation, timeouts, timeout_inputs)
                    calculation_text = f" | {calculation}" if calculation else ""
                    if failure_summary:
                        failed_cases_list.append(f"{q_name}: {failure_summary}{calculation_text}")
                    else:
                        failed_cases_list.append(f"{q_name}: {wrong_inputs_str}{calculation_text}")
        if failed_cases_list:
            comments_parts.append("Failed Test Cases:\n" + "\n".join(failed_cases_list))
        
        # 1.5 Add Compilation Errors
        compilation_errors_list = []
        for col_name in compile_columns:
            if row[col_name]:  # If there was a compilation error
                q_name_match = re.match(r'Compilation_Error_(Q\d+)', col_name)
                if q_name_match:
                    q_name = q_name_match.group(1)
                    compilation_errors_list.append(f"Compilation error on {q_name}")
        if compilation_errors_list:
            comments_parts.append("Compilation Errors:\n" + "\n".join(compilation_errors_list))

        repair_notes_list = []
        for col_name in repair_note_columns:
            repair_note = row[col_name]
            if repair_note:
                q_name_match = re.match(r'Compilation_Repair_Note_(Q\d+)', col_name)
                if q_name_match:
                    q_name = q_name_match.group(1)
                    status = row.get(f"Compilation_Repair_Status_{q_name}", "")
                    attempts = row.get(f"Compilation_Repair_Attempts_{q_name}", 0)
                    repair_penalty_value = row.get(f"Compilation_Repair_Penalty_{q_name}", 0)
                    if status == "fixed":
                        repair_notes_list.append(
                            f"{q_name}: fixed after {int(attempts)} attempts (-{repair_penalty_value:g}): {repair_note}"
                        )
                    else:
                        repair_notes_list.append(f"{q_name}: {repair_note}")
        if repair_notes_list:
            comments_parts.append("Compilation Repair: " + "; ".join(repair_notes_list))

        structural_notes_list = []
        for col_name in structural_status_columns:
            status = row[col_name]
            if status and status != "passed":
                q_name_match = re.match(r'Structural_Check_Status_(Q\d+)', col_name)
                if q_name_match:
                    q_name = q_name_match.group(1)
                    structural_penalty_value = row.get(f"Structural_Penalty_{q_name}", 0)
                    structural_note = row.get(f"Structural_Notes_{q_name}", "")
                    note_text = f": {structural_note}" if structural_note else ""
                    structural_notes_list.append(
                        f"{q_name}: {status} (-{structural_penalty_value:g}){note_text}"
                    )
        if structural_notes_list:
            comments_parts.append("Non-Recursive Solution Checks: " + "; ".join(structural_notes_list))
        
        # 2. Add Timeout Cases
        timeout_cases_list = []
        for col_name in timeout_input_columns:
            timeout_inputs_str = row[col_name]
            if timeout_inputs_str:
                q_name_match = re.match(r'Timeout_Inputs_(Q\d+)', col_name)
                if q_name_match:
                    q_name = q_name_match.group(1)
                    timeout_cases_list.append(f"{q_name}: {timeout_inputs_str}")
        if timeout_cases_list:
            comments_parts.append("Timeout Cases:\n" + "\n".join(timeout_cases_list))
        
        # 3. Add Penalty reason and amount
        penalty_info = row[PENALTY_APPLIED_COLUMN]
        if penalty_info:
            comments_parts.append(f"Penalty: {penalty_info}")
        
        # Join all comments with newlines
        final_df.loc[index, COMMENTS_COLUMN] = "\n\n".join(comments_parts) if comments_parts else ""

    # --- Handle Slim vs Full Output --- 
    if slim:
        # Slim output now includes ID, Comments, and Grade
        final_output = final_df[[ID_COLUMN, COMMENTS_COLUMN, FINAL_GRADE_COLUMN]]
    else:
        # Full output includes everything else plus Comments, Penalty, Grade
        excluded_cols = [
            ID_COLUMN,
            COMMENTS_COLUMN,
            PENALTY_APPLIED_COLUMN,
            FINAL_GRADE_COLUMN,
            WEIGHTED_SUBTOTAL_COLUMN,
            SUBMISSION_PENALTY_AMOUNT_COLUMN,
            SUBMISSION_PENALTY_COUNT_COLUMN,
        ]
        other_cols = [col for col in final_df.columns if col not in excluded_cols]
        
        # Define desired column order (ID first, then others, then specific last columns)
        final_cols_order = [ID_COLUMN] + sorted(other_cols) + [COMMENTS_COLUMN, PENALTY_APPLIED_COLUMN, FINAL_GRADE_COLUMN]
        
        # Ensure all columns exist before reordering
        if all(col in final_df.columns for col in final_cols_order):
             final_output = final_df[final_cols_order]
        else:
            log("Warning: Columns mismatch during final reordering, using default order.", "warning")
            # Ensure ID is still first even in fallback
            cols = list(final_df.columns)
            if ID_COLUMN in cols:
                cols.remove(ID_COLUMN)
                final_output = final_df[[ID_COLUMN] + cols]
            else:
                final_output = final_df 

    return final_output


def build_summary_tables(final_grades_df, folder_data, folder_weights=None, top_wrong_inputs=10):
    folder_weights = folder_weights or {}
    return {
        "overall": build_overall_summary(final_grades_df, folder_data),
        "per_question": build_per_question_summary(folder_data, folder_weights, top_wrong_inputs),
        "grade_distribution": build_grade_distribution_table(numeric_series(final_grades_df.get(FINAL_GRADE_COLUMN, []))),
        "top_wrong_inputs": build_top_wrong_inputs_table(folder_data, top_wrong_inputs),
        "attention_needed": build_attention_needed_table(final_grades_df, folder_data),
    }


def build_overall_summary(final_grades_df, folder_data):
    final_grades = numeric_series(final_grades_df.get(FINAL_GRADE_COLUMN, []))
    metrics = [
        ("Students graded", int(len(final_grades_df))),
        ("Average final grade", grade_stat(final_grades, "mean")),
        ("Median final grade", grade_stat(final_grades, "median")),
        ("Std dev final grade", grade_stat(final_grades, "std")),
        ("Minimum final grade", grade_stat(final_grades, "min")),
        ("Maximum final grade", grade_stat(final_grades, "max")),
        ("Pass rate (>=60)", percent_stat((final_grades >= 60).sum(), len(final_grades))),
        ("Perfect final grades", int((final_grades == 100).sum()) if not final_grades.empty else 0),
        ("Zero final grades", int((final_grades == 0).sum()) if not final_grades.empty else 0),
        ("Submission penalties applied", count_submission_penalties(final_grades_df)),
        ("Students with compilation errors", count_students_with_any(folder_data, "Compilation_Error", bool)),
        ("Question compilation errors", sum(count_truthy(df, "Compilation_Error") for df in folder_data.values())),
        ("Students with original compilation errors", count_students_with_any(folder_data, "Original_Compilation_Error", bool)),
        ("LLM compile repairs", sum(count_equal(df, "Compilation_Repair_Status", "fixed") for df in folder_data.values())),
        ("Students with timeouts", count_students_with_any(folder_data, "Timeouts", is_positive)),
        ("Total timeouts", sum(sum_numeric(df, "Timeouts") for df in folder_data.values())),
        ("Non-recursive penalties", sum(count_positive(df, "Structural_Penalty") for df in folder_data.values())),
    ]
    return pd.DataFrame(metrics, columns=["Metric", "Value"])


def build_per_question_summary(folder_data, folder_weights, top_wrong_inputs):
    rows = []
    for question, df in folder_data.items():
        grades = numeric_series(df.get("Grade", []))
        rows.append({
            "Question": question,
            "Weight": folder_weights.get(question, ""),
            "Students": int(len(df)),
            "Average": grade_stat(grades, "mean"),
            "Median": grade_stat(grades, "median"),
            "StdDev": grade_stat(grades, "std"),
            "Min": grade_stat(grades, "min"),
            "Max": grade_stat(grades, "max"),
            "Pass_Rate": percent_stat((grades >= 60).sum(), len(grades)),
            "Perfect": int((grades == 100).sum()) if not grades.empty else 0,
            "Zero": int((grades == 0).sum()) if not grades.empty else 0,
            "Compilation_Errors": count_truthy(df, "Compilation_Error"),
            "Original_Compilation_Errors": count_truthy(df, "Original_Compilation_Error"),
            "Compile_Repairs": count_equal(df, "Compilation_Repair_Status", "fixed"),
            "Students_With_Timeouts": count_positive(df, "Timeouts"),
            "Total_Timeouts": sum_numeric(df, "Timeouts"),
            "Non_Recursive_Penalties": count_positive(df, "Structural_Penalty"),
            "Top_Wrong_Inputs": top_wrong_inputs_text(df, limit=top_wrong_inputs),
        })
    return pd.DataFrame(rows)


def build_grade_distribution_table(final_grades):
    buckets = [
        ("<60", final_grades < 60),
        ("60-69", (final_grades >= 60) & (final_grades < 70)),
        ("70-79", (final_grades >= 70) & (final_grades < 80)),
        ("80-89", (final_grades >= 80) & (final_grades < 90)),
        ("90-100", (final_grades >= 90) & (final_grades <= 100)),
    ]
    return pd.DataFrame(
        [{"Bucket": label, "Students": int(mask.sum())} for label, mask in buckets],
        columns=["Bucket", "Students"],
    )


def build_top_wrong_inputs_table(folder_data, limit=10):
    rows = []
    for question, df in folder_data.items():
        counts = wrong_input_counts(df)
        denominator = max(int(len(df)), 1)
        for input_value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]:
            rows.append({
                "Question": question,
                "Input": input_value,
                "Failed_Students": count,
                "Failure_Rate": percent_stat(count, denominator),
            })
    return pd.DataFrame(rows, columns=["Question", "Input", "Failed_Students", "Failure_Rate"])


def build_attention_needed_table(final_grades_df, folder_data):
    rows = []
    final_grade_by_id = final_grade_lookup(final_grades_df)
    attention_ids = attention_student_ids(final_grades_df)
    per_student_reasons = {student_id: [] for student_id in attention_ids}
    add_final_grade_attention(per_student_reasons, final_grades_df, attention_ids)
    add_submission_penalty_attention(per_student_reasons, final_grades_df, attention_ids)
    for question, df in folder_data.items():
        for _, row in df.iterrows():
            student_id = str(row.get(ID_COLUMN, ""))
            if student_id not in attention_ids:
                continue
            question_reason = attention_question_reason(question, row)
            if question_reason:
                per_student_reasons[student_id].append(question_reason)

    for student_id in sorted(attention_ids, key=natural_id_sort_key):
        rows.append({
            "ID_number": student_id,
            "Final_Grade": final_grade_by_id.get(student_id, ""),
            "Reason": attention_score_reason(final_grade_by_id.get(student_id, ""), final_grades_df),
            "Details": "; ".join(per_student_reasons.get(student_id, [])),
        })
    return pd.DataFrame(rows, columns=["ID_number", "Final_Grade", "Reason", "Details"])


def attention_student_ids(final_grades_df):
    if ID_COLUMN not in final_grades_df.columns or FINAL_GRADE_COLUMN not in final_grades_df.columns:
        return set()
    final_grades = numeric_series(final_grades_df[FINAL_GRADE_COLUMN])
    if final_grades.empty:
        return set()
    median_grade = float(final_grades.median())
    threshold = median_grade - 30
    selected = final_grades_df[
        (pd.to_numeric(final_grades_df[FINAL_GRADE_COLUMN], errors="coerce") < 50)
        | (pd.to_numeric(final_grades_df[FINAL_GRADE_COLUMN], errors="coerce") <= threshold)
    ]
    return {str(student_id) for student_id in selected[ID_COLUMN]}


def attention_score_reason(final_grade, final_grades_df):
    try:
        numeric_grade = float(final_grade)
    except (TypeError, ValueError):
        return "Needs review"
    median_grade = numeric_series(final_grades_df.get(FINAL_GRADE_COLUMN, [])).median()
    if numeric_grade < 50:
        return "Final grade below 50"
    if numeric_grade <= median_grade - 30:
        return f"Final grade at least 30 points below median ({format_grade_number(median_grade)})"
    return "Needs review"


def natural_id_sort_key(value):
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(value)))


def add_final_grade_attention(per_student_reasons, final_grades_df, attention_ids):
    if FINAL_GRADE_COLUMN not in final_grades_df.columns:
        return
    for _, row in final_grades_df.iterrows():
        student_id = str(row.get(ID_COLUMN, ""))
        if student_id in attention_ids and float(row.get(FINAL_GRADE_COLUMN, 0) or 0) == 0:
            per_student_reasons[student_id].append("Overall: final grade is 0")


def add_submission_penalty_attention(per_student_reasons, final_grades_df, attention_ids):
    if ID_COLUMN not in final_grades_df.columns:
        return
    for _, row in final_grades_df.iterrows():
        student_id = str(row.get(ID_COLUMN, ""))
        if student_id not in attention_ids:
            continue
        penalty_text = submission_penalty_text(row)
        if penalty_text:
            per_student_reasons[student_id].append(f"Submission penalty: {penalty_text}")


def attention_question_reason(question, row):
    details = []
    grade = row.get("Grade", "")
    if is_number_below(grade, 60):
        details.append(f"score {format_grade_number(grade)}")
    failure_summary = failed_inputs_summary(
        row.get("Wrong_Inputs", ""),
        row.get("Grade_Calculation", ""),
        row.get("Timeouts", 0),
        row.get("Timeout_Inputs", ""),
    )
    if failure_summary:
        details.append(failure_summary)
    if bool(row.get("Compilation_Error", False)):
        details.append("compilation error")
    if str(row.get("Compilation_Repair_Status", "")).lower() == "fixed":
        details.append("compile repaired")
    if is_positive(row.get("Structural_Penalty", 0)):
        structural_note = row.get("Structural_Notes", "")
        note_text = f": {structural_note}" if structural_note else ""
        details.append(f"non-recursive penalty -{format_grade_number(row.get('Structural_Penalty', 0))}{note_text}")
    return f"{question}: {', '.join(details)}" if details else ""


def is_number_below(value, threshold):
    try:
        return float(value) < threshold
    except (TypeError, ValueError):
        return False


def submission_penalty_text(row):
    if PENALTY_APPLIED_COLUMN in row and str(row.get(PENALTY_APPLIED_COLUMN, "") or "").strip():
        return str(row.get(PENALTY_APPLIED_COLUMN, ""))
    comments = str(row.get(COMMENTS_COLUMN, "") or "")
    match = re.search(r"Penalty:\s*(.*)", comments)
    return match.group(1).strip() if match else ""


def final_grade_lookup(final_grades_df):
    if ID_COLUMN not in final_grades_df.columns or FINAL_GRADE_COLUMN not in final_grades_df.columns:
        return {}
    return {
        str(row[ID_COLUMN]): row[FINAL_GRADE_COLUMN]
        for _, row in final_grades_df[[ID_COLUMN, FINAL_GRADE_COLUMN]].iterrows()
    }


def numeric_series(values):
    return pd.to_numeric(pd.Series(values), errors="coerce").dropna()


def grade_stat(series, stat_name):
    if series.empty:
        return ""
    if stat_name == "std":
        value = series.std(ddof=0)
    else:
        value = getattr(series, stat_name)()
    return round(float(value), 2)


def percent_stat(count, total):
    if not total:
        return ""
    return round(float(count) * 100 / float(total), 2)


def count_submission_penalties(final_grades_df):
    if PENALTY_APPLIED_COLUMN in final_grades_df.columns:
        return int(final_grades_df[PENALTY_APPLIED_COLUMN].fillna("").astype(str).str.strip().ne("").sum())
    if COMMENTS_COLUMN in final_grades_df.columns:
        return int(final_grades_df[COMMENTS_COLUMN].fillna("").astype(str).str.contains("Penalty:").sum())
    return 0


def count_truthy(df, column_name):
    if column_name not in df.columns:
        return 0
    return int(df[column_name].fillna(False).astype(bool).sum())


def count_equal(df, column_name, expected_value):
    if column_name not in df.columns:
        return 0
    return int(df[column_name].fillna("").astype(str).str.lower().eq(expected_value.lower()).sum())


def count_positive(df, column_name):
    if column_name not in df.columns:
        return 0
    return int((pd.to_numeric(df[column_name], errors="coerce").fillna(0) > 0).sum())


def sum_numeric(df, column_name):
    if column_name not in df.columns:
        return 0
    return int(pd.to_numeric(df[column_name], errors="coerce").fillna(0).sum())


def count_students_with_any(folder_data, column_name, predicate):
    student_ids = set()
    for df in folder_data.values():
        if column_name not in df.columns or ID_COLUMN not in df.columns:
            continue
        for _, row in df.iterrows():
            if predicate(row.get(column_name)):
                student_ids.add(str(row[ID_COLUMN]))
    return len(student_ids)


def is_positive(value):
    try:
        return float(value or 0) > 0
    except (TypeError, ValueError):
        return False


def top_wrong_inputs_text(df, limit=5):
    counts = wrong_input_counts(df)
    if not counts:
        return ""
    top_items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return "; ".join(f"{input_value} ({count})" for input_value, count in top_items)


def wrong_input_counts(df):
    if "Wrong_Inputs" not in df.columns:
        return {}
    counts = {}
    for wrong_inputs in df["Wrong_Inputs"].fillna(""):
        for wrong_input in split_input_list(wrong_inputs):
            counts[wrong_input] = counts.get(wrong_input, 0) + 1
    return counts


def split_input_list(value):
    return [item.strip() for item in str(value).split(",") if item.strip()]


def failed_inputs_summary(wrong_inputs, grade_calculation="", timeouts=0, timeout_inputs=""):
    wrong_input_list = split_input_list(wrong_inputs)
    timeout_input_list = split_input_list(timeout_inputs)
    correct_count, total_count = parse_correct_total(grade_calculation)
    failed_count = len(wrong_input_list) + safe_int(timeouts)
    if total_count:
        failed_count = max(failed_count, total_count - correct_count)
    if not wrong_input_list and not timeout_input_list:
        return ""

    examples = wrong_input_examples(wrong_input_list, timeout_input_list)
    if total_count and failed_count >= total_count:
        return f"failed all {total_count} inputs{examples}"
    if total_count and failed_count / total_count >= 0.9:
        passed_count = max(total_count - failed_count, 0)
        return f"failed {failed_count}/{total_count} inputs; passed only {passed_count}{examples}"
    if total_count:
        return f"failed {failed_count}/{total_count} inputs{examples}"
    return f"failed inputs: {', '.join(wrong_input_list)}"


def parse_correct_total(grade_calculation):
    match = re.search(r"(\d+)\s*/\s*(\d+)\s+correct", str(grade_calculation or ""))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def safe_int(value):
    try:
        if pd.isna(value):
            return 0
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def wrong_input_examples(wrong_inputs, timeout_inputs, limit=5):
    examples = wrong_inputs[:limit]
    if not examples and timeout_inputs:
        examples = [f"{input_value} (timeout)" for input_value in timeout_inputs[:limit]]
    if not examples:
        return ""
    suffix = "..." if len(wrong_inputs) + len(timeout_inputs) > limit else ""
    return f" (examples: {', '.join(examples)}{suffix})"


def write_summary_dashboard(writer, workbook, summary_tables):
    worksheet = workbook.add_worksheet("Summary")
    writer.sheets["Summary"] = worksheet
    title_format = workbook.add_format({"bold": True, "font_size": 14})
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1})
    section_rows = {}
    current_row = 0

    for title, key in [
        ("Overall Metrics", "overall"),
        ("Per-Question Metrics", "per_question"),
        ("Final Grade Distribution", "grade_distribution"),
        ("Top Wrong Inputs", "top_wrong_inputs"),
        ("Attention Needed", "attention_needed"),
    ]:
        section_rows[key] = current_row
        current_row = write_summary_section(
            worksheet,
            summary_tables[key],
            title,
            current_row,
            title_format,
            header_format,
        )

    for column_index in range(0, 18):
        worksheet.set_column(column_index, column_index, 18)
    worksheet.set_column(0, 0, 24)
    worksheet.set_column(1, 1, 24)
    worksheet.set_column(2, 2, 18)
    worksheet.set_column(3, 3, 48)
    worksheet.freeze_panes(1, 0)
    add_summary_charts(workbook, worksheet, summary_tables, section_rows)


def format_grades_worksheet(workbook, worksheet, df):
    for i, _col in enumerate(df.columns):
        worksheet.set_column(i, i, 20)

    text_columns = [
        col for col in df.columns
        if col == ID_COLUMN
        or col in (COMMENTS_COLUMN, PENALTY_APPLIED_COLUMN)
        or col.startswith("Wrong_Inputs_")
        or col.startswith("Grade_Calculation_")
        or col.startswith("Timeout_Inputs_")
        or col.startswith("Compilation_Repair_Status_")
        or col.startswith("Compilation_Repair_Note_")
    ]
    write_text_columns(worksheet, df, text_columns)

    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#D9E1F2',
        'border': 1
    })
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_format)


def write_summary_section(worksheet, df, title, start_row, title_format, header_format):
    worksheet.write(start_row, 0, title, title_format)
    header_row = start_row + 1
    for column_index, column_name in enumerate(df.columns):
        worksheet.write(header_row, column_index, column_name, header_format)
    for row_offset, row in enumerate(df.itertuples(index=False), start=1):
        for column_index, value in enumerate(row):
            worksheet.write(header_row + row_offset, column_index, value)
    return header_row + len(df) + 3


def add_summary_charts(workbook, worksheet, summary_tables, section_rows):
    add_grade_distribution_chart(workbook, worksheet, summary_tables["grade_distribution"], section_rows["grade_distribution"])
    add_question_average_chart(workbook, worksheet, summary_tables["per_question"], section_rows["per_question"])
    add_issue_counts_chart(workbook, worksheet, summary_tables["per_question"], section_rows["per_question"])


def add_grade_distribution_chart(workbook, worksheet, df, start_row):
    if df.empty:
        return
    chart = workbook.add_chart({"type": "column"})
    first_data_row = start_row + 2
    last_data_row = first_data_row + len(df) - 1
    chart.add_series({
        "name": "Students",
        "categories": ["Summary", first_data_row, 0, last_data_row, 0],
        "values": ["Summary", first_data_row, 1, last_data_row, 1],
    })
    chart.set_title({"name": "Final Grade Distribution"})
    chart.set_legend({"none": True})
    worksheet.insert_chart(start_row, 5, chart, {"x_scale": 1.2, "y_scale": 1.0})


def add_question_average_chart(workbook, worksheet, df, start_row):
    if df.empty:
        return
    chart = workbook.add_chart({"type": "column"})
    first_data_row = start_row + 2
    last_data_row = first_data_row + len(df) - 1
    chart.add_series({
        "name": "Average",
        "categories": ["Summary", first_data_row, 0, last_data_row, 0],
        "values": ["Summary", first_data_row, 3, last_data_row, 3],
    })
    chart.add_series({
        "name": "Median",
        "categories": ["Summary", first_data_row, 0, last_data_row, 0],
        "values": ["Summary", first_data_row, 4, last_data_row, 4],
    })
    chart.set_title({"name": "Per-Question Average and Median"})
    worksheet.insert_chart(start_row, 20, chart, {"x_scale": 1.2, "y_scale": 1.0})


def add_issue_counts_chart(workbook, worksheet, df, start_row):
    if df.empty:
        return
    chart = workbook.add_chart({"type": "column"})
    first_data_row = start_row + 2
    last_data_row = first_data_row + len(df) - 1
    for name, column_index in [
        ("Compilation Errors", 11),
        ("Compile Repairs", 13),
        ("Students With Timeouts", 14),
        ("Non-Recursive Penalties", 16),
    ]:
        chart.add_series({
            "name": name,
            "categories": ["Summary", first_data_row, 0, last_data_row, 0],
            "values": ["Summary", first_data_row, column_index, last_data_row, column_index],
        })
    chart.set_title({"name": "Issue Counts by Question"})
    worksheet.insert_chart(start_row + 16, 20, chart, {"x_scale": 1.2, "y_scale": 1.0})


def create_excels(grade_folders, folder_weights, penalty: int, slim=True, per_error_penalty=False):
    """
    Create the final output file final_grades.xlsx
    
    :param grade_folders: A list of folder names
    :param folder_weights: A dictionary of weights per folder
    :param penalty: The penalty to apply for submission with error
    :param slim: If True, only output the most necessary columns
    :param per_error_penalty: If True, apply penalties per error. If False, apply only once per student.
    :return: None
    """
    log('\nCreating final excel file...', level='success')
    # Delete the final grades Excel file from the current directory if it exists
    final_output_excel = "final_grades.xlsx"
    if os.path.exists(final_output_excel):
        try:
            os.remove(final_output_excel)
            log(f"Deleted existing file: {final_output_excel}", level="success", verbosity=2)
        except Exception as e:
            log(f"Failed to delete {final_output_excel}: {e}", level="error", verbosity=1)

    # Process each folder and get their DataFrames (with extra columns)
    folder_data = create_excel_for_grades(grade_folders)

    # Compute and write final grades if at least one folder was processed
    if folder_data:
        # Pass the penalty value down to compute_final_grades
        final_grades_df = compute_final_grades(folder_data, folder_weights, penalty, slim, per_error_penalty)
        student_details_df = (
            final_grades_df
            if not slim
            else compute_final_grades(folder_data, folder_weights, penalty, slim=False, per_error_penalty=per_error_penalty)
        )
        summary_tables = build_summary_tables(final_grades_df, folder_data, folder_weights)
        # Use ExcelWriter with the XlsxWriter engine to enable formatting.
        with pd.ExcelWriter(final_output_excel, engine='xlsxwriter') as writer:
            final_grades_df.to_excel(writer, sheet_name='Sheet1', index=False)
            student_details_df.to_excel(writer, sheet_name='Student Details', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Sheet1']
            details_worksheet = writer.sheets['Student Details']
            format_grades_worksheet(workbook, worksheet, final_grades_df)
            format_grades_worksheet(workbook, details_worksheet, student_details_df)

            write_summary_dashboard(writer, workbook, summary_tables)

        log(f"Created final grades Excel: {final_output_excel} with {len(final_grades_df)} records.", level="success")
    else:
        log("No valid folder data available to compute final grades.", level="warning")

