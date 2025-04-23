# Automated C Program Grading and Excel Report Generation

## Overview

This project automates the batch grading of multiple C programs. It sets up the Visual Studio C++ build environment, compiles and executes student C source files against a known-correct solution, compares outputs, and produces grading reports. Additionally, it generates Excel files with detailed grade breakdowns for each question folder as well as a consolidated final grade file for easy uploading (e.g., to Moodle). An optional "slim" feature allows generating a simplified final Excel file that contains only the student IDs and final grades.

## Requirements

- **Operating System:** Windows (script uses `cmd` and Visual Studio's C++ compiler)
- **Visual Studio 2022:** Community or higher, with C++ build tools installed  
  *Ensure the path to `vcvars64.bat` is correct (default: `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat`).*
- **Python 3:** Tested with standard libraries, plus dependencies listed in `requirements.txt`.

  Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

## Project Structure

The project consists of the following Python files:

- **gui.py** (New)
  Provides a graphical user interface (GUI) built with CustomTkinter for running the preprocessing, grading, and clearing tasks interactively. Displays logs and progress in the interface.

- **preprocess.py** (New)
  Handles the initial processing of student submissions from a zip archive. Extracts nested zips, identifies student IDs from folder names, finds C files (*_qN.c), renames them to `ID.c`, and moves them to the appropriate `QN/C/` folder. Reports any submissions that couldn't be processed correctly to `submit_error.txt`.

- **Process.py**  
  Sets up the Visual Studio environment, reads inputs, compiles and executes C files (excluding `original_sol.c`), compares outputs with a ground truth solution, and writes individual grade text files.
  
- **CreateExcel.py**  
  Scans the grade text files in each question folder, extracts grades (including flags for compilation errors and timeouts), and creates Excel files per folder along with a consolidated final grade file (`final_grades.xlsx`). The slim feature here allows you to generate a simplified Excel file with only final grades if desired.
  
- **main.py**  
  Serves as the **command-line** entry point for preprocessing, grading, and clearing actions. Also defines the question folders and weights.
  
- **Utils.py**  
  Provides a simple logging function and a configurable verbosity level for console output.

The expected folder structure for each question (e.g., `Q1`, `Q2`, `Q3`) is:

```
│
├─ Q1/
│   ├─ C/
│   │   ├─ file1.c
│   │   ├─ file2.c
│   │   ├─ output folder
│   │   └─ grade folder
│   ├─ original_sol.c
│   ├─ Q1_grades_to_upload.xlsx
│   └─ input.txt
├─ Q2/
│   ├─ C/
│   │   ├─ file1.c
│   │   ├─ file2.c
│   │   ├─ output folder
│   │   └─ grade folder
│   ├─ original_sol.c
│   ├─ Q2_grades_to_upload.xlsx
│   └─ input.txt
├─ CreateExcel.py
├─ final_grades.xlsx
├─ main.py
├─ Process.py
├─ README.md
├─ requirements.txt
└─ Utils.py
```

## How It Works

1. **Setup Visual Studio Environment:**  
   The script runs `vcvars64.bat` to configure the environment for compiling C programs.

2. **Input & Ground Truth Generation:**  
   - Reads test inputs from `input.txt`.
   - Compiles and executes `original_sol.c` to generate correct output (ground truth) for each input.

3. **Compilation and Execution:**  
   - All C files in the `C` subfolder (excluding `original_sol.c`) are compiled in parallel using Visual Studio's `cl`.
   - Each compiled executable is run with every input, and the outputs are stored in an `output` folder.
   - Outputs are compared with the ground truth to calculate a grade and to note any discrepancies or timeouts.

4. **Grading:**  
   - For each C file, a grade text file is generated in a `grade` folder (including any compilation errors or timeouts).

5. **Excel Report Generation:**  
   - **Per Folder:** An Excel file is created from the grade text files, extracting student IDs, grades, and error details.
   - **Final Aggregation:** A consolidated `final_grades.xlsx` is generated, which computes weighted final grades based on folder-specific weights (configurable in `main.py`).  
   - **Slim Feature:** You can opt to generate a "slim" final Excel file that contains only the student IDs and final grades.

6. **Cleanup:**  
   Temporary files (e.g., executables, `.obj` files) and previous grading outputs are cleaned before processing.

## Script Usage

You can run the tool either via the command line (`main.py`) or using the graphical interface (`gui.py`).

### Graphical User Interface (GUI)

1.  **Ensure** all requirements (Visual Studio, Python, dependencies) are installed:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run** the GUI script:
    ```bash
    python gui.py
    ```
3.  **Use the interface:**
    *   **Preprocessing:** Click "Browse" to select the main submissions zip file, then click "Run Preprocess".
    *   **Grading:** Click "Run Grading" to start the compilation and testing process.
    *   **Clear Actions:** Click the desired button to clear specific generated files (grades, output, C files, excels, build files) or click "Clear All".
    *   **Output:** Logs and progress information from the running tasks will appear in the text box at the bottom.

### Command Line Interface (CLI)

1.  **Ensure** requirements are installed.
2.  **Organize** your question folders (`Q1`, `Q2`, `Q3`, etc.) according to the expected structure.
3.  **Adjust** the path to `vcvars64.bat` in `Process.py` if necessary.
4.  **Run** `main.py` with the desired command:

    - **Preprocess submissions from a zip file:**
        ```bash
        python main.py preprocess --zip-path <path_to_your_zip_file.zip>
        ```
        This command extracts submissions from the specified main zip file. It expects the main zip to contain individual zip files for each student (e.g., `Student Name_12345_assign_file_ID.zip`). It then extracts each student zip, finds C files named like `somefile_q1.c`, `another_q2.c`, etc., renames them to `ID.c` (using the ID from the folder name), and places them into the corresponding `Q1/C/`, `Q2/C/`, etc. folders. If any submissions cannot be processed (e.g., missing C files, incorrect folder naming for ID extraction), details are logged to `submit_error.txt`.

    - **Run the full grading process:**
        ```bash
        python main.py run
        ```
        This will execute the tests, compare outputs, and generate all grade files and Excel reports.

    - **Clean up generated files:**
      Use the `clear` command followed by what you want to clear:
        - Clear grades folders:
            ```bash
            python main.py clear grades
            ```
        - Clear output folders:
            ```bash
            python main.py clear output
            ```
        - Clear C source folders (removes student code copies in `QN/C/`):
            ```bash
            python main.py clear c
            ```
        - Delete all build files (`*.exe`, `*.obj`):
            ```bash
            python main.py clear build
            ```
        - Clear grades, output, excel, and build files together:
            ```bash
            python main.py clear all
            ```
            *(Note: `clear all` does not include `clear c`)*

    - **View help:**
        ```bash
        python main.py --help
        ```
        This displays all available commands and their descriptions.

6. **Review** the generated outputs:
   - Individual output and grade text files will be in each question folder (if not cleared).
   - A consolidated Excel file `final_grades.xlsx` is created in the project root (if not cleared).
     *Optionally, you can enable the slim mode in the Excel creation process to generate a simplified final grade file.*

## Customization

- **VERBOSITY_LEVEL:**  
  Adjust this in `Utils.py` for more or less console output.
- **Timeouts and Worker Settings:**  
  Timeout duration for each executable run and maximum parallel workers (default: `os.cpu_count()`) can be modified in `Process.py`.
- **Slim Feature:**  
  In `CreateExcel.py`, set the `slim` parameter to `True` when calling `create_excels()` to generate a final Excel file with only the student IDs and final grades. Setting it to `False` will include detailed per-question data.

## Troubleshooting

- **Missing `cl.exe` or Build Tools:**  
  Verify that Visual Studio with C++ build tools is installed and the path to `vcvars64.bat` is correct.
- **Missing or Incorrect `input.txt`:**  
  Ensure each question folder contains a properly formatted `input.txt`.
- **Compilation Failures:**  
  Check the grade text files for error messages; ensure that the source code in the `C` folder adheres to C standards.

### GUI / Tkinter Issues

- **Error: `ModuleNotFoundError: No module named 'tkinter'` when running `gui.py`:**
  This means the Tkinter library, which the GUI depends on, is not found in your Python environment. Tkinter relies on a Tcl/Tk installation that should be included with your base Python installation.
  - **Solution:**
    1.  Ensure your base Python installation includes Tcl/Tk. If you installed Python from python.org, run the installer again, choose "Modify", and make sure the "tcl/tk and IDLE" feature is checked.
    2.  After modifying your base Python, it's recommended to **recreate** your virtual environment (`.venv`) to ensure it correctly links to the updated base Python. Deactivate the current environment (if active), delete the `.venv` folder, create a new one (`python -m venv .venv` or `py -m venv .venv`), activate it, and reinstall dependencies (`pip install -r requirements.txt`).
    3.  You can test if Tkinter is available in your active environment by running `python -m tkinter` in the terminal. A small test window should appear.

- **Network Errors during `pip install -r requirements.txt` (e.g., `WinError 10013`)**
  This usually indicates a problem connecting to the Python Package Index (PyPI). It might be caused by a firewall, proxy server, or antivirus software interfering with the connection. Check your network settings and security software configurations.

# Happy Testing and Grading!
```