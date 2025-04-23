import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import sys
import io
import os
import re # Import regex module

# Import backend functions
from main import questions, folder_weights # Use questions list and weights from main
from preprocess import preprocess_submissions
from Process import run_tests
from CreateExcel import create_excels
from clear_utils import (
    clear_grades,
    clear_output,
    clear_excels,
    clear_c_files,
    clear_all,
    clear_build_files
)
from Utils import log # For direct logging if needed, though most comes via redirect

ctk.set_appearance_mode("System") # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue") # Themes: "blue" (default), "green", "dark-blue"

class GuiStream(io.StringIO):
    """A custom stream to redirect stdout/stderr to a CTkTextbox."""
    def __init__(self, textbox):
        super().__init__()
        self.textbox = textbox

    def write(self, s):
        # Need to ensure thread-safe update of the GUI
        # Use CTkTextbox's built-in mechanism or schedule update via 'after'
        self.textbox.after(0, self._insert_text, s)

    def _insert_text(self, s):
        try:
            # Clean ANSI codes
            clean_s = re.sub(r'\x1b\[[0-9;]*m', '', s)
            if not clean_s: # Don't process empty strings
                return

            # Determine the tag based on the log level prefix
            normalized_s = clean_s.lstrip() # Remove leading whitespace/newlines
            tag_to_apply = "default_tag"
            if normalized_s.startswith("[INFO]"):
                tag_to_apply = "info_tag"
            elif normalized_s.startswith("[SUCCESS]"):
                tag_to_apply = "success_tag"
            elif normalized_s.startswith("[WARNING]"):
                tag_to_apply = "warning_tag"
            elif normalized_s.startswith("[ERROR]"):
                tag_to_apply = "error_tag"
            # Add other potential prefixes like tqdm progress bar? Unlikely to match.

            # --- Insert and Tag --- 
            self.textbox.configure(state="normal")
            start_index = self.textbox.index(tk.END) # Index before insert
            self.textbox.insert(tk.END, clean_s)
            end_index = self.textbox.index(tk.END)   # Index after insert
            
            # Apply the tag to the inserted range if it's not the default
            if tag_to_apply != "default_tag":
                # Indices are complex, tk.END includes a newline.
                # Tag from the character *before* the end index.
                try:
                    # Adjust for the newline Tkinter automatically adds
                    actual_start = self.textbox.index(f"{start_index} -1c") if start_index != "1.0" else "1.0"
                    actual_end = self.textbox.index(f"{end_index} -1c")
                    # Ensure start is not after end (can happen with rapid updates)
                    if self.textbox.compare(actual_start, "<=", actual_end):
                       self.textbox.tag_add(tag_to_apply, actual_start, actual_end)
                    # else: log to console if needed: print(f"Tagging skipped: start {actual_start} > end {actual_end}")
                except tk.TclError as tag_error:
                    # Handle potential errors during tagging itself, e.g., if indices become invalid
                    print(f"Error applying tag '{tag_to_apply}': {tag_error}") # Log error to console

            self.textbox.configure(state="disabled")
            self.textbox.see(tk.END)
        except tk.TclError:
            # Handle cases where the widget might be destroyed during the update
            pass
        except Exception as e:
             # Catch-all for other unexpected errors during text insertion/tagging
             print(f"Error in GuiStream._insert_text: {e}")

    def flush(self):
        # CTkTextbox updates immediately, so flush is less critical
        pass

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("C Auto Grader GUI")
        self.geometry("800x650")

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Frames --- 
        self.top_frame = ctk.CTkFrame(self, corner_radius=0)
        self.top_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self.top_frame.grid_columnconfigure(0, weight=1)

        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        # --- Top Frame Content (Controls) ---
        self.controls_frame = ctk.CTkFrame(self.top_frame)
        self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.controls_frame.grid_columnconfigure((0, 1, 2), weight=1) # Distribute sections

        # Section 1: Preprocessing
        self.preprocess_frame = ctk.CTkFrame(self.controls_frame)
        self.preprocess_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.preprocess_frame.grid_columnconfigure(0, weight=1)
        self.preprocess_label = ctk.CTkLabel(self.preprocess_frame, text="Preprocessing", font=ctk.CTkFont(size=14, weight="bold"))
        self.preprocess_label.grid(row=0, column=0, padx=10, pady=(10, 5))
        self.zip_path_var = tk.StringVar()
        self.zip_entry = ctk.CTkEntry(self.preprocess_frame, textvariable=self.zip_path_var, placeholder_text="Path to submissions zip", width=200)
        self.zip_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.browse_button = ctk.CTkButton(self.preprocess_frame, text="Browse", command=self.browse_zip)
        self.browse_button.grid(row=2, column=0, padx=10, pady=5)
        self.preprocess_button = ctk.CTkButton(self.preprocess_frame, text="Run Preprocess", command=lambda: self.run_task(self.task_preprocess))
        self.preprocess_button.grid(row=3, column=0, padx=10, pady=(5, 10))

        # Section 2: Grading
        self.grading_frame = ctk.CTkFrame(self.controls_frame)
        self.grading_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.grading_frame.grid_columnconfigure(0, weight=1)
        self.grading_label = ctk.CTkLabel(self.grading_frame, text="Grading", font=ctk.CTkFont(size=14, weight="bold"))
        self.grading_label.grid(row=0, column=0, padx=10, pady=(10, 5))
        self.run_button = ctk.CTkButton(self.grading_frame, text="Run Grading", command=lambda: self.run_task(self.task_run_grading))
        self.run_button.grid(row=1, column=0, padx=10, pady=(5, 10))

        # Section 3: Clear Actions
        self.clear_frame = ctk.CTkFrame(self.controls_frame)
        self.clear_frame.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")
        self.clear_frame.grid_columnconfigure((0,1), weight=1)
        self.clear_label = ctk.CTkLabel(self.clear_frame, text="Clear Actions", font=ctk.CTkFont(size=14, weight="bold"))
        self.clear_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5))
        self.clear_grades_button = ctk.CTkButton(self.clear_frame, text="Clear Grades", command=lambda: self.run_task(lambda: clear_grades(questions)))
        self.clear_grades_button.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.clear_output_button = ctk.CTkButton(self.clear_frame, text="Clear Output", command=lambda: self.run_task(lambda: clear_output(questions)))
        self.clear_output_button.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.clear_c_button = ctk.CTkButton(self.clear_frame, text="Clear C Files", command=lambda: self.run_task(lambda: clear_c_files(questions)))
        self.clear_c_button.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        self.clear_excels_button = ctk.CTkButton(self.clear_frame, text="Clear Excels", command=lambda: self.run_task(clear_excels))
        self.clear_excels_button.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.clear_build_button = ctk.CTkButton(self.clear_frame, text="Clear Build Files", command=lambda: self.run_task(clear_build_files))
        self.clear_build_button.grid(row=3, column=0, padx=5, pady=5, sticky="ew")
        self.clear_all_button = ctk.CTkButton(self.clear_frame, text="Clear All", command=lambda: self.run_task(lambda: clear_all(questions)), fg_color="#D32F2F", hover_color="#B71C1C") # Danger color
        self.clear_all_button.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # --- Log Frame Content ---
        self.log_textbox = ctk.CTkTextbox(self.log_frame, state="disabled", wrap="word", font=("Consolas", 11))
        self.log_textbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Configure tags for log levels
        # Using standard color names, could be themed later if needed
        self.log_textbox.tag_config("info_tag", foreground="#1E88E5") # Blue
        self.log_textbox.tag_config("success_tag", foreground="#4CAF50") # Green
        self.log_textbox.tag_config("warning_tag", foreground="#FF9800") # Orange
        self.log_textbox.tag_config("error_tag", foreground="#F44336") # Red
        # Default tag uses the textbox's default text color (no explicit config needed unless overriding)
        # self.log_textbox.tag_config("default_tag", foreground=self.log_textbox.cget("text_color"))

        # Store active buttons to disable during tasks
        self.active_buttons = [
            self.browse_button, self.preprocess_button, self.run_button,
            self.clear_grades_button, self.clear_output_button, self.clear_c_button,
            self.clear_excels_button, self.clear_build_button, self.clear_all_button
        ]

    def browse_zip(self):
        filepath = filedialog.askopenfilename(
            title="Select Submissions Zip File",
            filetypes=(("Zip files", "*.zip"), ("All files", "*.*"))
        )
        if filepath:
            self.zip_path_var.set(filepath)

    def set_controls_state(self, state):
        """Enable or disable all control buttons."""
        for button in self.active_buttons:
            button.configure(state=state)
        # Special handling for entry?
        # self.zip_entry.configure(state=state)

    def task_wrapper(self, task_func):
        """Wraps the target function to redirect stdio and manage button state."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", tk.END)
        self.log_textbox.configure(state="disabled")
        self.set_controls_state("disabled")

        gui_stream = GuiStream(self.log_textbox)
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = gui_stream
        sys.stderr = gui_stream # Redirect tqdm output here

        try:
            task_func()
            # Optionally add a final success message here if not logged by func
            log("Task completed.", level="success")
        except Exception as e:
            # Log exception to the GUI textbox
            import traceback
            log(f"\n--- TASK FAILED --- \n", level="error")
            log(traceback.format_exc(), level="error")
            messagebox.showerror("Task Error", f"An error occurred: {e}")
        finally:
            # Restore stdout/stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            # Re-enable buttons via 'after' to ensure it happens in the main thread
            self.after(100, lambda: self.set_controls_state("normal"))

    def run_task(self, task_func):
        """Run a function in a separate thread."""
        thread = threading.Thread(target=self.task_wrapper, args=(task_func,), daemon=True)
        thread.start()

    # --- Specific Task Functions ---
    def task_preprocess(self):
        zip_path = self.zip_path_var.get()
        if not zip_path:
            log("Error: No zip file path provided.", level="error")
            messagebox.showerror("Input Error", "Please select a zip file first.")
            return # Don't proceed
        if not os.path.exists(zip_path):
            log(f"Error: Provided zip path does not exist: {zip_path}", level="error")
            messagebox.showerror("Input Error", f"Zip file not found:\n{zip_path}")
            return
        # Simple check, actual validation is in preprocess_submissions
        if not zip_path.lower().endswith('.zip'):
             log(f"Error: Provided file does not appear to be a zip file: {zip_path}", level="warning")
             if not messagebox.askyesno("Potential Issue", f"The selected file doesn't end with .zip:\n{zip_path}\n\nContinue anyway?"):
                 return

        log(f"Starting preprocessing task for: {zip_path}", level="info")
        preprocess_submissions(zip_path, questions)

    def task_run_grading(self):
        log("Starting grading task...", level="info")
        # Encapsulate original grading logic from main
        run_tests(questions)
        create_excels(questions, folder_weights, slim=False)
        log("Grading task functions finished.", level="info") # Let wrapper add final message

if __name__ == "__main__":
    app = App()
    app.mainloop() 