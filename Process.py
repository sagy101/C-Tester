import os
import math
import shutil
import subprocess
import time
import threading # Needed for Event type hint if using Python < 3.9
from typing import Callable, Optional # For type hinting callbacks/events
import signal

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    # Define a dummy tqdm class if tqdm is not installed
    # or if we choose not to use it (e.g., in GUI)
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

from concurrent.futures import ThreadPoolExecutor, as_completed
from Utils import log
from Utils import VERBOSITY_LEVEL
from configuration import vs_path  # Import vs_path from configuration


def setup_visual_studio_environment():
    log("Setting up Visual Studio environment...", "info", verbosity=1)
    command = f'cmd /c ""{vs_path}" && set"'
    try:
        result = subprocess.run(command, capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            raise Exception(result.stderr)
        for line in result.stdout.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value
        log("Visual Studio environment setup complete.", "success", verbosity=1)
    except Exception as e:
        log(f"Error setting up Visual Studio environment: {str(e)}", "error", verbosity=1)


def sanitize_input(input_value):
    return input_value.replace('"', '').replace("'", '').replace(";", '')


def read_inputs_from_file(folder_name):
    input_file = os.path.join(folder_name, "input.txt")
    try:
        with open(input_file, "r", encoding="utf-8") as file:
            inputs = [sanitize_input(line.strip()) for line in file if line.strip()]
        log(f"Loaded {len(inputs)} sanitized inputs from {input_file}", "success")
        return inputs
    except Exception as e:
        log(f"Failed to read inputs from {input_file}: {str(e)}", "error")
        return []


def ensure_output_folder(folder_name):
    output_folder = os.path.join(folder_name, "output")
    grade_folder = os.path.join(folder_name, "grade")
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(grade_folder, exist_ok=True)
    log(f"Output and grade folders ready in {folder_name}", "success", verbosity=1)
    return output_folder, grade_folder


def compile_file(c_file):
    executable = c_file.replace(".c", ".exe")
    compile_cmd = f'cl /TC /EHsc /MP /O2 /Za /Fe{executable} {c_file}'
    result = subprocess.run(compile_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Compilation failed: {c_file}", "error", verbosity=1)
        return None, result.stderr
    log(f"Compilation successful: {c_file}", "success", verbosity=2)
    return executable, None


def parallel_compile_files(
    c_files_dir: str,
    c_files: list,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> tuple[dict, dict]:
    compiled = {}
    compile_errors = {}
    total_files = len(c_files)
    processed_count = 0
    description = "Compiling files"

    # Determine iterator: tqdm if no callback and available, else direct iteration
    use_tqdm = TQDM_AVAILABLE and progress_callback is None
    iterator_factory = tqdm if use_tqdm else lambda iterable, **kwargs: iterable

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        future_map = { executor.submit(compile_file, os.path.join(c_files_dir, f)): f for f in c_files }

        progress_iterator = iterator_factory(
            as_completed(future_map),
            total=total_files,
            desc=description if use_tqdm else None,
            unit="file",
            bar_format="\033[94m{l_bar}{bar}{r_bar}\033[0m" if use_tqdm else None
        )

        for future in progress_iterator:
            if cancel_event and cancel_event.is_set(): break
            file = future_map[future]
            try:
                exe, error = future.result()
                if exe:
                    compiled[file] = exe
                else:
                    compile_errors[file] = error
            except Exception as e:
                log(f"Error getting compilation result for {file}: {e}", "error")
                compile_errors[file] = str(e)
            finally:
                processed_count += 1
                if progress_callback:
                    progress_callback(processed_count, total_files, description)

    # Log summary only if not cancelled
    if not (cancel_event and cancel_event.is_set()):
        success_count = len(compiled)
        if success_count == 0 and total_files > 0:
            log(f"No files Compiled successfully!", "error")
        elif success_count != total_files:
            log(f"Compiled {success_count}/{total_files} files successfully.", "warning")
        else:
            log(f"All {total_files} files compiled successfully.", "success")

    return compiled, compile_errors


def run_executable(executable, input_value, timeout=5):
    """Run an executable with the given input and timeout (in seconds)."""
    try:
        # Start the process without shell=True to avoid cmd.exe wrapper
        process = subprocess.Popen(
            executable,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP  # Windows-specific: create new process group
        )
        
        # Send input and get output with timeout
        try:
            stdout, stderr = process.communicate(input=str(input_value), timeout=timeout)
            if process.returncode != 0:
                return f"Runtime Error: {stderr.strip()}"
            return stdout.strip()
        except subprocess.TimeoutExpired:
            # On Windows, we need to be more aggressive with process termination
            try:
                # First try CTRL+BREAK to the process group
                process.send_signal(signal.CTRL_BREAK_EVENT)
                time.sleep(0.1)  # Give it a moment to handle the signal
                
                # If still running, terminate
                if process.poll() is None:
                    process.terminate()
                    time.sleep(0.1)  # Give it a moment to terminate
                
                # If STILL running, kill it forcefully
                if process.poll() is None:
                    process.kill()
                
                # Clean up any remaining pipes
                try:
                    process.communicate(timeout=0.1)
                except:
                    pass
            except:
                # If any of the termination attempts fail, ensure the process is killed
                try:
                    process.kill()
                except:
                    pass
            
            timeout_msg = f"Timeout after {timeout}s"
        log(timeout_msg, "warning")
        return "Timeout"
    except Exception as e:
        log(f"Error running {executable}: {str(e)}", "error")
        return f"Error: {str(e)}"


def get_ground_truth(
    folder_name: str,
    inputs: list,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> list:
    original_sol = os.path.join(folder_name, "original_sol.c")
    executable, compile_error = compile_file(original_sol)
    if compile_error:
        log(f"Ground truth compilation failed: {compile_error}", "error")
        return []

    ground_truth = []
    total_inputs = len(inputs)
    processed_count = 0
    description = f"Processing original_sol in {folder_name}"

    use_tqdm = TQDM_AVAILABLE and progress_callback is None
    iterator_factory = tqdm if use_tqdm else lambda iterable, **kwargs: iterable

    progress_iterator = iterator_factory(
        inputs,
        total=total_inputs,
        desc=description if use_tqdm else None,
        unit="input",
        bar_format="\033[94m{l_bar}{bar}{r_bar}\033[0m" if use_tqdm else None
    )

    for input_value in progress_iterator:
        if cancel_event and cancel_event.is_set(): break
        output = run_executable(executable, input_value, timeout=5)  # Use same timeout as student solutions
        ground_truth.append((input_value, output))
        processed_count += 1
        if progress_callback:
            progress_callback(processed_count, total_inputs, description)

    if executable and os.path.exists(executable):
        try:
            os.remove(executable)
        except Exception as e:
            log(f"Error removing ground truth executable {executable}: {e}", "warning")

    return ground_truth


def write_grade(grade_path, correct_count, total, discrepancies, compile_error, timeout_count=0):
    try:
        with open(grade_path, "w", encoding="utf-8") as grade_file:
            if compile_error:
                grade_file.write(f"Grade: 0%\nCompilation error: {compile_error}\n")
            else:
                if total == 0:
                    grade_file.write("Grade: 0%\nNo inputs provided.\n")
                else:
                    percentage = (correct_count / total) * 100
                    rounded_percentage = math.ceil(percentage)
                    grade_file.write(f"Grade: {rounded_percentage}%\n")
                    grade_file.write(f"(Calculated grade is: {percentage:.2f}%)\n")
                    
                    # Add Wrong Inputs line if there were discrepancies
                    if discrepancies:
                        wrong_inputs = [str(d[0]) for d in discrepancies]
                        grade_file.write(f"Wrong Inputs: {', '.join(wrong_inputs)}\n")
                    else:
                         # Add line even if no wrong inputs, for consistency?
                         # grade_file.write("Wrong Inputs: None\n") 
                         pass # Or just omit the line

                if timeout_count != 0:
                    grade_file.write(f"\nTimeouts: {timeout_count}/{total}\n")
                    # Add list of inputs that caused timeouts
                    timeout_inputs = [str(d[0]) for d in discrepancies if d[2] == "Timeout"]
                    if timeout_inputs:
                        grade_file.write(f"Timeout Inputs: {', '.join(timeout_inputs)}\n")

                # Write discrepancies AFTER the summary lines
                if discrepancies:
                    grade_file.write("\nDiscrepancies:\n")
                    for input_value, expected, actual in discrepancies:
                        grade_file.write(f"Input: {input_value}\nExpected: {expected}\nActual: {actual}\n\n")
        log(f"Grade file created: {grade_path}", "success", verbosity=2)
    except Exception as e:
        log(f"Error writing grade file {grade_path}: {str(e)}", "error")


def compare_outputs(ground_truth, actual_outputs):
    total = len(ground_truth)
    correct_count = sum(
        1 for i in range(total) if ground_truth[i][1] == actual_outputs[i][1]
    )
    discrepancies = [
        (ground_truth[i][0], ground_truth[i][1], actual_outputs[i][1])
        for i in range(total)
        if ground_truth[i][1] != actual_outputs[i][1]
    ]
    return correct_count, discrepancies, total


def execute_and_grade(file, executable, inputs, ground_truth, output_folder, grade_folder):
    grade_path = os.path.join(grade_folder, file.replace(".c", ".txt"))
    output_path = os.path.join(output_folder, file.replace(".c", ".txt"))

    actual_outputs, lines_to_write = [], []

    timeout_count = 0

    for input_value in inputs:
        output = run_executable(executable, input_value)
        if output == "Timeout":
            timeout_count += 1
        actual_outputs.append((input_value, output))
        lines_to_write.append(f"Input: {input_value}\nOutput: {output}\n\n")

    with open(output_path, "w", encoding="utf-8") as sol_file:
        sol_file.writelines(lines_to_write)

    correct_count, discrepancies, total = compare_outputs(ground_truth, actual_outputs)
    write_grade(grade_path, correct_count, total, discrepancies, None, timeout_count)

    return executable


def log_compilation_summary(compile_errors):
    """
    By default, print a one-line list of files with compile errors.
    If VERBOSITY_LEVEL > 2, also list the detailed errors.
    """
    if compile_errors:
        files_str = ", ".join(compile_errors.keys())
        log(f"Compilation failed for: {files_str}", "warning", verbosity=1)

        if VERBOSITY_LEVEL > 2:
            for file, error in compile_errors.items():
                log(f"  {file} error:\n    {error}", "warning", verbosity=3)


def cleanup_folders(base_folder):
    log(f"Cleaning folders in: {base_folder}", "info", verbosity=1)
    # Iterate through potential folders to clean (output, grade)
    for folder_to_clean_name in ["output", "grade"]:
        folder_path = os.path.join(base_folder, folder_to_clean_name)
        if os.path.isdir(folder_path):
            log(f"Cleaning contents of: {folder_path}", "info", verbosity=2)
            for item_name in os.listdir(folder_path):
                # Skip the specific example file
                if item_name == "example_student.txt":
                    log(f"Skipping cleanup of example file: {os.path.join(folder_path, item_name)}", "info", verbosity=2)
                    continue
                
                item_path = os.path.join(folder_path, item_name)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                        log(f"Cleaned file: {item_path}", "success", verbosity=3)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path) # Remove subdirectories if any
                        log(f"Cleaned subdirectory: {item_path}", "success", verbosity=3)
                except Exception as e:
                    log(f"Error cleaning item {item_path}: {e}", "error")
        # else: Folder didn't exist, nothing to clean


def cleanup_executables(executables):
    for exe in executables:
        try:
            if os.path.exists(exe):
                os.remove(exe)
                log(f"Deleted: {exe}", "success", verbosity=2)
        except Exception as e:
            log(f"Error deleting {exe}: {str(e)}", "error")


def cleanup_obj_files():
    log("Cleaning up all *.obj files...", "info")
    deleted_count = 0
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".obj"):
                # Skip example object file
                if file == "example_student.obj":
                    log(f"Skipping cleanup of example object file: {os.path.join(root, file)}", "info", verbosity=2)
                    continue
                try:
                    file_path = os.path.join(root, file)
                    os.remove(file_path)
                    deleted_count += 1
                    log(f"Deleted obj file: {file_path}", "success", verbosity=3)
                except Exception as e:
                    log(f"Error deleting obj file {os.path.join(root, file)}: {str(e)}", "error")
    if deleted_count > 0:
        log(f"Deleted {deleted_count} .obj file(s).", "info")
    else:
        log("No .obj files found to delete.", "info")


def process_folder(
    folder_name: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> str:
    print("\n\n")
    log(f"Processing folder: {folder_name}...", "info")
    # Define stages and weights for progress reporting
    # Stage 1: Ground Truth (approx 30%?)
    # Stage 2: Compile (approx 30%?)
    # Stage 3: Execute (approx 40%?)
    # This is complex, maybe just report progress within each stage?
    # Let's stick to reporting progress for the 3 main loops.

    # --- Check Cancellation Point 1 --- 
    if cancel_event and cancel_event.is_set(): return "cancelled"
    cleanup_folders(folder_name)
    output_folder, grade_folder = ensure_output_folder(folder_name)

    inputs = read_inputs_from_file(folder_name)
    if not inputs: return "warning"

    # --- Ground Truth --- 
    log(f"Generating ground truth for {folder_name}...", "info")
    ground_truth_desc = f"[{folder_name}] Ground Truth"
    ground_truth = get_ground_truth(folder_name, inputs, progress_callback, cancel_event)
    if cancel_event and cancel_event.is_set(): return "cancelled"
    if not ground_truth: return "error"

    # --- Check Cancellation Point 2 --- 
    if cancel_event and cancel_event.is_set(): return "cancelled"
    c_files_dir = os.path.join(folder_name, "C")
    if not os.path.isdir(c_files_dir): return "error"
    
    # Filter C files to process, EXCLUDING example_student.c
    c_files_to_process = [
        f for f in os.listdir(c_files_dir)
        if f.endswith(".c") and f != "original_sol.c" and f != "example_student.c"
    ]
    if not c_files_to_process:
        log(f"No student .c files (excluding examples/originals) to process in {c_files_dir}.", "warning")
        return "warning" # Or success? If only example/original exist, maybe that's ok.

    # --- Compilation --- 
    log(f"Compiling student files in {folder_name}...", "info")
    compile_desc = f"[{folder_name}] Compiling"
    compiled, compile_errors = parallel_compile_files(c_files_dir, c_files_to_process, progress_callback, cancel_event)
    if cancel_event and cancel_event.is_set(): return "cancelled"

    # Write grade files for compilation errors
    for file, error in compile_errors.items():
        grade_path = os.path.join(grade_folder, file.replace(".c", ".txt"))
        write_grade(grade_path, 0, 0, [], error, 0)

    # ... (handle compile errors and write grades for them) ...
    if len(compiled) == 0 and len(c_files_to_process) > 0: return "error"
    if len(compiled) == 0: return "warning" # No files to even attempt compile?

    time.sleep(0.1)

    # --- Execution --- 
    log(f"Executing student programs in {folder_name}...", "info")
    execute_desc = f"[{folder_name}] Executing"
    executables_to_cleanup = []
    processed_count = 0
    total_to_execute = len(compiled)
    use_tqdm = TQDM_AVAILABLE and progress_callback is None
    iterator_factory = tqdm if use_tqdm else lambda iterable, **kwargs: iterable

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = { executor.submit(execute_and_grade, file, exe, inputs, ground_truth, output_folder, grade_folder): file
                    for file, exe in compiled.items() }

        progress_iterator = iterator_factory(
            as_completed(futures),
            total=total_to_execute,
            desc=execute_desc if use_tqdm else None,
            unit="file",
            bar_format="\033[94m{l_bar}{bar}{r_bar}\033[0m" if use_tqdm else None
        )

        for future in progress_iterator:
            if cancel_event and cancel_event.is_set(): break
            try:
                executable_used = future.result()
                if executable_used: # Should always return the exe path
                    executables_to_cleanup.append(executable_used)
            except Exception as e:
                file = futures[future]
                log(f"Error getting execution result for {file}: {e}", "error")
            finally:
                processed_count += 1
                if progress_callback:
                    progress_callback(processed_count, total_to_execute, execute_desc)

    # --- Cleanup & Summary --- 
    # Cleanup only if not cancelled mid-execution?
    if not (cancel_event and cancel_event.is_set()):
        cleanup_executables(executables_to_cleanup)
        log_compilation_summary(compile_errors)

        total_files = len(c_files_to_process)
        compiled_count = len(compiled)
        if compiled_count == total_files and len(compile_errors) == 0:
            return "success"
        else:
            return "warning"
    else:
        # Need to decide what to do with partially created executables if cancelled
        log("Execution was cancelled, skipping final cleanup of executables for this folder.", "info")
        return "cancelled"


def process_all_questions(
    questions_arr: list,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> list:
    results = []
    total_questions = len(questions_arr)
    description = "Overall Question Progress"
    for i, question in enumerate(questions_arr):
        if cancel_event and cancel_event.is_set():
            log("Processing all questions cancelled.", "warning", verbosity=1)
            break
        # Pass the main callback down to sub-stages
        status = process_folder(question, progress_callback=progress_callback, cancel_event=cancel_event)
        results.append((question, status))
        # Optionally report overall progress here too, though sub-stages are reporting
        # if progress_callback:
        #     progress_callback(i + 1, total_questions, description)

    # ... (summarize results, check for 'cancelled' status) ...
    summary_details = ", ".join(f"{q}({s})" for q, s in results)
    if any(s == "cancelled" for _, s in results):
        log(f"Processing cancelled. Results: {summary_details}", "warning", verbosity=1)
    else:
        # Original summary logic
        all_success = all(status == "success" for _, status in results)
        any_success = any(status == "success" or status == "warning" for _, status in results)
        if all_success:
            final_status = "success"
            msg = "All Questions processed successfully."
        elif any_success:
            final_status = "warning"
            msg = "Some Questions processed successfully, some had issues."
        else:
            final_status = "error"
            msg = "No Questions were processed successfully."
        log(f"Processed Questions: {summary_details}. {msg}", final_status, verbosity=1)

    return results


def run_tests(
    questions: list,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None
):
    try:
        setup_visual_studio_environment()
        # Pass callback and event down
        process_all_questions(questions, progress_callback, cancel_event)
    finally:
        # Cleanup only if not cancelled?
        if not (cancel_event and cancel_event.is_set()):
            time.sleep(0.1)
            print("\n")
            cleanup_obj_files()
            log("All temporary files cleaned.", "success", verbosity=1)
        else:
            log("Task cancelled, skipping final .obj cleanup.", "warning", verbosity=1)

