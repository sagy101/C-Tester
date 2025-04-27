import argparse
import os
import sys # Import sys for sys.exit
import zipfile
import subprocess
from Process import run_tests
from CreateExcel import create_excels
from clear_utils import clear_grades, clear_output, clear_excels, clear_c_files, clear_all, clear_build_files
from Utils import log
from preprocess import preprocess_submissions
# Import configuration from the new file
from configuration import questions, folder_weights, penalty, validate_config, winrar_path, vs_path

# Define your parent folders here - REMOVED, now in configuration.py
# questions = ["Q1", "Q2"]

# Weight in percentage for each question - REMOVED, now in configuration.py
# folder_weights = {questions[0]: 50, questions[1]: 50}

def validate_vs_path(path):
    """Validates the Visual Studio environment batch file path."""
    if not path:
        log("Error: Visual Studio path is empty", "error")
        return False
        
    if not os.path.exists(path):
        log(f"Error: Visual Studio path does not exist: {path}", "error")
        return False
        
    if not path.lower().endswith('.bat'):
        log(f"Error: Visual Studio path must be a .bat file: {path}", "error")
        return False
    
    # Test if the batch file can be executed
    try:
        log(f"Validating Visual Studio path: {path}", "info")
        test_cmd = f'cmd /c ""{path}" && echo Success"'
        result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
        
        if result.returncode != 0:
            log(f"Error: Visual Studio batch file execution failed: {result.stderr}", "error")
            return False
            
        # Check if cl.exe is in the path after running vcvars64.bat
        test_cmd = f'cmd /c ""{path}" && where cl.exe"'
        result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
        
        if result.returncode != 0:
            log("Warning: cl.exe compiler not found in the Visual Studio environment path.", "warning")
            log("Grading may not work correctly. Ensure Visual C++ build tools are installed.", "warning")
            # Return true with warning as this isn't a terminal issue
            return True
            
        log("Visual Studio path validation successful", "success")
        return True
    except Exception as e:
        log(f"Error validating Visual Studio path: {str(e)}", "error")
        return False

def validate_winrar_path(path):
    """Validates the WinRAR executable path."""
    if not path:
        log("Error: WinRAR path is empty", "error")
        return False
        
    if not os.path.exists(path):
        log(f"Error: WinRAR path does not exist: {path}", "error")
        return False
        
    if not path.lower().endswith('.exe'):
        log(f"Error: WinRAR path must be an .exe file: {path}", "error")
        return False
    
    # Test if the executable can be run
    try:
        log(f"Validating WinRAR path: {path}", "info")
        
        # For UnRAR.exe, try to get version info
        if 'unrar.exe' in path.lower():
            test_cmd = f'"{path}" -v'
        # For WinRAR.exe, try with /? parameter
        else:
            test_cmd = f'"{path}" /?'
            
        result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
        if result.returncode != 0 and 'unrar.exe' in path.lower():
            log(f"Error: UnRAR executable execution failed: {result.stderr}", "error")
            return False
            
        log("WinRAR path validation successful", "success")
        return True
    except Exception as e:
        log(f"Error validating WinRAR path: {str(e)}", "error")
        return False

def run_grading(questions_to_run, slim_mode=False, per_error_penalty_mode=False):
    """Runs the test and creates the Excel files."""
    # Validate Visual Studio path before grading
    if not validate_vs_path(vs_path):
        log("Cannot proceed with grading due to invalid Visual Studio environment path.", "error")
        sys.exit(1)
        
    log("Starting grading process...", level="info")
    # Pass the globally imported questions list from configuration
    run_tests(questions_to_run)
    
    # Use provided per_error_penalty_mode directly (no longer uses config default)
    # The default is now explicitly False (single penalty mode)
    
    # Log the mode being used
    mode_str = "per error" if per_error_penalty_mode else "once per student"
    log(f"Using penalty mode: {mode_str}", level="info")
    
    # Pass the globally imported weights and penalty from configuration
    create_excels(questions_to_run, folder_weights, penalty, slim=slim_mode, per_error_penalty=per_error_penalty_mode)
    log("\n\nDONE, HAPPY GRADING!", level="success")

