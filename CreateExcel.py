import math
import os
import re
import pandas as pd
from Utils import log
from configuration import penalty


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
        with open(error_file, 'r') as f:
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
                    parts = line[2:].split(":")  # Remove "- " and split at colon
                    
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
                        match = re.search(r'(\d{5,12})(?:\.(?:zip|rar))?$', submission_name)
                    
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

        rows = []  # Will store [student_id, grade, compilation_error, timeouts, wrong_inputs_str, timeout_inputs_str] for each file

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
            timeouts = extract_timeouts(text)
            wrong_inputs_str = extract_wrong_inputs(text)
            timeout_inputs_str = extract_timeout_inputs(text)  # Extract the new timeout inputs
            
            rows.append([student_id, grade_value, compilation_error, timeouts, wrong_inputs_str, timeout_inputs_str])

        # Create a DataFrame with the new column
        df = pd.DataFrame(rows, columns=["ID_number", "Grade", "Compilation_Error", "Timeouts", "Wrong_Inputs", "Timeout_Inputs"])

        # Write the per-question Excel
        output_excel = os.path.join(parent, f"{parent}_grades_to_upload.xlsx")
        df.to_excel(output_excel, index=False)
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
    log(f"Sample student IDs: {', '.join(sorted(list(all_student_ids))[:5])}...", "info", verbosity=2)
    
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
        log(f"Matching IDs: {', '.join(sorted(list(matching_ids))[:5])}...", "info", verbosity=2)
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
            "Timeouts": f"Timeouts_{folder}",
            "Wrong_Inputs": f"Wrong_Inputs_{folder}",
            "Timeout_Inputs": f"Timeout_Inputs_{folder}"  # Rename new column
        })
        if final_df is None:
            final_df = df_temp
        else:
            final_df = pd.merge(final_df, df_temp, on="ID_number", how="outer")

    # Fill missing values with 0 for numeric columns and False for compilation errors.
    grade_columns = [col for col in final_df.columns if col.startswith("Grade_")]
    timeout_columns = [col for col in final_df.columns if col.startswith("Timeouts_")]
    compile_columns = [col for col in final_df.columns if col.startswith("Compilation_Error_")]
    wrong_input_columns = [col for col in final_df.columns if col.startswith("Wrong_Inputs_")]
    timeout_input_columns = [col for col in final_df.columns if col.startswith("Timeout_Inputs_")]  # Add new column type

    final_df[grade_columns] = final_df[grade_columns].fillna(0)
    final_df[timeout_columns] = final_df[timeout_columns].fillna(0)
    for col in compile_columns:
        final_df[col] = final_df[col].fillna(False)
    for col in wrong_input_columns:
        final_df[col] = final_df[col].fillna("")  # Fill missing wrong inputs with empty string
    for col in timeout_input_columns:
        final_df[col] = final_df[col].fillna("")  # Fill missing timeout inputs with empty string

    # Calculate initial final weighted grade
    final_df["Final_Grade"] = 0
    for folder, weight in folder_weights.items():
        grade_column = f"Grade_{folder}_{weight}%"
        if grade_column in final_df.columns:
            final_df["Final_Grade"] += final_df[grade_column] * weight / 100

    # Apply Penalty
    final_df["Penalty Applied"] = "" # Initialize empty column
    penalty_applied_count = 0

    for index, row in final_df.iterrows():
        student_id = str(row["ID_number"]) # Ensure comparison as string
        
        # Check if this ID has a matching error ID through normalization
        if student_id in id_mapping:
            error_id = id_mapping[student_id]
            reason = submission_errors[error_id]
            penalty_applied_count += 1
            original_grade = row["Final_Grade"]
            
            # Calculate penalty based on number of errors if per_error_penalty is True
            if per_error_penalty:
                # Count the number of separate errors (split by semicolons)
                error_list = reason.split("; ")
                error_count = len(error_list)
                total_penalty = penalty * error_count
                penalized_grade = max(0, original_grade - total_penalty)
                penalty_text = f"{reason} (-{penalty}% x {error_count} = -{total_penalty}%)"
                log(f"Applied penalty ({penalty}% x {error_count} = {total_penalty}%) to ID {student_id} (matched to error ID {error_id}). Original: {original_grade:.2f}, Penalized: {penalized_grade:.2f}", "info", verbosity=2)
            else:
                # Traditional single penalty regardless of error count
                penalized_grade = max(0, original_grade - penalty)
                penalty_text = f"{reason} (-{penalty}%)"
                log(f"Applied penalty ({penalty}%) to ID {student_id} (matched to error ID {error_id}). Original: {original_grade:.2f}, Penalized: {penalized_grade:.2f}", "info", verbosity=2)
            
            final_df.loc[index, "Final_Grade"] = penalized_grade
            final_df.loc[index, "Penalty Applied"] = penalty_text
        
        # Traditional matching (backward compatibility)
        elif student_id in submission_errors:
            reason = submission_errors[student_id]
            penalty_applied_count += 1
            original_grade = row["Final_Grade"]
            
            # Calculate penalty based on number of errors if per_error_penalty is True
            if per_error_penalty:
                # Count the number of separate errors (split by semicolons)
                error_list = reason.split("; ")
                error_count = len(error_list)
                total_penalty = penalty * error_count
                penalized_grade = max(0, original_grade - total_penalty)
                penalty_text = f"{reason} (-{penalty}% x {error_count} = -{total_penalty}%)"
                log(f"Applied penalty ({penalty}% x {error_count} = {total_penalty}%) to ID {student_id}. Original: {original_grade:.2f}, Penalized: {penalized_grade:.2f}", "info", verbosity=2)
            else:
                # Traditional single penalty regardless of error count
                penalized_grade = max(0, original_grade - penalty)
                penalty_text = f"{reason} (-{penalty}%)"
                log(f"Applied penalty ({penalty}%) to ID {student_id}. Original: {original_grade:.2f}, Penalized: {penalized_grade:.2f}", "info", verbosity=2)
            
            final_df.loc[index, "Final_Grade"] = penalized_grade
            final_df.loc[index, "Penalty Applied"] = penalty_text

    if penalty_applied_count > 0:
        log(f"Applied submission error penalty to {penalty_applied_count} students.", "warning")
    else:
        log("No penalties were applied to any students", "warning")

    # Round the final grade
    final_df["Final_Grade"] = final_df["Final_Grade"].apply(math.ceil)

    # --- Create comprehensive Comments column with all information --- 
    final_df["Comments"] = ""
    for index, row in final_df.iterrows():
        comments_parts = []
        
        # 1. Add Failed Test Cases
        failed_cases_list = []
        for col_name in wrong_input_columns:
            wrong_inputs_str = row[col_name]
            if wrong_inputs_str:
                q_name_match = re.match(r'Wrong_Inputs_(Q\d+)', col_name)
                if q_name_match:
                    q_name = q_name_match.group(1)
                    failed_cases_list.append(f"{q_name}: {wrong_inputs_str}")
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
        penalty_info = row["Penalty Applied"]
        if penalty_info:
            comments_parts.append(f"Penalty: {penalty_info}")
        
        # Join all comments with newlines
        final_df.loc[index, "Comments"] = "\n\n".join(comments_parts) if comments_parts else ""

    # --- Handle Slim vs Full Output --- 
    if slim:
        # Slim output now includes ID, Comments, and Grade
        final_output = final_df[["ID_number", "Comments", "Final_Grade"]]
    else:
        # Full output includes everything else plus Comments, Penalty, Grade
        excluded_cols = ["ID_number", "Comments", "Penalty Applied", "Final_Grade"]
        other_cols = [col for col in final_df.columns if col not in excluded_cols]
        
        # Define desired column order (ID first, then others, then specific last columns)
        final_cols_order = ["ID_number"] + sorted(other_cols) + ["Comments", "Penalty Applied", "Final_Grade"]
        
        # Ensure all columns exist before reordering
        if all(col in final_df.columns for col in final_cols_order):
             final_output = final_df[final_cols_order]
        else:
            log("Warning: Columns mismatch during final reordering, using default order.", "warning")
            # Ensure ID is still first even in fallback
            cols = list(final_df.columns)
            if "ID_number" in cols:
                cols.remove("ID_number")
                final_output = final_df[["ID_number"] + cols]
            else:
                final_output = final_df 

    return final_output


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
    log(f'\nCreating final excel file...', level='success')
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
        # Use ExcelWriter with the XlsxWriter engine to enable formatting.
        with pd.ExcelWriter(final_output_excel, engine='xlsxwriter') as writer:
            final_grades_df.to_excel(writer, sheet_name='Sheet1', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Sheet1']

            # Set each column width to 20 (adjust this value as needed)
            for i, col in enumerate(final_grades_df.columns):
                worksheet.set_column(i, i, 20)

            # Define a header format with a light blue background
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'border': 1
            })

            # Apply the header format to the first row
            for col_num, value in enumerate(final_grades_df.columns.values):
                worksheet.write(0, col_num, value, header_format)

        log(f"Created final grades Excel: {final_output_excel} with {len(final_grades_df)} records.", level="success")
    else:
        log("No valid folder data available to compute final grades.", level="warning")

