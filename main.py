import os
import math
import shutil
import subprocess
import time

from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

VERBOSITY_LEVEL = 1  # Adjust verbosity (0=minimal, 1=normal, 2=verbose)


def log(message, level="info", verbosity=1):
    if verbosity <= VERBOSITY_LEVEL:
        colors = {
            "info": "\033[94m",
            "success": "\033[92m",
            "warning": "\033[93m",
            "error": "\033[91m"
        }
        reset_color = "\033[0m"
        print(f"{colors.get(level, colors['info'])}[{level.upper()}] {message}{reset_color}")


def setup_visual_studio_environment():
    log("Setting up Visual Studio environment...", "info")
    vs_path = r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
    command = f'cmd /c ""{vs_path}" && set"'
    try:
        result = subprocess.run(command, capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            raise Exception(result.stderr)
        for line in result.stdout.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value
        log("Visual Studio environment setup complete.", "success")
    except Exception as e:
        log(f"Error setting up Visual Studio environment: {str(e)}", "error")


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
    log(f"Output and grade folders ready in {folder_name}", "success", verbosity=2)
    return output_folder, grade_folder


def compile_file(c_file):
    executable = c_file.replace(".c", ".exe")
    compile_cmd = f'cl /EHsc /MP /O2 /Fe{executable} {c_file}'
    result = subprocess.run(compile_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Compilation failed: {c_file}", "error", verbosity=2)
        return None, result.stderr
    log(f"Compilation successful: {c_file}", "success", verbosity=2)
    return executable, None


def parallel_compile_files(c_files_dir, c_files):
    compiled = {}
    compile_errors = {}
    total_files = len(c_files)

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        future_map = {
            executor.submit(compile_file, os.path.join(c_files_dir, f)): f for f in c_files
        }

        with tqdm(total=total_files, desc="Compiling C files", unit="file",
                  bar_format="\033[94m{l_bar}{bar}{r_bar}\033[0m") as pbar:
            for future in as_completed(future_map):
                file = future_map[future]
                exe, error = future.result()
                if exe:
                    compiled[file] = exe
                else:
                    compile_errors[file] = error
                pbar.update(1)

    success_count = len(compiled)
    if success_count == 0:
        log(f"No files Compiled successfully!", "error")
    elif success_count != total_files:
        log(f"Compiled {success_count}/{total_files} files successfully.", "warning")
    else:
        log(f"All {total_files} files compiled successfully.", "success")

    return compiled, compile_errors


def run_executable(executable, input_value, timeout=30):
    try:
        result = subprocess.run(
            [executable],
            input=str(input_value),
            capture_output=True,
            text=True,
            shell=True,
            timeout=timeout
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        timeout_msg = f"Timeout after {timeout}s for input '{input_value}'"
        log(timeout_msg, "warning")
        return "Timeout"
    except Exception as e:
        log(f"Error running {executable}: {str(e)}", "error")
        return f"Error: {str(e)}"


def get_ground_truth(folder_name, inputs):
    original_sol = os.path.join(folder_name, "original_sol.c")
    executable, compile_error = compile_file(original_sol)
    if compile_error:
        log(f"Ground truth compilation failed: {compile_error}", "error")
        return []

    ground_truth = []
    with tqdm(total=len(inputs), desc=f"Processing original_sol in {folder_name}",
              unit="input", bar_format="\033[94m{l_bar}{bar}{r_bar}\033[0m") as pbar:
        for input_value in inputs:
            output = run_executable(executable, input_value)
            ground_truth.append((input_value, output))
            pbar.update(1)

    if executable and os.path.exists(executable):
        os.remove(executable)

    return ground_truth


def write_grade(grade_path, correct_count, total, discrepancies, compile_error):
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

    for input_value in inputs:
        output = run_executable(executable, input_value)
        actual_outputs.append((input_value, output))
        lines_to_write.append(f"Input: {input_value}\nOutput: {output}\n\n")

    with open(output_path, "w", encoding="utf-8") as sol_file:
        sol_file.writelines(lines_to_write)

    correct_count, discrepancies, total = compare_outputs(ground_truth, actual_outputs)
    write_grade(grade_path, correct_count, total, discrepancies, None)

    return executable


def log_compilation_summary(compile_errors):
    """
    By default, print a one-line list of files with compile errors.
    If VERBOSITY_LEVEL > 2, also list the detailed errors.
    """
    if compile_errors:
        files_str = ", ".join(compile_errors.keys())
        log(f"Compilation failed for: {files_str}", "warning", verbosity=2)

        if VERBOSITY_LEVEL > 2:
            for file, error in compile_errors.items():
                log(f"  {file} error:\n    {error}", "warning", verbosity=3)


def cleanup_folders(base_folder):
    log(f"Cleaning folders in: {base_folder}", "info")
    for root, dirs, files in os.walk(base_folder):
        for dir_name in dirs:
            if dir_name in ["output", "grade"]:
                shutil.rmtree(os.path.join(root, dir_name), ignore_errors=True)
                log(f"Cleaned: {dir_name}", "success", verbosity=2)


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
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".obj"):
                try:
                    os.remove(os.path.join(root, file))
                except Exception as e:
                    log(f"Error deleting {file}: {str(e)}", "error")


def process_folder(folder_name):
    """
    Process a single folder (QX).
    Returns a status string: "success" if all files compiled+ran,
    "warning" if some did, or "error" if none did.
    """
    print("\n\n")
    log(f"Processing folder: {folder_name}...", "info")
    cleanup_folders(folder_name)
    output_folder, grade_folder = ensure_output_folder(folder_name)

    inputs = read_inputs_from_file(folder_name)
    if not inputs:
        log("No inputs available.", "warning")
        # We can consider that a partial error or warning. Let's choose "warning"
        return "warning"

    ground_truth = get_ground_truth(folder_name, inputs)
    if not ground_truth:
        log("Ground truth generation failed.", "error")
        return "error"

    c_files_dir = os.path.join(folder_name, "C")
    if not os.path.isdir(c_files_dir):
        log(f"No 'C' directory found in {folder_name}.", "error")
        return "error"

    c_files_to_process = [
        f for f in os.listdir(c_files_dir)
        if f.endswith(".c") and f != "original_sol.c"
    ]

    if not c_files_to_process:
        log(f"No .c files to process in {c_files_dir}.", "warning")
        return "warning"

    # Compile each .c file
    compiled, compile_errors = parallel_compile_files(c_files_dir, c_files_to_process)

    # Immediately log any compilation errors (and give them a 0% grade)
    for file, error in compile_errors.items():
        grade_path = os.path.join(grade_folder, file.replace(".c", ".txt"))
        write_grade(
            grade_path=grade_path,
            correct_count=0,
            total=0,
            discrepancies=None,
            compile_error=error
        )

    # If none compiled, return error
    if len(compiled) == 0:
        log("No files compiled successfully for this folder.", "error")
        return "error"

    # Wait for log to be done
    time.sleep(0.1)

    executables_to_cleanup = []
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {
            executor.submit(
                execute_and_grade, file, executable, inputs, ground_truth,
                output_folder, grade_folder
            ): file
            for file, executable in compiled.items()
        }
        with tqdm(total=len(futures),
                  desc=f"Executing programs in {folder_name}",
                  unit="file",
                  bar_format="\033[94m{l_bar}{bar}{r_bar}\033[0m") as pbar:
            for future in as_completed(futures):
                executable = future.result()
                executables_to_cleanup.append(executable)
                pbar.update(1)

    # Clean up leftover executables
    cleanup_executables(executables_to_cleanup)
    # Summarize all compile errors
    log_compilation_summary(compile_errors)

    # Decide final status for this folder
    # If we compiled some but not all, "warning"
    # If we compiled all, "success"
    total_files = len(c_files_to_process)
    compiled_count = len(compiled)
    if compiled_count == total_files and len(compile_errors) == 0:
        return "success"
    else:
        return "warning"


def process_all_questions(questions_arr):
    """
    Processes each folder in questions_arr.
    At the end, prints a final log message with success/warning/error:
      - success if ALL were "success"
      - warning if at least one was "success" (but not all)
      - error if none were "success"
    """
    results = []
    for question in questions_arr:
        status = process_folder(question)
        results.append((question, status))

    print("\n")

    # Summarize final status
    all_success = all(status == "success" for _, status in results)
    any_success = any(status == "success" for _, status in results)

    if all_success:
        final_status = "success"
        msg = "All Questions processed successfully."
    elif any_success:
        final_status = "warning"
        msg = "Some Questions processed successfully, some had issues."
    else:
        final_status = "error"
        msg = "No Questions were processed successfully."

    # List out each folder and its status
    summary_details = ", ".join(f"{q}({s})" for q, s in results)
    log(f"Processed Questions: {summary_details}. {msg}", final_status)


def run_tests():
    try:
        setup_visual_studio_environment()
        questions = ["Q1", "Q2"]
        process_all_questions(questions)
    finally:
        time.sleep(0.1)
        print("\n")
        cleanup_obj_files()
        log("All temporary files cleaned.", "success")
        print("\nDONE, HAPPY GRADING!")

if __name__ == "__main__":
    run_tests()