if __name__ == "__main__":
    # --- Configuration Validation --- 
    # Validate the imported configuration using the imported validator
    config_errors = validate_config(questions, folder_weights)
    if config_errors:
        log("Configuration errors found:", level="error")
        for error in config_errors:
            log(f"- {error}", level="error")
        sys.exit(1) # Stop execution
    else:
        log("Configuration validated successfully.", level="info")
        
    parser = argparse.ArgumentParser(description="Run grading scripts or clear generated files.")
    subparsers = parser.add_subparsers(dest='command', help='Available commands', required=True) # Make command required

    # Run command
    parser_run = subparsers.add_parser('run', help='Run the grading process (run tests and create excels).')
    parser_run.add_argument('--slim', action='store_true', 
                          help='Generate final_grades.xlsx with only ID and Final_Grade columns.')
    parser_run.add_argument('--per-error-penalty', action='store_true',
                          help='Apply penalty for each submission error (can accumulate).')
    # Removed the --single-penalty option since it's now the default

    # Preprocess command
    parser_preprocess = subparsers.add_parser('preprocess', help='Preprocess submissions from a zip file.')
    parser_preprocess.add_argument('--zip-path', required=True, help='Path to the main zip file containing student submissions.')
    parser_preprocess.add_argument('--rar-support', action='store_true', help='Enable support for RAR submission files.')

    # Clear commands
    parser_clear = subparsers.add_parser('clear', help='Clear generated files.')
    clear_subparsers = parser_clear.add_subparsers(dest='clear_command', help='Specific items to clear', required=True) # Make clear command required
    clear_subparsers.add_parser('grades', help='Clear contents of all <Question>/grades folders.')
    clear_subparsers.add_parser('output', help='Clear contents of all <Question>/output folders.')
    clear_subparsers.add_parser('c', help='Clear contents of all <Question>/C folders.')
    clear_subparsers.add_parser('excels', help='Delete all *.xlsx files.')
    clear_subparsers.add_parser('build', help='Delete all build files (*.exe, *.obj).')
    clear_subparsers.add_parser('all', help='Clear grades, output, excel, and build files.')

    args = parser.parse_args()

    if args.command == 'run':
        # Simplified handling - now we only have one flag (--per-error-penalty)
        # Default mode is single penalty (per_error_penalty=False)
        per_error_penalty_mode = args.per_error_penalty
            
        # Pass the imported config to run_grading
        run_grading(questions, slim_mode=args.slim, per_error_penalty_mode=per_error_penalty_mode)
    elif args.command == 'preprocess':
        # Check if zip path exists
        if not os.path.exists(args.zip_path):
            log(f"Error: Provided zip path does not exist: {args.zip_path}", level="error")
            sys.exit(1) # Exit with error code
        if not zipfile.is_zipfile(args.zip_path):
             log(f"Error: Provided file is not a valid zip file: {args.zip_path}", level="error")
             sys.exit(1)
             
        # Validate WinRAR path if RAR support is enabled
        if args.rar_support and not validate_winrar_path(winrar_path):
            log("Cannot proceed with RAR support due to invalid WinRAR path.", "error")
            sys.exit(1)
             
        # Pass imported questions list
        preprocess_submissions(args.zip_path, questions, rar_support=args.rar_support, winrar_path=winrar_path)
    elif args.command == 'clear':
        # Pass imported questions list
        if args.clear_command == 'grades':
            clear_grades(questions)
        elif args.clear_command == 'output':
            clear_output(questions)
        elif args.clear_command == 'c':
            clear_c_files(questions)
        elif args.clear_command == 'excels':
            clear_excels()
        elif args.clear_command == 'build':
            clear_build_files()
        elif args.clear_command == 'all':
            clear_all(questions)
    # No need for else: parser.print_help() because 'command' is required