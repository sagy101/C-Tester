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
                    log(f"Failed to delete {file_path}: {e}", level="error")


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


def parse_submit_errors(error_file="submit_error.txt") -> dict[str, str]:
    """Reads the submit_error.txt file and returns a dict mapping student ID to error reason."""
    errors = {}
    if not os.path.exists(error_file):
        log(f"'{error_file}' not found. Assuming no preprocessing errors.", "info")
        return errors

    try:
        with open(error_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith("- "):
                    content = line[2:] # Remove "- "
                    # Try to extract ID assuming format "..._ID (Reason...)"
                    # Regex: Match name parts, underscore, digits (ID), space, parenthesis (reason)
                    match = re.match(r'^.+_(\d+)\s*\((.*)\)$' , content)
                    if match:
                        student_id = match.group(1)
                        reason = match.group(2).strip()
                        errors[student_id] = reason
                    else:
                        # Fallback: Maybe no reason in parenthesis? Try just ID extraction
                        match_no_reason = re.match(r'^.+_(\d+)$' , content)
                        if match_no_reason:
                            student_id = match_no_reason.group(1)
                            errors[student_id] = "Preprocessing Error (Unknown Reason)" # Generic reason
                        else:
                             log(f"Could not parse student ID or reason from error line: {line}", "warning")
    except Exception as e:
        log(f"Error reading or parsing '{error_file}': {e}", "error")

    log(f"Parsed {len(errors)} entries from '{error_file}' for penalty application.", "info")
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

        rows = []  # Will store [student_id, grade, compilation_error, timeouts, wrong_inputs_str] for each file

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
            wrong_inputs_str = extract_wrong_inputs(text) # Extract the new info
            
            rows.append([student_id, grade_value, compilation_error, timeouts, wrong_inputs_str])

        # Create a DataFrame with the new column
        df = pd.DataFrame(rows, columns=["ID_number", "Grade", "Compilation_Error", "Timeouts", "Wrong_Inputs"])

        # Write the per-question Excel
        output_excel = os.path.join(parent, f"{parent}_grades_to_upload.xlsx")
        df.to_excel(output_excel, index=False)
        log(f"Created file: {output_excel} with {len(df)} records.", level="success")

        folder_data[parent] = df

    return folder_data


def compute_final_grades(folder_data, folder_weights, penalty: int, slim=True):
    """
    Given a dictionary mapping folder names to DataFrames (which now include extra columns)
    and corresponding weight percentages, computes the final weighted grade for each student.
    This function also renames extra columns so that they are unique per folder.
    In the final Excel, the grade column headers now include the folder weight (e.g. "Grade_Q1_25%").
    Returns a final DataFrame containing the final grade and (optionally) all additional details.
    """
    # Parse preprocessing errors for penalty application
    submission_errors = parse_submit_errors()
    
    final_df = None
    # Merge the DataFrames on 'ID_number'
    for folder, df in folder_data.items():
        weight = folder_weights.get(folder, "")
        # Rename columns to indicate the folder and include weight in the Grade column header
        df_temp = df.copy().rename(columns={
            "Grade": f"Grade_{folder}_{weight}%",
            "Compilation_Error": f"Compilation_Error_{folder}",
            "Timeouts": f"Timeouts_{folder}",
            "Wrong_Inputs": f"Wrong_Inputs_{folder}" # Rename new column
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

    final_df[grade_columns] = final_df[grade_columns].fillna(0)
    final_df[timeout_columns] = final_df[timeout_columns].fillna(0)
    for col in compile_columns:
        final_df[col] = final_df[col].fillna(False)
    for col in wrong_input_columns:
        final_df[col] = final_df[col].fillna("") # Fill missing wrong inputs with empty string

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
        if student_id in submission_errors:
            penalty_applied_count += 1
            reason = submission_errors[student_id]
            original_grade = row["Final_Grade"]
            penalized_grade = max(0, original_grade - penalty) # Use the passed penalty argument here
            final_df.loc[index, "Final_Grade"] = penalized_grade
            # Store reason and penalty amount using the passed penalty
            final_df.loc[index, "Penalty Applied"] = f"{reason} (-{penalty}%) "
            log(f"Applied penalty ({penalty}%) to ID {student_id}. Original: {original_grade:.2f}, Penalized: {penalized_grade:.2f}", "info")

    if penalty_applied_count > 0:
        log(f"Applied submission error penalty to {penalty_applied_count} students.", "warning")

    # Round the final grade
    final_df["Final_Grade"] = final_df["Final_Grade"].apply(math.ceil)

    # --- Aggregate Wrong Inputs for Final Report (ALWAYS calculate this now) --- 
    final_df["Failed Test Cases"] = ""
    for index, row in final_df.iterrows():
        failed_cases_list = []
        for col_name in wrong_input_columns:
            wrong_inputs_str = row[col_name]
            if wrong_inputs_str:
                q_name_match = re.match(r'Wrong_Inputs_(Q\d+)', col_name)
                if q_name_match:
                    q_name = q_name_match.group(1)
                    failed_cases_list.append(f"{q_name}: {wrong_inputs_str}")
        final_df.loc[index, "Failed Test Cases"] = "\n".join(failed_cases_list)

    # --- Handle Slim vs Full Output --- 
    if slim:
        # Slim output now includes ID, Failed Cases, and Grade
        final_output = final_df[["ID_number", "Failed Test Cases", "Final_Grade"]]
    else:
        # Full output includes everything else plus Failed Cases, Penalty, Grade
        excluded_cols = ["ID_number", "Failed Test Cases", "Penalty Applied", "Final_Grade"]
        other_cols = [col for col in final_df.columns if col not in excluded_cols]
        
        # Define desired column order (ID first, then others, then specific last columns)
        final_cols_order = ["ID_number"] + sorted(other_cols) + ["Failed Test Cases", "Penalty Applied", "Final_Grade"]
        
        # Ensure all columns exist before reordering
        # This check might be overly cautious if we derive other_cols correctly
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


def create_excels(grade_folders, folder_weights, penalty: int, slim=True):
    # Delete the final grades Excel file from the current directory if it exists
    final_output_excel = "final_grades.xlsx"
    if os.path.exists(final_output_excel):
        try:
            os.remove(final_output_excel)
            log(f"Deleted existing file: {final_output_excel}", level="success", verbosity=2)
        except Exception as e:
            log(f"Failed to delete {final_output_excel}: {e}", level="error")

    # Process each folder and get their DataFrames (with extra columns)
    folder_data = create_excel_for_grades(grade_folders)

    # Compute and write final grades if at least one folder was processed
    if folder_data:
        # Pass the penalty value down to compute_final_grades
        final_grades_df = compute_final_grades(folder_data, folder_weights, penalty, slim)
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

