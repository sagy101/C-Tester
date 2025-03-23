# Automated C Program Grading and Excel Report Generation

## Overview

This project automates the batch grading of multiple C programs. It sets up the Visual Studio C++ build environment, compiles and executes student C source files against a known-correct solution, compares outputs, and produces grading reports. Additionally, it generates Excel files with detailed grade breakdowns for each question folder as well as a consolidated final grade file for easy uploading (e.g., to Moodle). An optional "slim" feature allows generating a simplified final Excel file that contains only the student IDs and final grades.

## Requirements

- **Operating System:** Windows (script uses `cmd` and Visual Studio’s C++ compiler)
- **Visual Studio 2022:** Community or higher, with C++ build tools installed  
  *Ensure the path to `vcvars64.bat` is correct (default: `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat`).*
- **Python 3:** Tested with standard libraries, plus:
  - `tqdm` for progress bars  
    ```bash
    pip install tqdm
    ```
  - `pandas` and `xlsxwriter` for Excel file creation  
    ```bash
    pip install pandas xlsxwriter
    ```

## Project Structure

The project consists of the following Python files:

- **Process.py**  
  Sets up the Visual Studio environment, reads inputs, compiles and executes C files (excluding `original_sol.c`), compares outputs with a ground truth solution, and writes individual grade text files.
  
- **CreateExcel.py**  
  Scans the grade text files in each question folder, extracts grades (including flags for compilation errors and timeouts), and creates Excel files per folder along with a consolidated final grade file (`final_grades.xlsx`). The slim feature here allows you to generate a simplified Excel file with only final grades if desired.
  
- **main.py**  
  Serves as the entry point by calling the test execution (grading) process and the Excel creation process. It defines the question folders (e.g., `Q1`, `Q2`, `Q3`) and their respective weights.
  
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
   - All C files in the `C` subfolder (excluding `original_sol.c`) are compiled in parallel using Visual Studio’s `cl`.
   - Each compiled executable is run with every input, and the outputs are stored in an `output` folder.
   - Outputs are compared with the ground truth to calculate a grade and to note any discrepancies or timeouts.

4. **Grading:**  
   - For each C file, a grade text file is generated in a `grade` folder (including any compilation errors or timeouts).

5. **Excel Report Generation:**  
   - **Per Folder:** An Excel file is created from the grade text files, extracting student IDs, grades, and error details.
   - **Final Aggregation:** A consolidated `final_grades.xlsx` is generated, which computes weighted final grades based on folder-specific weights (configurable in `main.py`).  
   - **Slim Feature:** You can opt to generate a "slim" final Excel file that contains only the `ID_number` and `Final_Grade` columns, instead of all detailed per-question data.

6. **Cleanup:**  
   Temporary files (e.g., executables, `.obj` files) and previous grading outputs are cleaned before processing.

## Script Usage

1. **Clone/Copy** the project files into your working directory.
2. **Adjust** the path to `vcvars64.bat` in `Process.py` if necessary.
3. **Organize** your question folders (`Q1`, `Q2`, `Q3`, etc.) according to the expected structure.
4. **Install** required Python dependencies:
   ```bash
   pip install tqdm pandas xlsxwriter
   ```
5. **Run** the main script:
   ```bash
   python main.py
   ```
6. **Review** the generated outputs:
   - Individual output and grade text files will be in each question folder.
   - A consolidated Excel file `final_grades.xlsx` is created in the project root.  
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

# Happy Testing and Grading!
```