import os
import zipfile
import shutil
import re
import glob
import threading
from typing import Callable, Optional
import json  # Add missing import for json

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
    cancel_event: Optional[threading.Event] = None,
    expected_question_count: int = 0  # New parameter to know how many questions to expect
) -> tuple[list, set]:
    """Finds C files (*_qN.c), renames, moves them, and reports status.

    Searches the submission_folder first. If no files found, searches all
    immediate subdirectories.

    Args:
        submission_folder: Path to the submission folder to search.
        student_id: Student ID to use for renamed files.
        questions_base_path: Base path where question folders are located.
        cancel_event: Optional event to signal cancellation.
        expected_question_count: Number of expected question files (default: 0).

    Returns:
        tuple: (statuses, processed_q_numbers)
          statuses (list): List of status strings like 'ok_root', 'ok_subfolder', 'found_wrong_name', etc.
          processed_q_numbers (set): Set of integers for successfully processed Q numbers.
    """
    processed_q_numbers = set()
    statuses = []
    c_files_found_paths = []
    found_in_subfolder = False
    found_wrong_names = False
    subdirs = []

    # 1. Search in the root submission folder
    log(f"Searching for C files in root: {submission_folder}", level="info")
    root_c_file_pattern = os.path.join(submission_folder, 'hw[0-9]_q[0-9].c')
    c_files_found_paths = glob.glob(root_c_file_pattern)

    if c_files_found_paths:
        log(f"Found {len(c_files_found_paths)} C file(s) directly in {submission_folder}", level="info")
        statuses.append('ok_root')
    else:
        log(f"No C files found directly in {submission_folder}. Checking immediate subfolders...", level="info")
        # 2. If no files in root, search immediate subdirectories
        try:
            items = os.listdir(submission_folder)
            subdirs = [os.path.join(submission_folder, item) for item in items if os.path.isdir(os.path.join(submission_folder, item))]
        except OSError as e:
            log(f"Error listing directory {submission_folder}: {e}", level="error")
            statuses.append('error_listing_dir')

        if subdirs:
            log(f"Found {len(subdirs)} subfolder(s) to check.", level="info")
            for subdir in subdirs:
                log(f"Searching for C files in subfolder: {subdir}", level="info")
                subdir_c_file_pattern = os.path.join(subdir, 'hw[0-9]_q[0-9].c')
                files_in_subdir = glob.glob(subdir_c_file_pattern)
                if files_in_subdir:
                    log(f"Found {len(files_in_subdir)} C file(s) in {subdir}", level="info")
                    c_files_found_paths.extend(files_in_subdir)
                    found_in_subfolder = True
            
            if found_in_subfolder:
                statuses.append('ok_subfolder')
        else:
             log(f"No subfolders found in {submission_folder}", level="info")

    # Check if we should look for incorrectly named files:
    # 1. If we have no files at all, or
    # 2. If we have some files but fewer than expected (mixed case)
    found_file_count = len(c_files_found_paths)
    should_find_wrong_names = (found_file_count == 0) or (expected_question_count > 0 and found_file_count < expected_question_count)
    
    if should_find_wrong_names:
        log(f"Found {found_file_count} correctly named files but expected {expected_question_count}. Searching for incorrectly named files...", level="info")
        
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
        
        # Filter out already found files to avoid duplicates
        already_found_paths = set(c_files_found_paths)
        new_c_files = [f for f in all_c_files if f not in already_found_paths]
        
        if new_c_files:
            log(f"Found {len(new_c_files)} additional C files that might be incorrectly named", level="info")
            
            # Filter for files containing 'q' followed by a number
            wrong_named_files = []
            for c_file in new_c_files:
                filename = os.path.basename(c_file)
                # Check both patterns: 'q' followed by number anywhere, or exact 'q<number>.c'
                if re.search(r'^q\d+\.c$|_q\d+(?:_.*)?\.c$|hw\d+.*\.c$', filename, re.IGNORECASE):
                    wrong_named_files.append(c_file)
                    log(f"Found incorrectly named file: {filename}", level="info")
                else:
                    log(f"File did not match pattern: {filename}", level="info")
            
            if wrong_named_files:
                statuses.append('found_wrong_name')
                found_wrong_names = True
                c_files_found_paths.extend(wrong_named_files)
                log(f"Found {len(wrong_named_files)} C file(s) with incorrect naming pattern: {[os.path.basename(f) for f in wrong_named_files]}", level="info")
            elif not c_files_found_paths:
                # Only report "no files found" if we have no files at all
                log(f"No matching files found. All C files found were: {[os.path.basename(f) for f in all_c_files]}", level="warning")
                if not statuses:  # Only add not_found if we haven't found anything else
                    statuses.append('not_found')
                log(f"No C files with question numbers found in any format", level="warning")

    # --- Filter out example file BEFORE processing --- 
    original_count = len(c_files_found_paths)
    c_files_found_paths = [p for p in c_files_found_paths if os.path.basename(p) != "example_student.c"]
    if len(c_files_found_paths) < original_count:
        log("Ignoring 'example_student.c' found during preprocessing search.", "info")

    # Check for cancellation before processing found files
    if cancel_event and cancel_event.is_set():
        log("File processing cancelled before starting.", "warning")
        return ["cancelled"], processed_q_numbers

    # 3. Process all found C files (from root or subfolders)
    if not c_files_found_paths:
        log(f"No C files matching pattern '*_qN*.c' found for submission ID {student_id} in {submission_folder} or its subfolders.", level="warning")
        if not statuses:  # Only add not_found if we haven't found anything else
            statuses.append('not_found')
        return statuses, processed_q_numbers

    log(f"Processing {len(c_files_found_paths)} found C file(s) for ID {student_id}", level="info")
    for c_file_path in c_files_found_paths:
        # --- Cancellation Check within loop --- 
        if cancel_event and cancel_event.is_set():
            log(f"File processing cancelled mid-way for ID {student_id}.", "warning")
            statuses = ["cancelled"]  # Override with cancelled status
            break # Exit loop

        filename = os.path.basename(c_file_path)
        # Extract question number: matches any filename containing q<digits> and ending with .c
        match = re.search(r'q(\d+).*\.c$', filename, re.IGNORECASE)
        if match:
            # Use the first matching group that isn't None
            q_number_str = next((g for g in match.groups() if g is not None), None)
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
                    if 'error_copying' not in statuses:
                        statuses.append('error_copying')
            except ValueError:
                 log(f"Could not convert question number '{q_number_str}' to integer in '{filename}'. Skipping.", level="warning")
                 if 'invalid_q_number' not in statuses:
                     statuses.append('invalid_q_number')
        else:
            log(f"Could not extract question number from filename '{filename}' (path: {c_file_path}). Skipping.", level="warning")
            if 'cant_extract_q_number' not in statuses:
                statuses.append('cant_extract_q_number')

    # Final status checks
    if "cancelled" in statuses:
        # Keep only cancelled if present
        return ["cancelled"], processed_q_numbers
    
    # Check if we found files but couldn't process any
    if not processed_q_numbers and c_files_found_paths:
        if 'processing_failed' not in statuses:
            statuses.append('processing_failed')
    
    # If we found fewer questions than expected, add a status for it
    if expected_question_count > 0 and len(processed_q_numbers) < expected_question_count:
        if 'missing_expected_questions' not in statuses:
            statuses.append('missing_expected_questions')
            log(f"Processed {len(processed_q_numbers)} questions but expected {expected_question_count}", level="warning")
    
    # If we have no status at all, mark as not_found
    if not statuses:
        statuses.append('not_found')
        
    return statuses, processed_q_numbers

