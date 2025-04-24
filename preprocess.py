import os
import zipfile
import shutil
import re
import glob
import threading
from typing import Callable, Optional

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    class tqdm:
        def __init__(self, iterable=None, *args, **kwargs):
            self.iterable = iterable
        def __iter__(self):
            return iter(self.iterable)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def update(self, n=1):
            pass

from Utils import log

def extract_main_zip(zip_filename):
    log(f"Extracting main zip file: {zip_filename}", "info")
    # Create zip directory if it doesn't exist
    if not os.path.exists('zip'):
        os.makedirs('zip')
    
    # Extract the main zip file
    with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
        zip_ref.extractall('zip')
        log(f"Found {len(zip_ref.namelist())} files in main zip", "info")

def extract_nested_zips():
    log("Extracting nested zip files...", "info")
    # Get all zip files in the zip directory
    zip_files = [f for f in os.listdir('zip') if f.endswith('.zip')]
    log(f"Found {len(zip_files)} nested zip files", "info")
    
    extracted_count = 0
    for zip_file in zip_files:
        zip_path = os.path.join('zip', zip_file)
        # Create directory with the same name as the zip (without extension)
        extract_dir = os.path.join('zip', os.path.splitext(zip_file)[0])
        os.makedirs(extract_dir, exist_ok=True)
        
        try:
            # Extract the zip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                extracted_count += 1
            
            # Delete the zip file
            os.remove(zip_path)
        except Exception as e:
            log(f"Error extracting {zip_file}: {str(e)}", "error")
    
    log(f"Successfully extracted {extracted_count} nested zip files", "success")

def organize_c_files():
    log("Organizing C files...", "info")
    total_processed = 0
    skipped_folders = 0
    skipped_no_id = 0
    processed_ids = set()
    no_c_files_folders = []
    file_problems = {}  # Dictionary to store file problems for each ID
    
    # Process each folder in the zip directory
    folders = [f for f in os.listdir('zip') if os.path.isdir(os.path.join('zip', f))]
    log(f"Found {len(folders)} folders to process", "info")
    
    for folder in folders:
        folder_path = os.path.join('zip', folder)
        if not os.path.isdir(folder_path):
            skipped_folders += 1
            continue
            
        # Extract ID number from folder name
        id_match = re.search(r'_(\d+)$', folder)
        if not id_match:
            log(f"Could not extract ID from folder name: {folder}", "warning")
            skipped_no_id += 1
            continue
        id_number = id_match.group(1)
        
        if id_number in processed_ids:
            log(f"Warning: Duplicate ID found: {id_number} in folder {folder}", "warning")
        processed_ids.add(id_number)
        
        # Process each C file in the folder
        c_files_found = False
        for file in os.listdir(folder_path):
            if file.startswith('hw') and file.endswith('.c'):
                # Extract question number
                q_match = re.search(r'q(\d+)', file)
                if not q_match:
                    log(f"Could not extract question number from file: {file}", "warning")
                    continue
                q_number = q_match.group(1)
                
                # Create Q/C directory only when needed
                dest_dir = f'Q{q_number}/C'
                os.makedirs(dest_dir, exist_ok=True)
                
                # Create new filename and destination path
                new_filename = f'{id_number}.c'
                dest_path = os.path.join(dest_dir, new_filename)
                
                # Move and rename the file
                src_path = os.path.join(folder_path, file)
                shutil.move(src_path, dest_path)
                c_files_found = True
                total_processed += 1
        
        if not c_files_found:
            log(f"No C files found in folder: {folder}", "warning")
            no_c_files_folders.append(folder)
            file_problems[id_number] = True

    # Write errors to file
    if no_c_files_folders:
        with open("preprocess_errors.txt", "w", encoding="utf-8") as f:
            f.write("Folders with no C files found:\n")
            for folder in no_c_files_folders:
                f.write(f"{folder}\n")
        log(f"Saved {len(no_c_files_folders)} errors to preprocess_errors.txt", "info")

    # Save file problems to a JSON file for the grading process
    with open("file_problems.json", "w", encoding="utf-8") as f:
        json.dump(file_problems, f, indent=2)
    log("Saved file problems information for grading process", "info")

    log("\nProcessing Summary:", "info")
    log(f"Total folders found: {len(folders)}", "info")
    log(f"Total C files processed: {total_processed}", "info")
    log(f"Unique IDs processed: {len(processed_ids)}", "info")
    log(f"Folders skipped (not a directory): {skipped_folders}", "info")
    log(f"Folders skipped (no ID): {skipped_no_id}", "info")
    if len(processed_ids) < len(folders):
        log(f"Warning: Processed fewer IDs ({len(processed_ids)}) than folders ({len(folders)})", "warning")

