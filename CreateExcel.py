import math
import os
import re
import pandas as pd
from Utils import log


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

        rows = []  # Will store [student_id, grade, compilation_error, timeouts] for each file

        for filename in os.listdir(grade_folder):
            # Process only .txt files (adjust as needed)
            if not filename.lower().endswith(".txt"):
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
            rows.append([student_id, grade_value, compilation_error, timeouts])

        # Create a DataFrame from the rows with additional columns for error and timeouts
        df = pd.DataFrame(rows, columns=["ID_number", "Grade", "Compilation_Error", "Timeouts"])

        # Write an Excel file for the folder's grades (including extra details)
        output_excel = os.path.join(parent, f"{parent}_grades_to_upload.xlsx")
        # You can similarly use ExcelWriter for individual folder files if you want to format them
        df.to_excel(output_excel, index=False)
        log(f"Created file: {output_excel} with {len(df)} records.", level="success")

        folder_data[parent] = df

    return folder_data


def compute_final_grades(folder_data, folder_weights, slim=True):
    """
    Given a dictionary mapping folder names to DataFrames (which now include extra columns)
    and corresponding weight percentages, computes the final weighted grade for each student.
    This function also renames extra columns so that they are unique per folder.
    In the final Excel, the grade column headers now include the folder weight (e.g. "Grade_Q1_25%").
    Returns a final DataFrame containing the final grade and (optionally) all additional details.
    """
    final_df = None
    # Merge the DataFrames on 'ID_number'
    for folder, df in folder_data.items():
        weight = folder_weights.get(folder, "")
        # Rename columns to indicate the folder and include weight in the Grade column header
        df_temp = df.copy().rename(columns={
            "Grade": f"Grade_{folder}_{weight}%",
            "Compilation_Error": f"Compilation_Error_{folder}",
            "Timeouts": f"Timeouts_{folder}"
        })
        if final_df is None:
            final_df = df_temp
        else:
            final_df = pd.merge(final_df, df_temp, on="ID_number", how="outer")

    # Fill missing values with 0 for numeric columns and False for compilation errors.
    grade_columns = [col for col in final_df.columns if col.startswith("Grade_")]
    timeout_columns = [col for col in final_df.columns if col.startswith("Timeouts_")]
    compile_columns = [col for col in final_df.columns if col.startswith("Compilation_Error_")]

    final_df[grade_columns] = final_df[grade_columns].fillna(0)
    final_df[timeout_columns] = final_df[timeout_columns].fillna(0)
    for col in compile_columns:
        final_df[col] = final_df[col].fillna(False)

    # Calculate final weighted grade using only the grade columns
    final_df["Final_Grade"] = 0
    for folder, weight in folder_weights.items():
        grade_column = f"Grade_{folder}_{weight}%"
        if grade_column in final_df.columns:
            final_df["Final_Grade"] += final_df[grade_column] * weight / 100

    # Round the final grade up to the ceiling value
    final_df["Final_Grade"] = final_df["Final_Grade"].apply(math.ceil)

    if slim:
        # Option 1: If you only want to upload the final grade, select just ID and Final_Grade:
        final_output = final_df[["ID_number", "Final_Grade"]]
    else:
        # Option 2: Include all per-question details along with the final grade:
        final_output = final_df

    return final_output


def create_excels(grade_folders, folder_weights, slim=True):
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
        final_grades_df = compute_final_grades(folder_data, folder_weights, slim)
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


if __name__ == "__main__":
    # Define your parent folders here (e.g., Q1, Q2, Q3)
    grade_folders = ["Q1", "Q2", "Q3"]
    # Weight in percentage for each grade_folder
    folder_weights = {grade_folders[0]: 25, grade_folders[1]: 45, grade_folders[2]: 30}
    create_excels(grade_folders, folder_weights)