def preprocess_submissions(
    zip_path: str,
    questions_list: list,
    rar_support: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    winrar_path: str = None  # New parameter to override the default winrar_path from configuration
):
    """
    Main function to preprocess submissions:
    1. Extracts the main zip.
    2. Extracts inner student zips.
    3. Finds, renames, and moves C files.
    4. Cleans up intermediate files/folders.
    5. Reports submissions with issues.
    
    Args:
        zip_path: Path to the main submissions zip file
        questions_list: List of question folder names
        rar_support: Whether to enable RAR extraction support
        progress_callback: Optional callback for progress reporting
        cancel_event: Optional event to signal cancellation
        winrar_path: Optional path to WinRAR/UnRAR executable, overrides the configuration default
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
    
    # Number of expected questions
    expected_question_count = len(expected_qs_set)

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

    # Find and add RAR files
    inner_rar_pattern = os.path.join(base_extract_folder, '*.rar')
    inner_rars = glob.glob(inner_rar_pattern)


    if not inner_zips and not inner_rars:
        log(f"No inner archive files (*.zip, *.rar) found directly in '{base_extract_folder}'. Make sure the main zip contains individual student submission archives (ZIP or RAR).", level="warning")
        # No inner archives found, maybe the structure is different? We'll proceed to cleanup.
    else:
         log(f"Found {len(inner_zips) + len(inner_rars)} inner archive files. Extracting...", level="info")

    # Dictionary to store issues per submission: submission_name -> list of (priority, message)
    # This change allows tracking multiple issues per submission
    submissions_issues = {}

    # Define priorities (lower number = higher priority)
    PRIORITY = {
        "EXTRACT_FAIL": 0,
        "ID_FAIL": 1,
        "UNKNOWN_STATUS": 2,
        "NO_C_FILES": 3,
        "MISSING_QS_ROOT": 4,
        "MISSING_QS_SUB": 5,
        "OK_SUBFOLDER_WARN": 6,
        "RAR_FILE": 7  # New priority for RAR files
    }

    total_archives = len(inner_zips) + len(inner_rars)
    processed_zip_count = 0
    description = "Processing student archives"

    # Determine iterator
    use_tqdm = TQDM_AVAILABLE and progress_callback is None
    iterator_factory = tqdm if use_tqdm else lambda iterable, **kwargs: iterable

    inner_archives = inner_zips + inner_rars

    progress_iterator = iterator_factory(
        inner_archives,
        total=total_archives,
        desc=description if use_tqdm else None,
        unit="archive"
        # No color codes needed here for tqdm format
    )

    for inner_archive in progress_iterator:
        if cancel_event and cancel_event.is_set(): break
        archive_filename = os.path.basename(inner_archive)
        submission_name = os.path.splitext(archive_filename)[0]
        submission_folder_path = os.path.join(base_extract_folder, submission_name)
        
        # Initialize list to collect issues for this submission
        current_issues = []
        if inner_archive.endswith('.zip'):
            zip_extract_success = extract_zip(inner_archive, submission_folder_path)
            extract_success = zip_extract_success
        elif inner_archive.endswith('.rar') and rar_support:
            rar_extract_success = extract_rar(inner_archive, submission_folder_path, winrar_path)
            if rar_extract_success:
                current_issues.append((PRIORITY["RAR_FILE"], "Archive of type RAR, not zip"))
            extract_success = rar_extract_success
        else:
            # Unsupported archive type
            log(f"Unsupported archive type for file: {inner_archive}", level="warning")
            current_issues.append((PRIORITY["EXTRACT_FAIL"], "Unsupported archive type"))
            extract_success = False
            
        # Process the extracted archive if successful
        if extract_success:
            # 4. Delete the inner zip file after successful extraction
            try:
                os.remove(inner_archive)
                log(f"Deleted inner archive file: '{inner_archive}'", level="info")
            except Exception as e:
                log(f"Could not delete inner archive '{inner_archive}': {e}", level="warning") # Non-fatal
                current_issues.append((PRIORITY["EXTRACT_FAIL"], f"Could not delete inner archive: {e}"))

            # 5, 6, 7. Process the extracted submission folder
            # Extract student ID - assuming format "..._ID" where ID is numeric at the end
            # First try the normal pattern without .zip
            id_match = re.search(r'_(\d+)$', submission_name)
            id_found = True
            
            if not id_match:
                # If not found, try pattern with .zip at the end
                id_match = re.search(r'_(\d+)\.zip$', submission_name)
                if id_match:
                    # Add to issues list that the file had incorrect naming
                    current_issues.append((PRIORITY["ID_FAIL"], f"ID found but has .zip suffix"))
                else:
                    id_match = re.search(r'_(\d+)\.$', submission_name)
                    if id_match:
                        # Add to issues list that the file had incorrect naming
                        current_issues.append((PRIORITY["ID_FAIL"], f"ID found but has . suffix"))
                    else:
                        id_found = False
                        current_issues.append((PRIORITY["ID_FAIL"], f"ID extraction failed"))
                        log(f"Could not extract numeric student ID from folder name '{submission_name}'. Skipping processing.", level="warning")

            if id_found:
                student_id = id_match.group(1)
                log(f"Processing submission folder: '{submission_folder_path}' for student ID: {student_id}", level="info")

                status, processed_qs = find_and_process_c_files(
                    submission_folder_path, 
                    student_id, 
                    ".", 
                    cancel_event,
                    expected_question_count
                )

                missing_qs = expected_qs_set - processed_qs
                missing_qs_str = ""
                if missing_qs:
                    missing_qs_str = f"Missing Qs: {', '.join(f'Q{q}' for q in sorted(list(missing_qs)))}"

                # Process multiple status codes returned from find_and_process_c_files
                # The status is now a list of strings instead of a single string
                if 'cancelled' in status:
                    # Don't add an issue for cancellations
                    log(f"Processing for {submission_name} was cancelled", level="warning")
                else:
                    # Check for specific statuses and add issues accordingly
                    for status_code in status:
                        if status_code == 'ok_root':
                            if missing_qs:
                                current_issues.append((PRIORITY["MISSING_QS_ROOT"], missing_qs_str))
                            else:
                                # Success from root, no issue to report
                                log(f"Submission {submission_name} (ID: {student_id}) processed successfully from root.", level="success")
                        elif status_code == 'ok_subfolder':
                            base_msg = "Files found in subfolder(s)"
                            if missing_qs:
                                current_issues.append((PRIORITY["MISSING_QS_SUB"], f"{base_msg}, {missing_qs_str}"))
                            else:
                                # Files found in subfolder is a warning, not an error
                                current_issues.append((PRIORITY["OK_SUBFOLDER_WARN"], base_msg))
                                log(f"Submission {submission_name} (ID: {student_id}) processed successfully from subfolder(s).", level="info")
                        elif status_code == 'found_wrong_name':
                            current_issues.append((PRIORITY["NO_C_FILES"], "C files found with incorrect naming pattern"))
                        elif status_code == 'not_found':
                            current_issues.append((PRIORITY["NO_C_FILES"], "No C files found at all"))
                        elif status_code == 'error_listing_dir':
                            current_issues.append((PRIORITY["EXTRACT_FAIL"], "Error listing directory contents"))
                        elif status_code == 'error_copying':
                            current_issues.append((PRIORITY["EXTRACT_FAIL"], "Error copying C files to destination"))
                        elif status_code == 'invalid_q_number':
                            current_issues.append((PRIORITY["NO_C_FILES"], "Invalid question number found in filename"))
                        elif status_code == 'cant_extract_q_number':
                            current_issues.append((PRIORITY["NO_C_FILES"], "Could not extract question number from filename"))
                        elif status_code == 'processing_failed':
                            current_issues.append((PRIORITY["NO_C_FILES"], "Files found but processing failed"))
                        elif status_code == 'missing_expected_questions':
                            current_issues.append((PRIORITY["NO_C_FILES"], "Missing expected questions"))
                        else:
                            current_issues.append((PRIORITY["UNKNOWN_STATUS"], f"Unknown processing status: {status_code}"))
                            log(f"Unknown status '{status_code}' returned for {submission_name}", level="error")
        else:
             current_issues.append((PRIORITY["EXTRACT_FAIL"], "Extraction failed"))
             log(f"Failed to extract archive '{inner_archive}'. Skipping processing for this submission.", level="error")

        # Add all issues to the submission's issue list
        if current_issues:
            submissions_issues[submission_name] = current_issues
        
        processed_zip_count += 1
        if progress_callback:
            progress_callback(processed_zip_count, total_archives, description)

    # --- Cancellation Point 4 (Before Reporting/Cleanup) --- 
    # Report only if not cancelled? Or report partial results?
    if cancel_event and cancel_event.is_set():
         log("Preprocessing was cancelled. Error report might be incomplete.", "warning")
         # Optionally write partial report
    
    if submissions_issues:
        error_file = "submit_error.txt"
        log(f"Found issues/warnings for {len(submissions_issues)} submissions. Writing details to '{error_file}'", level="warning")
        try:
            # Create a list of entries to sort
            sorted_entries = []
            total_issues_count = 0
            for submission_name, issues in submissions_issues.items():
                # Sort issues by priority
                issues.sort(key=lambda x: x[0])
                # Find the highest priority (lowest number) for sorting submissions
                highest_priority = issues[0][0] if issues else 999
                sorted_entries.append((highest_priority, submission_name, issues))
                total_issues_count += len(issues)
            
            # Sort by highest priority (primary) and submission_name (secondary)
            sorted_entries.sort()
            
            with open(error_file, 'w') as f:
                f.write(f"Submissions with processing errors/warnings: {len(submissions_issues)} submissions with a total of {total_issues_count} issues (sorted by issue type):\n")
                for _, submission_name, issues in sorted_entries:
                    f.write(f"- {submission_name}: ")
                    for _, message in issues:
                        f.write(f" * {message}")
                    f.write("\n")
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

def extract_rar(rar_path, dest_path, winrar_path=None):
    """
    Extracts a RAR file to the specified destination.
    
    Args:
        rar_path (str): Path to the RAR file
        dest_path (str): Destination folder to extract to
        custom_winrar_path (str): Optional custom path to WinRAR/UnRAR executable
    
    Returns:
        bool: True if extraction was successful, False otherwise
    """
    try:
        import rarfile
        # Set the path to the WinRAR executable - use custom path if provided
        rarfile.UNRAR_TOOL = winrar_path
        
        # Check if the tool exists
        if not os.path.exists(rarfile.UNRAR_TOOL):
            log(f"WinRAR executable not found at: {rarfile.UNRAR_TOOL}", level="error")
            # Try to fallback to WinRAR.exe if UnRAR.exe was specified
            if rarfile.UNRAR_TOOL.lower().endswith('unrar.exe'):
                alternative_path = rarfile.UNRAR_TOOL.replace('UnRAR.exe', 'WinRAR.exe')
                if os.path.exists(alternative_path):
                    rarfile.UNRAR_TOOL = alternative_path
                    log(f"Using alternative WinRAR path: {rarfile.UNRAR_TOOL}", level="info")
                else:
                    log(f"Alternative WinRAR path also not found: {alternative_path}", level="error")
                    return False
            else:
                return False
                
        log(f"Extracting RAR archive: {rar_path} to {dest_path}", level="info", verbosity=2)
        
        # Create destination directory if it doesn't exist
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)
            
        with rarfile.RarFile(rar_path) as rf:
            rf.extractall(path=dest_path)
            
        log(f"Successfully extracted RAR: {rar_path}", level="success", verbosity=2)
        return True
        
    except ImportError:
        log("RAR extraction failed: rarfile module not installed. Install with 'pip install rarfile'", level="error")
        return False
    except rarfile.RarCannotExec:
        log("RAR extraction failed: UnRAR executable not found. Install UnRAR or WinRAR and ensure it's in your PATH.", level="error")
        return False
    except rarfile.BadRarFile:
        log(f"RAR extraction failed: {rar_path} is not a valid RAR file", level="error")
        return False
    except Exception as e:
        log(f"RAR extraction failed for {rar_path}: {str(e)}", level="error")
        return False

# End of file, ensure no __main__ block remains
