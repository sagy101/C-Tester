import os
import glob
from Utils import log # Import the log function

def clear_folder_contents(folder_path):
    """Removes all files within a given folder, but not the folder itself.
    Skips deleting 'example_student.c' and 'example_student.txt'.
    """
    if not os.path.isdir(folder_path):
        log(f"Directory not found: {folder_path}", level="warning") # Use log with warning level
        return
    for filename in os.listdir(folder_path):
        # Skip the specific example files
        if filename == "example_student.c" or filename == "example_student.txt":
            log(f"Skipping deletion of example file: {os.path.join(folder_path, filename)}", "info", verbosity=2)
            continue 
            
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
                log(f"Deleted file: {file_path}", level="info") # Use log
            # Optionally, add elif os.path.isdir(file_path): shutil.rmtree(file_path) to remove subdirectories
        except Exception as e:
            log(f'Failed to delete {file_path}. Reason: {e}', level="error") # Use log with error level

def clear_grades(questions):
    """Clears the contents of the 'grade' folder for each question."""
    log("Clearing grade folders...", level="info") # Use log
    for q_folder in questions:
        grades_path = os.path.join(q_folder, 'grade')
        clear_folder_contents(grades_path)
    log("Finished clearing grade folders.", level="success") # Use log with success level

def clear_output(questions):
    """Clears the contents of the 'output' folder, deletes 
    'original_sol_output.txt' for each question, and deletes submit_error.txt.
    """
    log("Clearing output folders, original_sol_output.txt files, and submit_error.txt...", level="info")
    
    # Delete submit_error.txt in the current directory
    if os.path.exists("submit_error.txt"):
        try:
            os.remove("submit_error.txt")
            log("Deleted submit_error.txt", level="info")
        except Exception as e:
            log(f"Failed to delete submit_error.txt. Reason: {e}", level="error")
    
    for q_folder in questions:
        # Clear contents of the output subfolder
        output_path = os.path.join(q_folder, 'output')
        clear_folder_contents(output_path)
        
        # Delete the original_sol_output.txt file in the parent question folder
        original_output_file = os.path.join(q_folder, "original_sol_output.txt")
        if os.path.exists(original_output_file):
            try:
                os.remove(original_output_file)
                log(f"Deleted original solution output file: {original_output_file}", level="info")
            except Exception as e:
                log(f"Failed to delete {original_output_file}. Reason: {e}", level="error")
        # else: File didn't exist, nothing to delete
            
    log("Finished clearing output folders, original_sol_output.txt files, and submit_error.txt.", level="success")

def clear_c_files(questions):
    """Clears the contents of the 'C' folder for each question."""
    log("Clearing C folders...", level="info") # Use log
    for q_folder in questions:
        c_path = os.path.join(q_folder, 'C')
        clear_folder_contents(c_path)
    log("Finished clearing C folders.", level="success") # Use log with success level

def clear_excels():
    """Deletes all .xlsx files in the current directory and subdirectories."""
    log("Deleting all Excel files...", level="info") # Use log
    excel_files = glob.glob('**/*.xlsx', recursive=True)
    if not excel_files:
        log("No Excel files found.", level="info") # Use log
        return
    for file_path in excel_files:
        try:
            os.remove(file_path)
            log(f"Deleted Excel file: {file_path}", level="info") # Use log
        except Exception as e:
            log(f'Failed to delete {file_path}. Reason: {e}', level="error") # Use log with error level
    log("Finished deleting Excel files.", level="success") # Use log with success level

def clear_build_files():
    """Deletes all .exe and .obj files in the current directory and subdirectories."""
    log("Deleting build files (.exe, .obj)...", level="info")
    deleted_count = 0
    errors = 0
    for pattern in ['**/*.exe', '**/*.obj']:
        files_to_delete = glob.glob(pattern, recursive=True)
        if files_to_delete:
            log(f"Found {len(files_to_delete)} files matching '{pattern}'", level="info")
            for file_path in files_to_delete:
                try:
                    os.remove(file_path)
                    log(f"Deleted build file: {file_path}", level="info")
                    deleted_count += 1
                except Exception as e:
                    log(f'Failed to delete {file_path}. Reason: {e}', level="error")
                    errors += 1
        else:
             log(f"No files found matching '{pattern}'", level="info")

    if deleted_count > 0 or errors == 0:
        log(f"Finished deleting build files. Deleted: {deleted_count}, Errors: {errors}", level="success")
    else:
         log(f"Finished deleting build files attempt. Deleted: {deleted_count}, Errors: {errors}", level="warning")

def clear_all(questions):
    """Runs clear_grades, clear_output, clear_excels, and clear_build_files."""
    log("Starting clear all operation...", level="info")
    clear_grades(questions)
    clear_output(questions)  # This will now also delete submit_error.txt
    clear_excels()
    clear_build_files()
    log("Finished clear all operation.", level="success") 