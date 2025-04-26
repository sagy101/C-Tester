import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import sys
import io
import os
import re # Import regex module

# Import backend functions & default config
# Import defaults from configuration.py now
from configuration import questions as default_questions
from configuration import folder_weights as default_weights
from configuration import penalty as default_penalty # Import default penalty
from configuration import per_error_penalty as default_per_error_penalty # Import default per-error-penalty flag
# Import validator from configuration now
from configuration import validate_config
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

            # Determine the tag
            normalized_s = clean_s.lstrip()
            tag_to_apply = None # Use None for default
            if normalized_s.startswith("[INFO]"):
                tag_to_apply = "info_tag"
            elif normalized_s.startswith("[SUCCESS]"):
                tag_to_apply = "success_tag"
            elif normalized_s.startswith("[WARNING]"):
                tag_to_apply = "warning_tag"
            elif normalized_s.startswith("[ERROR]"):
                tag_to_apply = "error_tag"

            # --- Insert with Tag --- 
            self.textbox.configure(state="normal")
            if tag_to_apply:
                self.textbox.insert(tk.END, clean_s, tag_to_apply)
            else:
                self.textbox.insert(tk.END, clean_s) # Insert without specific tag
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
        self.geometry("1000x750") # Increased width/height

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0) # Progress/Cancel
        self.grid_rowconfigure(2, weight=1) # Logs

        # --- App State (Initialize with defaults) --- 
        self.gui_questions = default_questions[:] # Make copies
        self.gui_weights = default_weights.copy()
        self.gui_penalty = default_penalty # Initialize GUI penalty
        self.gui_per_error_penalty = default_per_error_penalty # Initialize per-error penalty flag
        self.slim_output_var = tk.BooleanVar(value=False) # Variable for slim checkbox
        self.per_error_penalty_var = tk.BooleanVar(value=default_per_error_penalty) # Variable for per-error penalty checkbox
        self.config_valid = False
        self.config_dirty = False # Track unapplied changes
        self.current_task_thread = None
        self.cancel_event = None
        self.config_rows = [] # To store row widgets [q_entry, w_entry]

        # --- Frames --- 
        self.top_frame = ctk.CTkFrame(self, corner_radius=0)
        self.top_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self.top_frame.grid_columnconfigure(0, weight=1)

        self.progress_cancel_frame = ctk.CTkFrame(self)
        self.progress_cancel_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.progress_cancel_frame.grid_columnconfigure(1, weight=1) # Progress bar takes space

        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        # --- Top Frame Content (Controls) ---
        self.controls_frame = ctk.CTkFrame(self.top_frame)
        self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
         # Adjust column weights: Config, Preprocess, Grading, Clear
        self.controls_frame.grid_columnconfigure((0, 1, 2, 3), weight=1) 

        # Section 0: Configuration
        self.config_frame = ctk.CTkFrame(self.controls_frame)
        self.config_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.config_frame.grid_columnconfigure((0, 1), weight=1) # Columns for table
        # Row 1 for headers, Row 2 for table frame (expands), Row 3 for penalty, Row 4 for buttons, Row 5 for status
        self.config_frame.grid_rowconfigure(2, weight=1) 

        self.config_label = ctk.CTkLabel(self.config_frame, text="Configuration", font=ctk.CTkFont(size=14, weight="bold"))
        self.config_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="ew")
        
        # Table Headers
        ctk.CTkLabel(self.config_frame, text="Question Folder", anchor="w").grid(row=1, column=0, padx=10, pady=2, sticky="w")
        ctk.CTkLabel(self.config_frame, text="Weight (%)", anchor="w").grid(row=1, column=1, padx=10, pady=2, sticky="w")
        
        # Frame for the scrollable rows (if needed, or just grid directly)
        self.config_table_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent") # Frame to hold rows
        self.config_table_frame.grid(row=2, column=0, columnspan=2, padx=5, pady=0, sticky="nsew")
        self.config_table_frame.grid_columnconfigure((0, 1), weight=1) # Columns expand
        
        # Penalty Input
        self.penalty_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        self.penalty_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        self.penalty_label = ctk.CTkLabel(self.penalty_frame, text="Submission Error Penalty (%):", anchor="w")
        self.penalty_label.pack(side=tk.LEFT, padx=(0,5))
        self.penalty_entry = ctk.CTkEntry(self.penalty_frame, width=50)
        self.penalty_entry.pack(side=tk.LEFT)
        self.penalty_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty()) 
        
        # Add Per-Error Penalty Checkbox
        self.per_error_penalty_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        self.per_error_penalty_frame.grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        self.per_error_penalty_checkbox = ctk.CTkCheckBox(self.per_error_penalty_frame, 
                                                   text="Apply penalty per error (cumulative)",
                                                   variable=self.per_error_penalty_var,
                                                   onvalue=True, offvalue=False,
                                                   command=self.mark_config_dirty)
        self.per_error_penalty_checkbox.pack(side=tk.LEFT)
        
        # Buttons below table
        self.config_buttons_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        self.config_buttons_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=5)
        self.add_row_button = ctk.CTkButton(self.config_buttons_frame, text="Add Question", command=self.add_new_config_row_action, width=120)
        self.add_row_button.pack(side=tk.LEFT, padx=5)
        self.remove_row_button = ctk.CTkButton(self.config_buttons_frame, text="Remove Last", command=self.remove_last_config_row_action, width=100)
        self.remove_row_button.pack(side=tk.LEFT, padx=5)
        self.apply_config_button = ctk.CTkButton(self.config_buttons_frame, text="Apply Config", command=self.apply_gui_configuration, width=120)
        self.apply_config_button.pack(side=tk.LEFT, padx=5)
        self._default_apply_button_color = self.apply_config_button.cget("border_color") # Store default border

        self.config_status_label = ctk.CTkLabel(self.config_frame, text="Status: Unknown", anchor="w", text_color="gray")
        self.config_status_label.grid(row=6, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

        # Section 1: Preprocessing
        self.preprocess_frame = ctk.CTkFrame(self.controls_frame)
        self.preprocess_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.preprocess_frame.grid_columnconfigure(0, weight=1)
        self.preprocess_label = ctk.CTkLabel(self.preprocess_frame, text="Preprocessing", font=ctk.CTkFont(size=14, weight="bold"))
        self.preprocess_label.grid(row=0, column=0, padx=10, pady=(10, 5))
        self.zip_path_var = tk.StringVar()
        self.zip_entry = ctk.CTkEntry(self.preprocess_frame, textvariable=self.zip_path_var, placeholder_text="Path to submissions zip", width=200)
        self.zip_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.browse_button = ctk.CTkButton(self.preprocess_frame, text="Browse", command=self.browse_zip)
        self.browse_button.grid(row=2, column=0, padx=10, pady=5)
        self.preprocess_button = ctk.CTkButton(self.preprocess_frame, text="Run Preprocess", command=lambda: self.run_task(self.task_preprocess_internal))
        self.preprocess_button.grid(row=3, column=0, padx=10, pady=(5, 10))

        # Section 2: Grading
        self.grading_frame = ctk.CTkFrame(self.controls_frame)
        self.grading_frame.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")
        self.grading_frame.grid_columnconfigure(0, weight=1)
        self.grading_label = ctk.CTkLabel(self.grading_frame, text="Grading", font=ctk.CTkFont(size=14, weight="bold"))
        self.grading_label.grid(row=0, column=0, padx=10, pady=(10, 5))
        self.run_button = ctk.CTkButton(self.grading_frame, text="Run Grading", command=lambda: self.run_task(self.task_run_grading_internal))
        self.run_button.grid(row=1, column=0, padx=10, pady=(5, 5))
        # Add Slim Output Checkbox
        self.slim_checkbox = ctk.CTkCheckBox(self.grading_frame, 
                                           text="Slim Output (ID & Final Grade Only)",
                                           variable=self.slim_output_var,
                                           onvalue=True, offvalue=False)
        self.slim_checkbox.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="w")

        # Section 3: Clear Actions
        self.clear_frame = ctk.CTkFrame(self.controls_frame)
        self.clear_frame.grid(row=0, column=3, padx=10, pady=10, sticky="nsew")
        self.clear_frame.grid_columnconfigure((0,1), weight=1)
        self.clear_label = ctk.CTkLabel(self.clear_frame, text="Clear Actions", font=ctk.CTkFont(size=14, weight="bold"))
        self.clear_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5))
        self.clear_grades_button = ctk.CTkButton(self.clear_frame, text="Clear Grades", command=lambda: self.run_task(lambda: clear_grades(self.gui_questions)))
        self.clear_grades_button.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.clear_output_button = ctk.CTkButton(self.clear_frame, text="Clear Output", command=lambda: self.run_task(lambda: clear_output(self.gui_questions)))
        self.clear_output_button.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.clear_c_button = ctk.CTkButton(self.clear_frame, text="Clear C Files", command=lambda: self.run_task(lambda: clear_c_files(self.gui_questions)))
        self.clear_c_button.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        self.clear_excels_button = ctk.CTkButton(self.clear_frame, text="Clear Excels", command=lambda: self.run_task(clear_excels))
        self.clear_excels_button.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.clear_build_button = ctk.CTkButton(self.clear_frame, text="Clear Build Files", command=lambda: self.run_task(clear_build_files))
        self.clear_build_button.grid(row=3, column=0, padx=5, pady=5, sticky="ew")
        self.clear_all_button = ctk.CTkButton(self.clear_frame, text="Clear All", command=lambda: self.run_task(lambda: clear_all(self.gui_questions)), fg_color="#D32F2F", hover_color="#B71C1C") # Danger color
        self.clear_all_button.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # --- Progress/Cancel Frame Content ---
        self.progress_desc_label = ctk.CTkLabel(self.progress_cancel_frame, text="Idle", anchor="w")
        self.progress_desc_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(self.progress_cancel_frame, orientation="horizontal", mode="determinate")
        self.progress_bar.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.progress_bar.set(0)

        self.cancel_button = ctk.CTkButton(self.progress_cancel_frame, text="Cancel Task", command=self.cancel_current_task, state="disabled", fg_color="#E53935", hover_color="#C62828")
        self.cancel_button.grid(row=0, column=2, padx=(5, 10), pady=5, sticky="e")

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

        self.setup_button_commands() # Bind commands AFTER initial validation might disable them

        # --- Populate initial config & Validate --- 
        self.populate_config_fields()
        self.apply_gui_configuration() # Validate initial config
        self.setup_button_commands() # Bind main task button commands

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
        # Enable/disable cancel button based on task running
        self.cancel_button.configure(state="normal" if state == "disabled" else "disabled")

    def update_progress(self, current_step, total_steps, description="Processing..."):
        """Callback function to update the progress bar and description label."""
        # Update label
        progress_text = f"{description}: {current_step}/{total_steps}"
        self.progress_desc_label.configure(text=progress_text)

        # Update progress bar
        if total_steps > 0:
            progress = float(current_step) / float(total_steps)
            self.progress_bar.set(progress)
        else:
            self.progress_bar.set(0)

    def reset_progress(self):
        """Resets progress bar and label."""
        self.progress_bar.set(0)
        self.progress_desc_label.configure(text="Idle")

    def cancel_current_task(self):
        """Sets the cancel event for the currently running task."""
        if self.cancel_event:
            log("--- Cancel request sent --- ", "warning")
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled", text="Cancelling...") # Indicate cancellation

    def task_wrapper(self, task_func, cancel_event):
        """Wraps the target function for threading, stdio redirect, progress, cancel."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", tk.END)
        self.log_textbox.configure(state="disabled")
        self.set_controls_state("disabled") # Disables main buttons, enables cancel
        self.reset_progress() # Reset progress at start

        gui_stream = GuiStream(self.log_textbox)
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = gui_stream
        sys.stderr = gui_stream

        # Create a GUI-safe progress callback that includes description
        def gui_progress_callback(current, total, description):
            self.after(0, self.update_progress, current, total, description)

        # Determine arguments for the task function
        task_args = {}
        # Check if the target function is one that accepts our args
        if task_func in [self.task_run_grading_internal, self.task_preprocess_internal]:
             task_args['progress_callback'] = gui_progress_callback
             task_args['cancel_event'] = cancel_event

        try:
            task_func(**task_args)
            if not cancel_event.is_set():
                log("Task completed.", level="success")
            else:
                log("Task was cancelled.", level="warning")
        except Exception as e:
            if not cancel_event.is_set(): # Don't show error popup if cancelled
                import traceback
                log(f"\n--- TASK FAILED --- \n", level="error")
                log(traceback.format_exc(), level="error")
                messagebox.showerror("Task Error", f"An error occurred: {e}")
            else:
                 log(f"\n--- TASK CANCELLED with exception ({type(e).__name__}) --- \n", level="warning")
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            self.cancel_event = None # Clear the event
            # Schedule GUI updates for the main thread
            self.after(10, lambda: self.set_controls_state("normal"))
            self.after(10, self.reset_progress)
            self.after(10, lambda: self.cancel_button.configure(text="Cancel Task")) # Reset cancel button text

    def run_task(self, task_func):
        if self.current_task_thread and self.current_task_thread.is_alive():
            messagebox.showwarning("Task Busy", "Another task is currently running.")
            return

        self.cancel_event = threading.Event()
        # Pass the task function AND the cancel event to the wrapper
        self.current_task_thread = threading.Thread(target=self.task_wrapper, args=(task_func, self.cancel_event), daemon=True)
        self.current_task_thread.start()

    # --- Specific Task Functions (Internal implementations called by run_task) ---
    # These now accept the callback/event args if needed
    def task_preprocess_internal(self, progress_callback=None, cancel_event=None):
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
        # Pass the CURRENT GUI config
        preprocess_submissions(zip_path, self.gui_questions, progress_callback, cancel_event)

    def task_run_grading_internal(self, progress_callback=None, cancel_event=None):
        log("Starting grading task...", level="info")
        
        # --- Re-validate configuration just before running --- 
        log("Re-validating configuration before grading...", "info")
        config_errors = validate_config(self.gui_questions, self.gui_weights)
        if config_errors:
            error_string = "Configuration check failed (folder structure changed?):\n\n" + "\n".join([f"- {e}" for e in config_errors])
            error_string += "\n\nPlease check folder contents and re-apply configuration if needed."
            log("Validation failed before grading run.", "error")
            messagebox.showerror("Grading Configuration Error", error_string)
            # Mark config as invalid in the GUI state
            self.config_valid = False 
            self.config_dirty = True # Force user to re-apply
            self.after(10, self.update_dependent_button_states) # Update UI after returning
            self.after(10, lambda: self.config_status_label.configure(text="Status: INVALID", text_color="#F44336")) 
            self.after(10, lambda: self.apply_config_button.configure(border_color="#F44336", border_width=2))
            return # Stop the task
        else:
            log("Configuration validated successfully.", "info")
            
        # --- Proceed with Grading Task --- 
        run_tests(self.gui_questions, progress_callback, cancel_event)
        if not (cancel_event and cancel_event.is_set()):
             # Get slim state from checkbox variable
             slim_mode = self.slim_output_var.get()
             per_error_penalty_mode = self.gui_per_error_penalty
             
             # Log the modes being used
             mode_str = "per error" if per_error_penalty_mode else "once per student"
             log(f"Creating Excel output (Slim mode: {slim_mode}, Penalty mode: {mode_str})...", "info")
             
             # Pass the per_error_penalty parameter
             create_excels(self.gui_questions, self.gui_weights, self.gui_penalty, slim=slim_mode, per_error_penalty=per_error_penalty_mode)
             log("Excel creation finished.", level="info")
        else:
             log("Skipping Excel creation due to cancellation.", "warning")

    # Update button commands to pass CURRENT GUI config where needed
    def setup_button_commands(self):
        # Section 0: Config
        # Apply button already configured
        # Section 1: Preprocessing
        self.preprocess_button.configure(command=lambda: self.run_task(self.task_preprocess_internal))
        # Section 2: Grading
        self.run_button.configure(command=lambda: self.run_task(self.task_run_grading_internal))
        # Section 3: Clear Actions
        self.clear_grades_button.configure(command=lambda: self.run_task(lambda: clear_grades(self.gui_questions)))
        self.clear_output_button.configure(command=lambda: self.run_task(lambda: clear_output(self.gui_questions)))
        self.clear_c_button.configure(command=lambda: self.run_task(lambda: clear_c_files(self.gui_questions)))
        self.clear_excels_button.configure(command=lambda: self.run_task(clear_excels))
        self.clear_build_button.configure(command=lambda: self.run_task(clear_build_files))
        self.clear_all_button.configure(command=lambda: self.run_task(lambda: clear_all(self.gui_questions)))

    def _add_config_row(self, question_name="", weight=""):
        """Adds a row of entry widgets and binds KeyRelease event."""
        row_index = len(self.config_rows)
        q_entry = ctk.CTkEntry(self.config_table_frame)
        q_entry.grid(row=row_index, column=0, padx=5, pady=2, sticky="ew")
        q_entry.insert(0, question_name)
        q_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty())

        w_entry = ctk.CTkEntry(self.config_table_frame, width=80) # Fixed width for weight
        w_entry.grid(row=row_index, column=1, padx=5, pady=2, sticky="ew")
        w_entry.insert(0, str(weight))
        w_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty())

        self.config_rows.append([q_entry, w_entry])

    def add_new_config_row_action(self):
        self._add_config_row()
        self.mark_config_dirty()

    def remove_last_config_row_action(self):
        if not self.config_rows: return
        last_row_widgets = self.config_rows.pop()
        for widget in last_row_widgets:
            widget.destroy()
        self.mark_config_dirty()
        
    def mark_config_dirty(self):
        """Updates UI to show configuration needs applying."""
        if self.config_dirty: return # Already marked
        self.config_dirty = True
        self.config_status_label.configure(text="Status: Unapplied changes", text_color="#FFA000") # Orange
        # Highlight Apply button (e.g., border color)
        self.apply_config_button.configure(border_color="#FFA000", border_width=2) 
        # Disable run buttons when dirty
        self.preprocess_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        log("Configuration changed, please Apply.", "info")

    def populate_config_fields(self):
        """Populates the table and penalty field with the current config."""
        # Clear existing rows
        for row_widgets in self.config_rows:
            for widget in row_widgets:
                widget.destroy()
        self.config_rows = []
        # Add rows from current config
        # Ensure order matches if weights dict order is not guaranteed (Python < 3.7)
        for q_name in self.gui_questions:
             weight = self.gui_weights.get(q_name, "") # Get weight or empty
             self._add_config_row(q_name, weight)
        # Add any weights that might be orphaned (shouldn't happen with validation)
        for q_name, weight in self.gui_weights.items():
            if q_name not in self.gui_questions:
                 self._add_config_row(q_name, weight)
        # Populate penalty
        self.penalty_entry.delete(0, tk.END)
        self.penalty_entry.insert(0, str(self.gui_penalty))
        # Set per-error penalty checkbox
        self.per_error_penalty_var.set(self.gui_per_error_penalty)

    def apply_gui_configuration(self):
        """Parses, validates, updates state, resets dirty flag and UI."""
        parsed_questions = []
        parsed_weights = {}
        parse_errors = []

        for i, row_widgets in enumerate(self.config_rows):
            q_entry, w_entry = row_widgets
            q_name = q_entry.get().strip()
            weight_str = w_entry.get().strip()

            if not q_name and not weight_str:
                continue # Skip completely empty rows
            
            if not q_name:
                 parse_errors.append(f"Row {i+1}: Question folder name cannot be empty.")
                 continue # Skip this row for weight processing
            
            parsed_questions.append(q_name)
            
            try:
                weight = int(weight_str)
                parsed_weights[q_name] = weight
            except ValueError:
                parse_errors.append(f"Row {i+1} ('{q_name}'): Invalid numeric weight '{weight_str}'.")

        # Parse Penalty
        penalty_str = self.penalty_entry.get().strip()
        parsed_penalty = None
        try:
            parsed_penalty = int(penalty_str)
            if parsed_penalty < 0:
                 parse_errors.append("Penalty value cannot be negative.")
                 parsed_penalty = None # Mark as invalid
        except ValueError:
            parse_errors.append(f"Invalid numeric value for Penalty: '{penalty_str}'.")
            
        # Get per-error penalty value
        parsed_per_error_penalty = self.per_error_penalty_var.get()

        if parse_errors:
            messagebox.showerror("Configuration Parse Error", "\n".join(parse_errors))
            self.config_status_label.configure(text="Status: Invalid Input", text_color="#F44336")
            self.config_valid = False
            self.config_dirty = True # Still dirty, needs fixing
            self.apply_config_button.configure(border_color="#F44336", border_width=2) # Error border
            self.update_dependent_button_states()
            return

        validation_errors = validate_config(parsed_questions, parsed_weights)
        status_text = ""
        status_color = "gray"
        apply_border_color = self._default_apply_button_color
        apply_border_width = 1 # Default maybe?
        if hasattr(self.apply_config_button, "_apply_configure_kwargs"): # Get default width
             apply_border_width = self.apply_config_button._apply_configure_kwargs.get("border_width", 1)

        if validation_errors:
             self.config_valid = False
             self.config_dirty = True # Still dirty, needs fixing
             status_text = "Status: INVALID"
             status_color = "#F44336" # Red
             apply_border_color = "#F44336" # Error border
             apply_border_width = 2
             messagebox.showwarning("Configuration Validation Error", "\n".join(validation_errors))
        else:
             self.config_valid = True
             self.config_dirty = False # Applied successfully
             self.gui_questions = parsed_questions
             self.gui_weights = parsed_weights
             self.gui_penalty = parsed_penalty
             self.gui_per_error_penalty = parsed_per_error_penalty
             status_text = "Status: Valid"
             status_color = "#4CAF50" # Green
             # apply_border_color remains default
             log("GUI Configuration Applied and Validated.", "info")

        self.config_status_label.configure(text=status_text, text_color=status_color)
        # Reset Apply button appearance
        self.apply_config_button.configure(border_color=apply_border_color, border_width=apply_border_width)
        self.update_dependent_button_states()

    def update_dependent_button_states(self):
        """Enable/disable buttons based on config validity."""
        state = "normal" if self.config_valid else "disabled"
        self.preprocess_button.configure(state=state)
        self.run_button.configure(state=state)
        # Clear buttons might also depend on questions, enable/disable accordingly
        clear_state = "normal" if self.gui_questions else "disabled"
        self.clear_grades_button.configure(state=clear_state)
        self.clear_output_button.configure(state=clear_state)
        self.clear_c_button.configure(state=clear_state)
        # clear_all depends on questions
        self.clear_all_button.configure(state=clear_state)
        # Excels/Build don't strictly depend on questions list, keep enabled?
        # self.clear_excels_button.configure(state="normal")
        # self.clear_build_button.configure(state="normal")

if __name__ == "__main__":
    app = App()
    app.mainloop() 