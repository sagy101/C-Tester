## Overview

This Python script automates the process of:
1. Setting up a Visual Studio C++ build environment (on Windows).
2. Discovering `.c` source files within specified question directories (e.g., `Q1`, `Q2` `...`).
3. Compiling them in parallel using Visual Studio's `cl`.
4. Executing each compiled program with inputs read from `input.txt`.
5. Comparing their outputs with a "ground truth" output produced by `original_sol.c`.
6. Generating an `output` folder containing the results from each program.
7. Generating a `grade` folder containing a grade file (`.txt`) for each `.c` file.

This script is primarily intended for batch grading or testing of multiple C programs against a known correct solution, using a uniform set of inputs.

---

## Requirements

- **Windows OS** (since it relies on `cmd` and the Visual Studio `cl` compiler).
- **Visual Studio 2022** (Community or above), installed with C++ build tools.
- A valid path to `vcvars64.bat` (or equivalent) so the script can set the required environment variables. 
  - By default, the script uses:
    ```bash
    C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat
    ```
- **Python 3** (tested with `concurrent.futures`, `tqdm`, etc.).
- **tqdm** Python package for progress bars:
  ```bash
  pip install tqdm
  ```

---

## Project Structure

The script expects a folder structure like this (for each question):

```
Q1/
 ├─ C/
 │   ├─ file1.c
 │   └─ file2.c
 ├─ original_sol.c
 └─ input.txt

Q2/
 ├─ C/
 │   ├─ fileA.c
 │   └─ fileB.c
 ├─ original_sol.c
 └─ input.txt
 
 .
 .
 .
```

- Each question folder (e.g., `Q1`, `Q2`) must contain:
  - An **input file**: `input.txt`  
    - Holds multiple lines, each used as an input for compiled programs.
  - A **subfolder**: `C`  
    - Contains one or more `.c` files (solution attempts).
    - Contains a special file named `original_sol.c`, which is treated as the "ground truth" solution.

---

## How It Works

1. **Setup Visual Studio Environment**  
   - The function `setup_visual_studio_environment()` runs the `vcvars64.bat` script to ensure `cl` and related environment variables are available.

2. **process_all_questions()**  
   - Calls `process_folder()` for each question directory in the `questions` list.

3. **process_folder()**  
   - **Cleanup**: Removes any old `output` and `grade` folders before starting.  
   - **Input Loading**: Reads `input.txt` from the question folder.  
   - **Ground Truth Generation**: Compiles and runs `original_sol.c`, saving its outputs for each input line.  
   - **Compile & Run**:
     - All `.c` files except `original_sol.c` get compiled in parallel.  
     - If compilation fails, a 0% grade is written for that file.  
     - If successful, the compiled executable is run with each input, and the output is saved.  
   - **Comparison & Grading**:
     - Each program’s output is compared to the ground truth.  
     - A text file summarizing the grade and any discrepancies is generated in the `grade` folder.

4. **Parallel Compilation & Execution**  
   - Uses `concurrent.futures.ThreadPoolExecutor` to run compile and execute tasks in parallel.  
   - Displays progress bars with `tqdm`.

5. **Cleanup**  
   - After processing, cleans up `.exe` files, `.obj` files, and old `output` / `grade` folders.

---

## Script Usage

1. **Clone/Copy** this script into a `.py` file (e.g., `run_tests.py`).  
2. **Adjust** the path to `vcvars64.bat` in `setup_visual_studio_environment()` if your Visual Studio installation is in a different location.  
3. **Place** your question folders (e.g., `Q1`, `Q2`, etc.) in the same directory as this script, matching the structure above.  
4. **Install** Python dependencies (at least `tqdm`):
   ```bash
   pip install tqdm
   ```
5. **Run** the script:
   ```bash
   python run_tests.py
   ```
6. **Check** each question folder for the newly created `output` and `grade` folders.

---

## Customization

- **VERBOSITY_LEVEL**:  
  Set in the script; higher values yield more detailed console output.  
- **Timeout**:  
  The `run_executable()` function allows specifying a `timeout`. Default is 30 seconds.  
- **Max Workers**:  
  The script uses `os.cpu_count()` for parallel tasks. Modify if needed.

---

## Troubleshooting

- **Missing `cl.exe`**:  
  Ensure you have installed the C++ build tools for Visual Studio.  
  Run Developer Command Prompt for Visual Studio or double-check the `vcvars64.bat` path.
- **No `input.txt`**:  
  If there's no input file, the script will generate a warning, and the question might receive a partial or zero grade.

---

# Happy testing and grading!