def prepare(zip_filename):
    try:
        # Step 1: Extract main zip
        extract_main_zip(zip_filename)
        
        # Step 2: Extract nested zips
        extract_nested_zips()
        
        # Step 3: Organize C files
        organize_c_files()
        
        # Step 4: Clean up zip directory
        shutil.rmtree('zip')
        
        log("File organization completed successfully!", "success")
        
    except Exception as e:
        log(f"An error occurred: {str(e)}", "error")
        raise

def extract_zip(zip_path, extract_to):
    """Extracts a zip file to a specified directory."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        log(f"Successfully extracted '{zip_path}' to '{extract_to}'", level="success")
        return True
    except zipfile.BadZipFile:
        log(f"Error: '{zip_path}' is not a valid zip file or is corrupted.", level="error")
        return False
    except Exception as e:
        log(f"Error extracting '{zip_path}': {e}", level="error")
        return False

def find_and_process_c_files(
    submission_folder: str,
    student_id: str,
    questions_base_path: str = ".",
    cancel_event: Optional[threading.Event] = None
) -> tuple[str, set]:
    """Finds C files (*_qN.c), renames, moves them, and reports status.

    Searches the submission_folder first. If no files found, searches all
    immediate subdirectories.

    Returns:
        tuple: (status, processed_q_numbers)
          status (str): 'ok_root', 'ok_subfolder', 'not_found'
          processed_q_numbers (set): Set of integers for successfully processed Q numbers.
    """
    processed_q_numbers = set()
    status = 'not_found'
    c_files_found_paths = []

    # 1. Search in the root submission folder
    log(f"Searching for C files in root: {submission_folder}", level="info")
    root_c_file_pattern = os.path.join(submission_folder, '*_q[0-9]*.c')
    c_files_found_paths = glob.glob(root_c_file_pattern)

    if c_files_found_paths:
        log(f"Found {len(c_files_found_paths)} C file(s) directly in {submission_folder}", level="info")
        status = 'ok_root'
    else:
        log(f"No C files found directly in {submission_folder}. Checking immediate subfolders...", level="info")
        # 2. If no files in root, search immediate subdirectories
        subdirs = []
        try:
            items = os.listdir(submission_folder)
            subdirs = [os.path.join(submission_folder, item) for item in items if os.path.isdir(os.path.join(submission_folder, item))]
        except OSError as e:
            log(f"Error listing directory {submission_folder}: {e}", level="error")
            # Cannot proceed with subfolder check, status remains 'not_found'

        if subdirs:
            log(f"Found {len(subdirs)} subfolder(s) to check.", level="info")
            for subdir in subdirs:
                log(f"Searching for C files in subfolder: {subdir}", level="info")
                subdir_c_file_pattern = os.path.join(subdir, '*_q[0-9]*.c')
                files_in_subdir = glob.glob(subdir_c_file_pattern)
                if files_in_subdir:
                    log(f"Found {len(files_in_subdir)} C file(s) in {subdir}", level="info")
                    c_files_found_paths.extend(files_in_subdir)
                    # If we find files in any subfolder, status becomes 'ok_subfolder'
                    # We don't break, collect files from all immediate subdirs
                    status = 'ok_subfolder'
        else:
             log(f"No subfolders found in {submission_folder}", level="info")

    # If no properly named files found, look for any .c files with q<number> pattern
    if not c_files_found_paths:
        # Search in root and all immediate subdirectories for any .c files
        all_c_files = []
        # Search root
        root_c_files = glob.glob(os.path.join(submission_folder, '*.c'))
        log(f"Found {len(root_c_files)} C files in root: {root_c_files}", level="info")
        all_c_files.extend(root_c_files)
        
        # Search subdirectories
        for subdir in subdirs:
            subdir_c_files = glob.glob(os.path.join(subdir, '*.c'))
            if subdir_c_files:
                log(f"Found {len(subdir_c_files)} C files in subdir {subdir}: {subdir_c_files}", level="info")
            all_c_files.extend(subdir_c_files)
        
        log(f"Total C files found before filtering: {len(all_c_files)}", level="info")
        
        # Filter for files containing 'q' followed by a number
        wrong_named_files = []
        for c_file in all_c_files:
            filename = os.path.basename(c_file)
            # Check both patterns: 'q' followed by number anywhere, or exact 'q<number>.c'
            if re.search(r'q\d+', filename, re.IGNORECASE) or re.match(r'^q\d+\.c$', filename, re.IGNORECASE):
                wrong_named_files.append(c_file)
                log(f"Found incorrectly named file: {filename}", level="info")
            else:
                log(f"File did not match pattern: {filename}", level="info")
        
        if wrong_named_files:
            c_files_found_paths = wrong_named_files
            status = 'found_wrong_name'
            log(f"Found {len(wrong_named_files)} C file(s) with incorrect naming pattern: {[os.path.basename(f) for f in wrong_named_files]}", level="info")
        else:
            # Double check - list all .c files that were found but didn't match
            log(f"No matching files found. All C files found were: {[os.path.basename(f) for f in all_c_files]}", level="warning")
            status = 'not_found'
            log(f"No C files with question numbers found in any format", level="warning")

    # --- Filter out example file BEFORE processing --- 
    original_count = len(c_files_found_paths)
    c_files_found_paths = [p for p in c_files_found_paths if os.path.basename(p) != "example_student.c"]
    if len(c_files_found_paths) < original_count:
        log("Ignoring 'example_student.c' found during preprocessing search.", "info")

    # Check for cancellation before processing found files
    if cancel_event and cancel_event.is_set():
        log("File processing cancelled before starting.", "warning")
        return "cancelled", processed_q_numbers

    # 3. Process all found C files (from root or subfolders)
    if not c_files_found_paths:
        log(f"No C files matching pattern '*_qN.c' found for submission ID {student_id} in {submission_folder} or its subfolders.", level="warning")
        return 'not_found', processed_q_numbers # Return current status and empty set

    log(f"Processing {len(c_files_found_paths)} found C file(s) for ID {student_id}", level="info")
    for c_file_path in c_files_found_paths:
        # --- Cancellation Check within loop --- 
        if cancel_event and cancel_event.is_set():
            log(f"File processing cancelled mid-way for ID {student_id}.", "warning")
            status = "cancelled" # Mark status as cancelled
            break # Exit loop

        filename = os.path.basename(c_file_path)
        # Extract question number: matches _q<digits>.c at the end OR just q<digits>.c
        match = re.search(r'(?:_)?q(\d+)\.c$', filename, re.IGNORECASE)
        if match:
            q_number_str = match.group(1)
            try:
                q_number = int(q_number_str)
                target_folder = os.path.join(questions_base_path, f"Q{q_number}", "C")
                target_filename = f"{student_id}.c"
                target_path = os.path.join(target_folder, target_filename)

                try:
                    os.makedirs(target_folder, exist_ok=True)
                    shutil.copy2(c_file_path, target_path) # Use copy2 to preserve metadata
                    log(f"Copied and renamed '{filename}' to '{target_path}'", level="success")
                    processed_q_numbers.add(q_number)
                except Exception as e:
                    log(f"Error copying '{c_file_path}' to '{target_path}': {e}", level="error")
                    # If copy fails, don't add to processed set
            except ValueError:
                 log(f"Could not convert question number '{q_number_str}' to integer in '{filename}'. Skipping.", level="warning")
        else:
            log(f"Could not extract question number from filename '{filename}' (path: {c_file_path}). Skipping.", level="warning")

    # Final check on status: If files were found but none were processed successfully
    if status == "cancelled":
        pass # Keep status as cancelled
    elif status != 'not_found' and not processed_q_numbers:
        status = 'not_found'
    elif status == 'not_found' and processed_q_numbers:
        status = 'ok_subfolder'

    return status, processed_q_numbers

def preprocess_submissions(
    zip_path: str,
    questions_list: list,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
):
    """
    Main function to preprocess submissions:
    1. Extracts the main zip.
    2. Extracts inner student zips.
    3. Finds, renames, and moves C files.
    4. Cleans up intermediate files/folders.
    5. Reports submissions with issues.
    """
    log(f"Starting preprocessing for '{zip_path}'...", level="info")

    # Extract expected question numbers (set of integers)
    expected_qs_set = set()
    for q_name in questions_list:
        match = re.match(r'Q(\d+)', q_name, re.IGNORECASE)
        if match:
            expected_qs_set.add(int(match.group(1)))
        else:
            log(f"Warning: Could not parse question number from folder name '{q_name}' in config. Skipping for completeness check.", level="warning")
    log(f"Expecting questions: {sorted(list(expected_qs_set))}", level="info")

    base_extract_folder = "_extracted_submissions" # Temporary folder

    # Clean up previous extraction folder if it exists
    if os.path.isdir(base_extract_folder):
        log(f"Removing existing extraction folder: '{base_extract_folder}'", level="info")
        try:
            shutil.rmtree(base_extract_folder)
        except Exception as e:
            log(f"Error removing existing folder '{base_extract_folder}': {e}", level="error")
            return # Stop if cleanup fails

    try:
        os.makedirs(base_extract_folder, exist_ok=True)
    except Exception as e:
        log(f"Error creating base extraction folder '{base_extract_folder}': {e}", level="error")
        return

    # --- Cancellation Point 1 (Before Extraction) --- 
    if cancel_event and cancel_event.is_set(): log("Preprocessing cancelled before start.", "warning"); return

    # 1. Extract the main zip file
    if not extract_zip(zip_path, base_extract_folder):
        log("Aborting preprocessing due to error extracting main zip.", level="error")
        # Attempt cleanup even if main extraction fails
        try:
            shutil.rmtree(base_extract_folder)
        except Exception as e:
            log(f"Error during cleanup after failed main extraction of '{base_extract_folder}': {e}", level="error")
        return

    # --- Cancellation Point 2 (After Main Extract, Before Inner) --- 
    if cancel_event and cancel_event.is_set(): log("Preprocessing cancelled after main extract.", "warning"); shutil.rmtree(base_extract_folder); return

    # 2. Find and extract inner zip files
    inner_zip_pattern = os.path.join(base_extract_folder, '*.zip')
    inner_zips = glob.glob(inner_zip_pattern)

    if not inner_zips:
        log(f"No inner zip files (*.zip) found directly in '{base_extract_folder}'. Make sure the main zip contains individual student submission zips.", level="warning")
        # No inner zips found, maybe the structure is different? We'll proceed to cleanup.
    else:
         log(f"Found {len(inner_zips)} inner zip files. Extracting...", level="info")

    # List to store tuples: (priority, submission_name, message)
    submissions_issues = []

    # Define priorities (lower number = higher priority)
    PRIORITY = {
        "EXTRACT_FAIL": 0,
        "ID_FAIL": 1,
        "UNKNOWN_STATUS": 2,
        "NO_C_FILES": 3,
        "MISSING_QS_ROOT": 4,
        "MISSING_QS_SUB": 5,
        "OK_SUBFOLDER_WARN": 6
    }

    total_zips = len(inner_zips)
    processed_zip_count = 0
    description = "Processing student zips"

    # Determine iterator
    use_tqdm = TQDM_AVAILABLE and progress_callback is None
    iterator_factory = tqdm if use_tqdm else lambda iterable, **kwargs: iterable

    progress_iterator = iterator_factory(
        inner_zips,
        total=total_zips,
        desc=description if use_tqdm else None,
        unit="zip"
        # No color codes needed here for tqdm format
    )

    for inner_zip in progress_iterator:
        if cancel_event and cancel_event.is_set(): break
        zip_filename = os.path.basename(inner_zip)
        submission_name = os.path.splitext(zip_filename)[0]
        submission_folder_path = os.path.join(base_extract_folder, submission_name)
        issue_priority = None
        issue_message = None

        # Extract inner zip
        if extract_zip(inner_zip, submission_folder_path):
            # 4. Delete the inner zip file after successful extraction
            try:
                os.remove(inner_zip)
                log(f"Deleted inner zip file: '{inner_zip}'", level="info")
            except Exception as e:
                log(f"Could not delete inner zip '{inner_zip}': {e}", level="warning") # Non-fatal

            # 5, 6, 7. Process the extracted submission folder
            # Extract student ID - assuming format "..._ID" where ID is numeric at the end
            # First try the normal pattern without .zip
            id_match = re.search(r'_(\d+)$', submission_name)
            if not id_match:
                # If not found, try pattern with .zip at the end
                id_match = re.search(r'_(\d+)\.zip$', submission_name)
                if id_match:
                    # Add to issues list that the file had incorrect naming
                    issue_priority = PRIORITY["ID_FAIL"]
                    issue_message = f"{submission_name} (ID found but has .zip suffix)"

            if id_match:
                student_id = id_match.group(1)
                log(f"Processing submission folder: '{submission_folder_path}' for student ID: {student_id}", level="info")

                status, processed_qs = find_and_process_c_files(submission_folder_path, student_id, ".", cancel_event)

                missing_qs = expected_qs_set - processed_qs
                missing_qs_str = ""
                if missing_qs:
                    missing_qs_str = f"Missing Qs: {', '.join(f'Q{q}' for q in sorted(list(missing_qs)))}"

                # Determine issue message and priority based on status and missing questions
                if status == 'ok_root':
                    if missing_qs:
                        issue_priority = PRIORITY["MISSING_QS_ROOT"]
                        issue_message = f"{submission_name} ({missing_qs_str})"
                    else:
                        # Success from root, no issue to report
                        log(f"Submission {submission_name} (ID: {student_id}) processed successfully from root.", level="success")
                elif status == 'ok_subfolder':
                    base_msg = "Files found in subfolder(s)"
                    if missing_qs:
                        issue_priority = PRIORITY["MISSING_QS_SUB"]
                        issue_message = f"{submission_name} ({base_msg}, {missing_qs_str})"
                    else:
                        # Files found in subfolder is a warning, not an error
                        issue_priority = PRIORITY["OK_SUBFOLDER_WARN"]
                        issue_message = f"{submission_name} ({base_msg})"
                        log(f"Submission {submission_name} (ID: {student_id}) processed successfully from subfolder(s).", level="info")
                elif status == 'found_wrong_name':
                    issue_priority = PRIORITY["NO_C_FILES"]  # Using same priority as no files
                    issue_message = f"{submission_name} (C files found with incorrect naming pattern)"
                elif status == 'not_found':
                    issue_priority = PRIORITY["NO_C_FILES"]
                    issue_message = f"{submission_name} (No C files found at all)"
                else:
                    issue_priority = PRIORITY["UNKNOWN_STATUS"]
                    issue_message = f"{submission_name} (Unknown processing status: {status})"
                    log(f"Unknown status '{status}' returned for {submission_name}", level="error")

            else:
                issue_priority = PRIORITY["ID_FAIL"]
                issue_message = f"{submission_name} (ID extraction failed)"
                log(f"Could not extract numeric student ID from folder name '{submission_name}'. Skipping processing.", level="warning")
        else:
             issue_priority = PRIORITY["EXTRACT_FAIL"]
             issue_message = f"{submission_name} (Extraction failed)"
             log(f"Failed to extract inner zip '{inner_zip}'. Skipping processing for this submission.", level="error")

        # Add issue to the list if one was generated
        if issue_priority is not None and issue_message is not None:
            submissions_issues.append((issue_priority, submission_name, issue_message))
        
        processed_zip_count += 1
        if progress_callback:
            progress_callback(processed_zip_count, total_zips, description)

    # --- Cancellation Point 4 (Before Reporting/Cleanup) --- 
    # Report only if not cancelled? Or report partial results?
    if cancel_event and cancel_event.is_set():
         log("Preprocessing was cancelled. Error report might be incomplete.", "warning")
         # Optionally write partial report
    
    if submissions_issues:
        error_file = "submit_error.txt"
        log(f"Found issues/warnings for {len(submissions_issues)} submissions. Writing details to '{error_file}'", level="warning")
        try:
            # Sort by priority (primary) and submission_name (secondary)
            submissions_issues.sort()
            with open(error_file, 'w') as f:
                f.write("Submissions with processing errors/warnings (sorted by issue type):\n")
                # Optional: Add headers for categories if desired
                # current_priority = -1
                for priority, sub_name, message in submissions_issues:
                    # Example category header logic:
                    # if priority != current_priority:
                    #     f.write(f"\n--- Category {priority} ---\n")
                    #     current_priority = priority
                    f.write(f"- {message}\n")
            log(f"Successfully wrote error report to '{error_file}'", level="success")
        except Exception as e:
             log(f"Could not write to error file '{error_file}': {e}", level="error")
    else:
        if not (cancel_event and cancel_event.is_set()): # Only log full success if not cancelled
             log("All submissions processed without errors or warnings requiring reporting.", level="success")

    # Cleanup only if not cancelled?
    if not (cancel_event and cancel_event.is_set()):
        # 8. Delete the base extraction folder
        log(f"Cleaning up temporary folder: '{base_extract_folder}'", level="info")
        try:
            shutil.rmtree(base_extract_folder)
            log("Cleanup successful.", level="success")
        except Exception as e:
            log(f"Error during final cleanup of '{base_extract_folder}': {e}", level="error")

    log("Preprocessing finished.", level="success")

# End of file, ensure no __main__ block remains
