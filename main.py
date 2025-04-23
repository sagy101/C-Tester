import argparse
import os
import sys # Import sys for sys.exit
import zipfile
from Process import run_tests
from CreateExcel import create_excels
from clear_utils import clear_grades, clear_output, clear_excels, clear_c_files, clear_all, clear_build_files
from Utils import log
from preprocess import preprocess_submissions
# Import configuration from the new file
from configuration import questions, folder_weights, penalty, validate_config

# Define your parent folders here - REMOVED, now in configuration.py
# questions = ["Q1", "Q2"]

# Weight in percentage for each question - REMOVED, now in configuration.py
# folder_weights = {questions[0]: 50, questions[1]: 50}

def run_grading(questions_to_run):
    """Runs the test and creates the Excel files."""
    log("Starting grading process...", level="info")
    # Pass the globally imported questions list from configuration
    run_tests(questions_to_run)
    # Pass the globally imported weights and penalty from configuration
    create_excels(questions_to_run, folder_weights, penalty, slim=False)
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

    # Preprocess command
    parser_preprocess = subparsers.add_parser('preprocess', help='Preprocess submissions from a zip file.')
    parser_preprocess.add_argument('--zip-path', required=True, help='Path to the main zip file containing student submissions.')

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
        # Pass the imported config to run_grading
        run_grading(questions)
    elif args.command == 'preprocess':
        # Check if zip path exists
        if not os.path.exists(args.zip_path):
            log(f"Error: Provided zip path does not exist: {args.zip_path}", level="error")
            sys.exit(1) # Exit with error code
        if not zipfile.is_zipfile(args.zip_path):
             log(f"Error: Provided file is not a valid zip file: {args.zip_path}", level="error")
             sys.exit(1)
        # Pass imported questions list
        preprocess_submissions(args.zip_path, questions)
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
