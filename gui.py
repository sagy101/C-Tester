import importlib.util
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

REQUIRED_IMPORTS = {
    "colorama": "colorama",
    "customtkinter": "customtkinter",
    "dateutil": "python-dateutil",
    "docx": "python-docx",
    "et_xmlfile": "et_xmlfile",
    "fitz": "pymupdf",
    "lxml": "lxml",
    "numpy": "numpy",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
    "pypdf": "pypdf",
    "pytz": "pytz",
    "rarfile": "rarfile",
    "six": "six",
    "tqdm": "tqdm",
    "tzdata": "tzdata",
    "xlsxwriter": "XlsxWriter",
}


def missing_required_packages():
    return [
        package_name
        for import_name, package_name in REQUIRED_IMPORTS.items()
        if importlib.util.find_spec(import_name) is None
    ]


def show_requirements_error(missing_packages):
    install_command = f'"{sys.executable}" -m pip install -r requirements.txt'
    root = tk.Tk()
    root.title("Missing Python Requirements")
    root.geometry("720x360")
    root.minsize(620, 300)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(2, weight=1)

    tk.Label(
        root,
        text="Some Python packages required by the grader are missing.",
        font=("Segoe UI", 13, "bold"),
        anchor="w",
    ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
    tk.Label(
        root,
        text="Install them for this Python interpreter, then restart the GUI.",
        anchor="w",
    ).grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")

    details = tk.Text(root, wrap="word", height=8)
    details.grid(row=2, column=0, padx=16, pady=8, sticky="nsew")
    details.insert(
        "1.0",
        "Missing packages:\n"
        + "\n".join(f"- {package}" for package in sorted(set(missing_packages)))
        + "\n\nRun this command from the project folder:\n"
        + install_command,
    )
    details.configure(state="disabled")

    button_frame = tk.Frame(root)
    button_frame.grid(row=3, column=0, padx=16, pady=(8, 16), sticky="e")

    def copy_command():
        root.clipboard_clear()
        root.clipboard_append(install_command)

    tk.Button(button_frame, text="Copy Install Command", command=copy_command).pack(side=tk.LEFT, padx=(0, 8))
    tk.Button(button_frame, text="Close", command=root.destroy).pack(side=tk.LEFT)
    root.mainloop()


missing_packages = missing_required_packages()
if missing_packages:
    show_requirements_error(missing_packages)
    sys.exit(1)


import customtkinter as ctk
import threading
import io
import os
import json
import re # Import regex module
import time

# Import backend functions & default config
# Import defaults from configuration.py now
from configuration import questions as default_questions
from configuration import folder_weights as default_weights
from configuration import penalty as default_penalty # Import default penalty
from configuration import per_error_penalty as default_per_error_penalty # Import default per-error-penalty flag
from configuration import vs_path as default_vs_path # Import default VS path
from configuration import winrar_path as default_winrar_path # Import default WinRAR path
# Import validator from configuration now
from configuration import validate_config
import configuration
from preprocess import detect_submission_naming, preprocess_submissions
from Process import run_tests, setup_visual_studio_environment, read_inputs_from_file, get_ground_truth
from CreateExcel import create_excels
from checker_assistant import (
    DEFAULT_GEMINI_MODEL,
    FakeLLMProvider,
    GeminiProvider,
    assignment_context_for_question,
    audit_cases_with_llm,
    available_checker_templates,
    build_audit_prompt,
    build_suggestion_prompt,
    get_google_api_key,
    list_gemini_models,
    parse_assignment_context,
    run_checker_tests,
    select_audit_cases,
    suggest_checker,
)
from semantic_grading import DEFAULT_CHECKER_CONFIG_PATH, load_checker_config, save_checker_config
from clear_utils import (
    clear_grades,
    clear_output,
    clear_excels,
    clear_c_files,
    clear_all,
    clear_build_files
)
from Utils import log # For direct logging if needed, though most comes via redirect

# Set a modern theme
ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

# Define custom colors
COLORS = {
    "primary": "#3498db",       # Blue for primary elements
    "secondary": "#2ecc71",     # Green for success elements
    "accent": "#9b59b6",        # Purple for accent elements
    "warning": "#f39c12",       # Orange for warnings
    "danger": "#e74c3c",        # Red for danger/errors
    "light_bg": "#f5f5f5",      # Light background
    "dark_bg": "#2c3e50",       # Dark background
    "text_light": "#ecf0f1",    # Light text
    "text_dark": "#34495e",     # Dark text
    "border": "#bdc3c7",        # Border color
    "hover": "#2980b9",         # Hover color for buttons
}

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

        self.title("C Auto Grader")
        self.geometry("1200x900")  # Increased height from 800 to 900
        self.minsize(1300, 800)     # Increased minimum height from 700 to 800
        
        # Add application icon (if available)
        try:
            self.iconbitmap("app_icon.ico")  # You'd need to create this icon file
        except:
            pass  # Silently fail if icon not found

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)  # Progress/Cancel
        self.grid_rowconfigure(2, weight=1)  # Logs

        # --- App State (Initialize with defaults) --- 
        self.gui_questions = default_questions[:]  # Make copies
        self.gui_weights = default_weights.copy()
        self.gui_penalty = default_penalty  # Initialize GUI penalty
        self.gui_per_error_penalty = default_per_error_penalty  # Initialize per-error penalty flag
        self.gui_rar_support = False  # New RAR support variable
        self.gui_vs_path = default_vs_path  # Initialize VS path
        self.gui_winrar_path = default_winrar_path  # Initialize WinRAR path
        self.gui_simple_naming = configuration.use_simple_naming  # Initialize simple naming flag
        self.slim_output_var = tk.BooleanVar(value=False)  # Variable for slim checkbox
        self.per_error_penalty_var = tk.BooleanVar(value=default_per_error_penalty)  # Variable for per-error penalty checkbox
        self.config_valid = False
        self.config_dirty = False  # Track unapplied changes
        self.vs_path_dirty = False  # Track unapplied VS path
        self.winrar_path_dirty = False  # Track unapplied WinRAR path
        self.current_task_thread = None
        self.cancel_event = None
        self.config_rows = []  # To store row widgets [q_entry, w_entry]

        # --- Frames with enhanced styling --- 
        # Top frame with a subtle header background
        self.top_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "gray20"))
        self.top_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=(15, 5))
        self.top_frame.grid_columnconfigure(0, weight=1)

        # Progress bar in its own frame with refined styling
        self.progress_cancel_frame = ctk.CTkFrame(self, corner_radius=10)
        self.progress_cancel_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=10)
        self.progress_cancel_frame.grid_columnconfigure(1, weight=1)  # Progress bar takes space

        # Log frame with increased padding and rounded corners
        self.log_frame = ctk.CTkFrame(self, corner_radius=10)
        self.log_frame.grid(row=2, column=0, sticky="nsew", padx=15, pady=(5, 15))
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        # --- Top Frame Content (Controls) ---
        self.controls_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        # Adjust column weights to provide more space for config which needs more width
        self.controls_frame.grid_columnconfigure(0, weight=3)  # Config gets more space
        self.controls_frame.grid_columnconfigure((1, 2, 3), weight=2)  # Other sections
        self.controls_frame.grid_rowconfigure(0, weight=1)  # Main sections row
        self.controls_frame.grid_rowconfigure(1, weight=0)  # Dependencies row

        # Section 0: Configuration - Now spans rows 0-1
        self.config_frame = ctk.CTkFrame(self.controls_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.config_frame.grid(row=0, column=0, rowspan=2, padx=10, pady=10, sticky="nsew")  # Added rowspan=2 to span both rows
        self.config_frame.grid_columnconfigure((0, 1), weight=1)  # Columns for table
        # Row 1 for headers, Row 2 for table frame (expands), Row 3 for penalty, Row 4 for buttons, Row 5 for status
        self.config_frame.grid_rowconfigure(2, weight=1) 

        # Section title with icon-like emoji and better font
        self.config_label = ctk.CTkLabel(
            self.config_frame, 
            text="⚙️ Configuration", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["primary"]
        )
        self.config_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="w")
        
        # Table Headers with improved styling
        header_font = ctk.CTkFont(size=12, weight="bold")
        ctk.CTkLabel(self.config_frame, text="Question Folder", anchor="w", font=header_font).grid(
            row=1, column=0, padx=10, pady=5, sticky="w"
        )
        ctk.CTkLabel(self.config_frame, text="Weight (%)", anchor="w", font=header_font).grid(
            row=1, column=1, padx=10, pady=5, sticky="w"
        )
        
        # Frame for the scrollable rows with subtle background
        self.config_table_frame = ctk.CTkFrame(self.config_frame, fg_color=("gray95", "gray17"))
        self.config_table_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.config_table_frame.grid_columnconfigure((0, 1), weight=1)  # Columns expand
        
        # Penalty Input with cleaner layout
        self.penalty_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        self.penalty_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        self.penalty_label = ctk.CTkLabel(self.penalty_frame, text="Submission Error Penalty (%):", anchor="w")
        self.penalty_label.pack(side=tk.LEFT, padx=(0,10))
        self.penalty_entry = ctk.CTkEntry(self.penalty_frame, width=60, border_width=1)
        self.penalty_entry.pack(side=tk.LEFT)
        self.penalty_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty()) 
        
        # Add Per-Error Penalty Checkbox with improved spacing
        self.per_error_penalty_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        self.per_error_penalty_frame.grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        self.per_error_penalty_checkbox = ctk.CTkCheckBox(
            self.per_error_penalty_frame, 
            text="Apply penalty per error (cumulative)",
            variable=self.per_error_penalty_var,
            onvalue=True, offvalue=False,
            command=self.mark_config_dirty,
            border_width=2,
            hover=True,
            width=250  # Ensure enough width for the text
        )
        self.per_error_penalty_checkbox.pack(side=tk.LEFT, padx=(0, 15))
        
        # Buttons with improved styling and spacing
        self.config_buttons_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        self.config_buttons_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=10)
        self.add_row_button = ctk.CTkButton(
            self.config_buttons_frame, 
            text="➕ Add Question", 
            command=self.add_new_config_row_action,
            width=130,
            height=32,
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.add_row_button.pack(side=tk.LEFT, padx=5)
        
        self.remove_row_button = ctk.CTkButton(
            self.config_buttons_frame, 
            text="➖ Remove Last", 
            command=self.remove_last_config_row_action,
            width=130,
            height=32,
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.remove_row_button.pack(side=tk.LEFT, padx=5)
        
        # Apply button
        self.apply_config_button = ctk.CTkButton(
            self.config_buttons_frame, 
            text="Apply Config", 
            command=self.apply_gui_configuration,
            width=140,
            height=32,
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.apply_config_button.pack(side=tk.LEFT, padx=5)
        
        # Store the default border color - fixed to avoid AttributeError
        self._default_border_color = self.apply_config_button.cget("border_color")

        # Status label with better formatting
        self.config_status_label = ctk.CTkLabel(
            self.config_frame, 
            text="Status: Unknown", 
            anchor="w", 
            text_color="gray",
            height=25
        )
        self.config_status_label.grid(row=6, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="ew")

        # Section 1: Preprocessing
        self.preprocess_frame = ctk.CTkFrame(self.controls_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.preprocess_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.preprocess_frame.grid_columnconfigure(0, weight=1)
        
        self.preprocess_label = ctk.CTkLabel(
            self.preprocess_frame, 
            text="📂 Preprocessing", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["primary"]
        )
        self.preprocess_label.grid(row=0, column=0, padx=10, pady=(10, 15))
        
        # Zip file selection with improved styling and more width
        self.zip_path_var = tk.StringVar()
        zip_entry_frame = ctk.CTkFrame(self.preprocess_frame, fg_color="transparent")
        zip_entry_frame.grid(row=1, column=0, padx=15, pady=(5, 10), sticky="ew")
        zip_entry_frame.grid_columnconfigure(0, weight=1)
        
        self.zip_entry = ctk.CTkEntry(
            zip_entry_frame, 
            textvariable=self.zip_path_var, 
            placeholder_text="Path to submissions zip",
            height=32,
            border_width=1
        )
        self.zip_entry.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        # Add binding to check preprocess button state when path changes
        self.zip_path_var.trace_add("write", lambda *args: self.check_preprocess_button_state())
        
        # Browse button with icon
        self.browse_button = ctk.CTkButton(
            self.preprocess_frame, 
            text="📁 Browse", 
            command=self.browse_zip,
            height=32,
            width=200,  # Make button wider
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.browse_button.grid(row=2, column=0, padx=15, pady=(0, 15))
        
        # Run preprocess button with improved styling
        self.preprocess_button = ctk.CTkButton(
            self.preprocess_frame, 
            text="▶️ Run Preprocess", 
            command=lambda: self.run_task(self.task_preprocess_internal),
            height=36,
            width=200,  # Make button wider
            corner_radius=6,
            hover=True,
            border_spacing=6,
            fg_color=COLORS["secondary"],
            hover_color=("#2aa65a", "#216e3d")  # Darker green on hover
        )
        self.preprocess_button.grid(row=3, column=0, padx=15, pady=(0, 15))
        
        # Add RAR support checkbox to preprocessing section where it belongs logically
        self.rar_support_frame = ctk.CTkFrame(self.preprocess_frame, fg_color="transparent")
        self.rar_support_frame.grid(row=4, column=0, padx=15, pady=(0, 10), sticky="w")
        
        self.rar_support_var = tk.BooleanVar(value=False)
        self.rar_support_checkbox = ctk.CTkCheckBox(
            self.rar_support_frame, 
            text="Enable RAR file support",
            variable=self.rar_support_var,
            command=self.update_rar_dependency_state,
            border_width=2,
            hover=True,
            width=200  # Ensure enough width for the text
        )
        self.rar_support_checkbox.pack(side=tk.LEFT)
        
        # Add help note for RAR support with improved styling
        self.rar_help_frame = ctk.CTkFrame(self.preprocess_frame, fg_color="transparent")
        self.rar_help_frame.grid(row=5, column=0, padx=15, pady=(0, 5), sticky="w")
        self.rar_help_label = ctk.CTkLabel(
            self.rar_help_frame, 
            text="requires rarfile package and WinRAR installed",
            font=("", 10),
            text_color="gray"
        )
        self.rar_help_label.pack(side=tk.LEFT)

        # Add Simple Naming checkbox
        self.simple_naming_frame = ctk.CTkFrame(self.preprocess_frame, fg_color="transparent")
        self.simple_naming_frame.grid(row=6, column=0, padx=15, pady=(0, 10), sticky="w")
        
        self.simple_naming_var = tk.BooleanVar(value=configuration.use_simple_naming)
        self.simple_naming_checkbox = ctk.CTkCheckBox(
            self.simple_naming_frame, 
            text="Use simple file naming (hw[0-9].c)",
            variable=self.simple_naming_var,
            command=self.update_simple_naming_state,
            border_width=2,
            hover=True,
            width=250  # Ensure enough width for the text
        )
        self.simple_naming_checkbox.pack(side=tk.LEFT)
        
        # Add help note for Simple Naming
        self.simple_naming_help_frame = ctk.CTkFrame(self.preprocess_frame, fg_color="transparent")
        self.simple_naming_help_frame.grid(row=7, column=0, padx=15, pady=(0, 5), sticky="w")
        self.simple_naming_help_label = ctk.CTkLabel(
            self.simple_naming_help_frame, 
            text="auto-detected from the selected zip; plain hw123.c is treated as Q1",
            font=("", 10),
            text_color="gray"
        )
        self.simple_naming_help_label.pack(side=tk.LEFT)

        self.naming_detection_label = ctk.CTkLabel(
            self.preprocess_frame,
            text="Select a submissions zip to auto-detect file naming.",
            font=("", 10),
            text_color="gray",
            anchor="w",
            justify="left",
            wraplength=260,
        )
        self.naming_detection_label.grid(row=8, column=0, padx=15, pady=(0, 10), sticky="ew")

        # Section 2: Grading
        self.grading_frame = ctk.CTkFrame(self.controls_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.grading_frame.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")
        self.grading_frame.grid_columnconfigure(0, weight=1)
        
        self.grading_label = ctk.CTkLabel(
            self.grading_frame, 
            text="📊 Grading", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["primary"]
        )
        self.grading_label.grid(row=0, column=0, padx=10, pady=(10, 15))
        
        # Run grading button with improved styling
        self.run_button = ctk.CTkButton(
            self.grading_frame, 
            text="📝 Run Grading", 
            command=lambda: self.run_task(self.task_run_grading_internal),
            height=36,
            width=200,  # Make button wider
            corner_radius=6,
            hover=True,
            border_spacing=6,
            fg_color=COLORS["accent"],
            hover_color=("#8649a3", "#61347a")  # Darker purple on hover
        )
        self.run_button.grid(row=1, column=0, padx=15, pady=(5, 15))
        
        # Add Slim Output Checkbox with improved styling
        self.slim_checkbox_frame = ctk.CTkFrame(self.grading_frame, fg_color="transparent")
        self.slim_checkbox_frame.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="w")
        
        self.slim_checkbox = ctk.CTkCheckBox(
            self.slim_checkbox_frame, 
            text="Slim Output (ID & Grade Only)",  # Shortened text slightly
                                           variable=self.slim_output_var,
            onvalue=True, 
            offvalue=False,
            border_width=2,
            hover=True,
            width=250  # Adjusted width
        )
        self.slim_checkbox.pack(side=tk.LEFT)

        self.checker_manager_button = ctk.CTkButton(
            self.grading_frame,
            text="🧪 Checker Manager",
            command=self.open_checker_manager,
            height=36,
            width=200,
            corner_radius=6,
            hover=True,
            border_spacing=6,
            fg_color=COLORS["primary"],
            hover_color=COLORS["hover"]
        )
        self.checker_manager_button.grid(row=3, column=0, padx=15, pady=(0, 15))

        self.open_excel_button = ctk.CTkButton(
            self.grading_frame,
            text="📄 Open Final Excel",
            command=self.open_final_excel,
            height=32,
            width=200,
            corner_radius=6,
            hover=True,
            border_spacing=6,
            state="disabled"
        )
        self.open_excel_button.grid(row=4, column=0, padx=15, pady=(0, 8))

        self.open_folder_button = ctk.CTkButton(
            self.grading_frame,
            text="📂 Open Output Folder",
            command=self.open_output_folder,
            height=32,
            width=200,
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.open_folder_button.grid(row=5, column=0, padx=15, pady=(0, 15))

        # Section 3: Clear Actions
        self.clear_frame = ctk.CTkFrame(self.controls_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.clear_frame.grid(row=0, column=3, padx=10, pady=10, sticky="nsew")
        self.clear_frame.grid_columnconfigure((0,1), weight=1)
        
        self.clear_label = ctk.CTkLabel(
            self.clear_frame, 
            text="🧹 Clear Actions", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["primary"]
        )
        self.clear_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 15))
        
        button_height = 32
        button_corner = 6
        button_width = 120  # Explicit width for clear buttons
        
        # Clear buttons with improved styling and icons
        self.clear_grades_button = ctk.CTkButton(
            self.clear_frame, 
            text="Clear Grades", 
            command=lambda: self.run_task(lambda: clear_grades(self.gui_questions)),
            height=button_height,
            width=button_width,
            corner_radius=button_corner,
            hover=True
        )
        self.clear_grades_button.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        
        self.clear_output_button = ctk.CTkButton(
            self.clear_frame, 
            text="Clear Output", 
            command=lambda: self.run_task(lambda: clear_output(self.gui_questions)),
            height=button_height,
            width=button_width,
            corner_radius=button_corner,
            hover=True
        )
        self.clear_output_button.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        self.clear_c_button = ctk.CTkButton(
            self.clear_frame, 
            text="Clear C Files", 
            command=lambda: self.run_task(lambda: clear_c_files(self.gui_questions)),
            height=button_height,
            width=button_width,
            corner_radius=button_corner,
            hover=True
        )
        self.clear_c_button.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        
        self.clear_excels_button = ctk.CTkButton(
            self.clear_frame, 
            text="Clear Excels", 
            command=lambda: self.run_task(clear_excels),
            height=button_height,
            width=button_width,
            corner_radius=button_corner,
            hover=True
        )
        self.clear_excels_button.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        self.clear_build_button = ctk.CTkButton(
            self.clear_frame, 
            text="Clear Build Files", 
            command=lambda: self.run_task(clear_build_files),
            height=button_height,
            width=button_width,
            corner_radius=button_corner,
            hover=True
        )
        self.clear_build_button.grid(row=3, column=0, padx=5, pady=5, sticky="ew")
        
        self.clear_all_button = ctk.CTkButton(
            self.clear_frame, 
            text="Clear All", 
            command=lambda: self.run_task(lambda: clear_all(self.gui_questions)), 
            fg_color=COLORS["danger"],
            hover_color=("#c0392b", "#922b21"),  # Darker red on hover
            height=button_height,
            width=button_width,
            corner_radius=button_corner,
            hover=True
        )
        self.clear_all_button.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # Section 4: Dependencies - Now placed in row 1, spanning columns 1-3
        self.dependencies_frame = ctk.CTkFrame(self.controls_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.dependencies_frame.grid(row=1, column=1, columnspan=3, padx=10, pady=(5, 10), sticky="ew")  # Span columns 1-3 in row 1
        self.dependencies_frame.grid_columnconfigure((0, 1, 2), weight=1)  # Equal weights for 3 sections

        # Title for Dependencies section
        self.dependencies_label = ctk.CTkLabel(
            self.dependencies_frame, 
            text="🔌 Dependencies", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["primary"]
        )
        self.dependencies_label.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 15), sticky="w")

        # Visual Studio Path - Column 0-1
        self.vs_path_frame = ctk.CTkFrame(self.dependencies_frame, fg_color="transparent")
        self.vs_path_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.vs_path_frame.grid_columnconfigure(0, weight=1)

        self.vs_path_label = ctk.CTkLabel(
            self.vs_path_frame, 
            text="Visual Studio Path:", 
            anchor="w"
        )
        self.vs_path_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.vs_path_var = tk.StringVar(value=default_vs_path)
        self.vs_path_entry = ctk.CTkEntry(
            self.vs_path_frame, 
            textvariable=self.vs_path_var,
            height=32,
            border_width=1
        )
        self.vs_path_entry.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.vs_path_entry.bind("<KeyRelease>", lambda event: self.mark_vs_path_dirty())

        # VS Path Buttons and Status - Row 2
        self.vs_buttons_frame = ctk.CTkFrame(self.vs_path_frame, fg_color="transparent")
        self.vs_buttons_frame.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        self.vs_buttons_frame.grid_columnconfigure(0, weight=1)
        self.vs_buttons_frame.grid_columnconfigure(1, weight=1)

        self.browse_vs_path_button = ctk.CTkButton(
            self.vs_buttons_frame, 
            text="📁 Browse", 
            command=self.browse_vs_path,
            height=32,
            width=120,
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.browse_vs_path_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.apply_vs_path_button = ctk.CTkButton(
            self.vs_buttons_frame, 
            text="Apply VS Path", 
            command=self.apply_vs_path,
            height=32,
            width=120,
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.apply_vs_path_button.grid(row=0, column=1, padx=5, pady=5, sticky="e")

        self.vs_path_status_label = ctk.CTkLabel(
            self.vs_path_frame, 
            text="Status: Unchecked", 
            anchor="w", 
            text_color="gray",
            height=25
        )
        self.vs_path_status_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")

        # WinRAR Path - Column 2-3
        self.winrar_path_frame = ctk.CTkFrame(self.dependencies_frame, fg_color="transparent")
        self.winrar_path_frame.grid(row=1, column=2, columnspan=2, padx=10, pady=5, sticky="ew")
        self.winrar_path_frame.grid_columnconfigure(0, weight=1)

        self.winrar_path_label = ctk.CTkLabel(
            self.winrar_path_frame, 
            text="WinRAR Path:", 
            anchor="w"
        )
        self.winrar_path_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.winrar_path_var = tk.StringVar(value=default_winrar_path)
        self.winrar_path_entry = ctk.CTkEntry(
            self.winrar_path_frame, 
            textvariable=self.winrar_path_var,
            height=32,
            border_width=1
        )
        self.winrar_path_entry.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.winrar_path_entry.bind("<KeyRelease>", lambda event: self.mark_winrar_path_dirty())

        # WinRAR Path Buttons and Status - Row 2
        self.winrar_buttons_frame = ctk.CTkFrame(self.winrar_path_frame, fg_color="transparent")
        self.winrar_buttons_frame.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        self.winrar_buttons_frame.grid_columnconfigure(0, weight=1)
        self.winrar_buttons_frame.grid_columnconfigure(1, weight=1)

        self.browse_winrar_path_button = ctk.CTkButton(
            self.winrar_buttons_frame, 
            text="📁 Browse", 
            command=self.browse_winrar_path,
            height=32,
            width=120,
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.browse_winrar_path_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.apply_winrar_path_button = ctk.CTkButton(
            self.winrar_buttons_frame, 
            text="Apply WinRAR Path", 
            command=self.apply_winrar_path,
            height=32,
            width=120,
            corner_radius=6,
            hover=True,
            border_spacing=6
        )
        self.apply_winrar_path_button.grid(row=0, column=1, padx=5, pady=5, sticky="e")

        self.winrar_path_status_label = ctk.CTkLabel(
            self.winrar_path_frame, 
            text="Status: Unchecked", 
            anchor="w", 
            text_color="gray",
            height=25
        )
        self.winrar_path_status_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")

        # --- Progress/Cancel Frame Content ---
        self.progress_desc_label = ctk.CTkLabel(
            self.progress_cancel_frame, 
            text="Idle", 
            anchor="w",
            font=ctk.CTkFont(size=12)
        )
        self.progress_desc_label.grid(row=0, column=0, padx=(15, 5), pady=10, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_cancel_frame, 
            orientation="horizontal", 
            mode="determinate",
            height=15,
            progress_color=COLORS["secondary"]
        )
        self.progress_bar.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        self.progress_bar.set(0)

        self.cancel_button = ctk.CTkButton(
            self.progress_cancel_frame, 
            text="Cancel Task", 
            command=self.cancel_current_task, 
            state="disabled", 
            fg_color=COLORS["danger"],
            hover_color=("#c0392b", "#922b21"),  # Darker red on hover
            height=30,
            width=120,
            corner_radius=6
        )
        self.cancel_button.grid(row=0, column=2, padx=(5, 15), pady=10, sticky="e")

        # --- Log Frame Content ---
        # Add a header label for the log section
        self.log_header = ctk.CTkLabel(
            self.log_frame,
            text="📋 Console Output",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        self.log_header.grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))
        
        # The main log text box with improved styling
        self.log_textbox = ctk.CTkTextbox(
            self.log_frame, 
            state="disabled", 
            wrap="word", 
            font=("Consolas", 11),
            corner_radius=6,
            border_width=1,
            border_color=COLORS["border"]
        )
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))

        # Configure tags for log levels with enhanced colors
        self.log_textbox.tag_config("info_tag", foreground=COLORS["primary"])       # Blue
        self.log_textbox.tag_config("success_tag", foreground=COLORS["secondary"])  # Green
        self.log_textbox.tag_config("warning_tag", foreground=COLORS["warning"])    # Orange
        self.log_textbox.tag_config("error_tag", foreground=COLORS["danger"])       # Red

        # Store active buttons to disable during tasks
        self.active_buttons = [
            self.browse_button, self.preprocess_button, self.run_button, self.checker_manager_button,
            self.open_excel_button, self.open_folder_button,
            self.clear_grades_button, self.clear_output_button, self.clear_c_button,
            self.clear_excels_button, self.clear_build_button, self.clear_all_button
        ]

        self.setup_button_commands() # Bind commands AFTER initial validation might disable them

        # --- Populate initial config & Validate --- 
        self.populate_config_fields()
        self.apply_gui_configuration() # Validate initial config
        
        # Perform initial validation of VS and WinRAR paths when the GUI starts
        # Use after() to ensure GUI is fully initialized first
        self.after(100, self.validate_initial_paths)

    def browse_zip(self):
        filepath = filedialog.askopenfilename(
            title="Select Submissions Zip File",
            filetypes=(("Zip files", "*.zip"), ("All files", "*.*"))
        )
        if filepath:
            self.zip_path_var.set(filepath)
            self.detect_and_apply_naming(show_dialog=True)
            # Enable the preprocess button now that a file is selected
            self.check_preprocess_button_state()
        else:
            # If user cancelled the dialog and no file was previously selected
            self.check_preprocess_button_state()

    def detect_and_apply_naming(self, show_dialog=False):
        zip_path = self.zip_path_var.get().strip()
        if not zip_path or not os.path.exists(zip_path) or not zip_path.lower().endswith(".zip"):
            self.naming_detection_label.configure(
                text="Select a submissions zip to auto-detect file naming.",
                text_color="gray",
            )
            return None

        try:
            detection = detect_submission_naming(zip_path)
        except Exception as exc:
            self.naming_detection_label.configure(
                text=f"Could not auto-detect naming: {exc}",
                text_color=COLORS["warning"],
            )
            return None

        recommendation = detection["recommendation"]
        counts = detection["counts"]
        if recommendation == "simple":
            self.simple_naming_var.set(True)
            self.naming_detection_label.configure(
                text=f"Detected simple naming: {counts['simple']} file(s). Plain hw123.c files will be mapped to Q1.",
                text_color=COLORS["secondary"],
            )
        elif recommendation == "standard":
            self.simple_naming_var.set(False)
            self.naming_detection_label.configure(
                text=f"Detected standard naming: {counts['standard']} file(s), e.g. hw123_q1.c.",
                text_color=COLORS["secondary"],
            )
        elif recommendation == "mixed":
            self.simple_naming_var.set(False)
            message = (
                f"Mixed naming detected: {counts['standard']} standard file(s) and {counts['simple']} simple file(s). "
                "Preprocess will handle both: hw123_qN.c goes to QN, plain hw123.c goes to Q1. "
                "If a plain file was meant for Q2 or another question, rename it to include _qN before preprocessing."
            )
            self.naming_detection_label.configure(text=message, text_color=COLORS["warning"])
            if show_dialog:
                messagebox.showinfo("Mixed File Naming Detected", message)
        else:
            self.naming_detection_label.configure(
                text="Could not detect supported C filenames yet. Preprocess will still report exact filename issues.",
                text_color=COLORS["warning"],
            )
        self.update_simple_naming_state()
        return detection

    def check_preprocess_button_state(self):
        """Check if preprocess button should be enabled based on zip file selection and WinRAR validation."""
        zip_path = self.zip_path_var.get().strip()
        
        # First check if a zip file is selected
        if not zip_path:
            self.preprocess_button.configure(state="disabled")
            return
        
        # Then check if RAR support is enabled and WinRAR path is valid
        if self.rar_support_var.get() and self.winrar_path_dirty:
            self.preprocess_button.configure(state="disabled")
        else:
            # If zip is selected and either RAR is disabled or WinRAR path is valid
            self.preprocess_button.configure(
                state="normal",
                fg_color=COLORS["secondary"],
                hover_color=("#2aa65a", "#216e3d")
            )

    def set_controls_state(self, state):
        """Enable or disable all control buttons."""
        for button in self.active_buttons:
            button.configure(state=state)
        if state == "normal":
            self.update_excel_button_state()
        # Special handling for entry?
        # self.zip_entry.configure(state=state)
        # Enable/disable cancel button based on task running
        self.cancel_button.configure(state="normal" if state == "disabled" else "disabled")

    def update_excel_button_state(self):
        state = "normal" if os.path.exists("final_grades.xlsx") else "disabled"
        self.open_excel_button.configure(state=state)

    def open_final_excel(self):
        excel_path = os.path.abspath("final_grades.xlsx")
        if not os.path.exists(excel_path):
            messagebox.showwarning("Excel Not Found", "final_grades.xlsx does not exist yet. Run grading first.")
            self.update_excel_button_state()
            return
        self.open_path(excel_path)

    def open_output_folder(self):
        self.open_path(os.path.abspath("."))

    def open_path(self, path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("Open Failed", f"Could not open:\n{path}\n\n{exc}")

    def update_progress(self, current_step, total_steps, description="Processing..."):
        """Callback function to update the progress bar and description label."""
        # Update label with emoji for visual indicator
        progress_percent = int((current_step / total_steps) * 100) if total_steps > 0 else 0
        progress_text = f"{description}: {current_step}/{total_steps} ({progress_percent}%)"
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
            self.cancel_button.configure(state="disabled", text="Cancelling...")  # Indicate cancellation

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

        self.detect_and_apply_naming(show_dialog=True)

        # Get current RAR support setting from checkbox
        rar_support = self.rar_support_var.get()
        self.gui_rar_support = rar_support
        
        # Get current simple naming setting
        simple_naming = self.simple_naming_var.get()
        self.gui_simple_naming = simple_naming
        configuration.use_simple_naming = simple_naming
        
        log(f"Starting preprocessing task for: {zip_path} (RAR support: {'enabled' if rar_support else 'disabled'}, Simple naming: {'enabled' if simple_naming else 'disabled'})", level="info")
        # Pass the CURRENT GUI config including the WinRAR path
        preprocess_submissions(
            zip_path, 
            self.gui_questions, 
            rar_support, 
            progress_callback, 
            cancel_event, 
            winrar_path=self.gui_winrar_path
        )

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
            self.after(10, lambda: self.config_status_label.configure(text="Status: INVALID", text_color=COLORS["danger"])) 
            self.after(10, lambda: self.apply_config_button.configure(border_color=COLORS["danger"], border_width=2))
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
             self.after(10, self.update_excel_button_state)
        else:
             log("Skipping Excel creation due to cancellation.", "warning")

    def task_clear_excels_internal(self):
        clear_excels()
        self.after(10, self.update_excel_button_state)

    # Update button commands to pass CURRENT GUI config where needed
    def setup_button_commands(self):
        # Section 0: Config
        # Apply button already configured
        # Section 1: Preprocessing
        self.preprocess_button.configure(command=lambda: self.run_task(self.task_preprocess_internal))
        # Section 2: Grading
        self.run_button.configure(command=lambda: self.run_task(self.task_run_grading_internal))
        self.checker_manager_button.configure(command=self.open_checker_manager)
        # Section 3: Clear Actions
        self.clear_grades_button.configure(command=lambda: self.run_task(lambda: clear_grades(self.gui_questions)))
        self.clear_output_button.configure(command=lambda: self.run_task(lambda: clear_output(self.gui_questions)))
        self.clear_c_button.configure(command=lambda: self.run_task(lambda: clear_c_files(self.gui_questions)))
        self.clear_excels_button.configure(command=lambda: self.run_task(self.task_clear_excels_internal))
        self.clear_build_button.configure(command=lambda: self.run_task(clear_build_files))
        self.clear_all_button.configure(command=lambda: self.run_task(lambda: clear_all(self.gui_questions)))

    def open_checker_manager(self):
        existing_window = getattr(self, "checker_manager_window", None)
        if existing_window is not None and existing_window.winfo_exists():
            existing_window.show_on_top()
            return
        self.checker_manager_window = CheckerManagerWindow(self)
        self.checker_manager_window.show_on_top()

    def _add_config_row(self, question_name="", weight=""):
        """Adds a row of entry widgets and binds KeyRelease event."""
        row_index = len(self.config_rows)
        q_entry = ctk.CTkEntry(self.config_table_frame, border_width=1)
        q_entry.grid(row=row_index, column=0, padx=5, pady=3, sticky="ew")
        q_entry.insert(0, question_name)
        q_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty())

        w_entry = ctk.CTkEntry(self.config_table_frame, width=80, border_width=1)  # Fixed width for weight
        w_entry.grid(row=row_index, column=1, padx=5, pady=3, sticky="ew")
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
        if self.config_dirty: return  # Already marked
        self.config_dirty = True
        self.config_status_label.configure(text="Status: Unapplied changes", text_color=COLORS["warning"])
        # Highlight Apply button (e.g., border color)
        self.apply_config_button.configure(border_color=COLORS["warning"], border_width=2) 
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
        # Set RAR support checkbox
        self.rar_support_var.set(self.gui_rar_support)
        # Set simple naming checkbox
        self.simple_naming_var.set(self.gui_simple_naming)

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
                continue  # Skip completely empty rows
            
            if not q_name:
                 parse_errors.append(f"Row {i+1}: Question folder name cannot be empty.")
                 continue  # Skip this row for weight processing
            
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
                 parsed_penalty = None  # Mark as invalid
        except ValueError:
            parse_errors.append(f"Invalid numeric value for Penalty: '{penalty_str}'.")
            
        # Get per-error penalty value
        parsed_per_error_penalty = self.per_error_penalty_var.get()
        
        # Get RAR support value
        parsed_rar_support = self.rar_support_var.get()

        if parse_errors:
            messagebox.showerror("Configuration Parse Error", "\n".join(parse_errors))
            self.config_status_label.configure(text="Status: Invalid Input", text_color=COLORS["danger"])
            self.config_valid = False
            self.config_dirty = True  # Still dirty, needs fixing
            self.apply_config_button.configure(border_color=COLORS["danger"], border_width=2)  # Error border
            self.update_dependent_button_states()
            return

        validation_errors = validate_config(parsed_questions, parsed_weights)
        status_text = ""
        status_color = "gray"
        apply_border_color = self._default_border_color
        apply_border_width = 1  # Default maybe?
        if hasattr(self.apply_config_button, "_apply_configure_kwargs"):  # Get default width
             apply_border_width = self.apply_config_button._apply_configure_kwargs.get("border_width", 1)

        if validation_errors:
             self.config_valid = False
             self.config_dirty = True  # Still dirty, needs fixing
             status_text = "Status: INVALID"
             status_color = COLORS["danger"]
             apply_border_color = COLORS["danger"]  # Error border
             apply_border_width = 2
             
             # Format validation errors with bullet points and better spacing
             formatted_errors = []
             for error in validation_errors:
                 # Parse error to improve formatting
                 if "Folder '" in error and "' not found" in error:
                     parts = error.split("(Expected path: ")
                     if len(parts) > 1:
                         folder_part = parts[0].replace("Configuration error: ", "")
                         path_part = parts[1].rstrip(").") if parts[1].endswith(").") else parts[1].rstrip(")")
                         formatted_errors.append(f"• {folder_part}\n  Expected path: {path_part}")
                     else:
                         formatted_errors.append(f"• {error}")
                 elif "Folder weights sum to" in error:
                     parts = error.split("sum to ")
                     if len(parts) > 1:
                         weight_part = parts[1].split("%")[0]
                         formatted_errors.append(f"• Total weight is {weight_part}%, must be exactly 100%")
                     else:
                         formatted_errors.append(f"• {error}")
                 else:
                     formatted_errors.append(f"• {error}")
             
             messagebox.showwarning("Configuration Validation Error", "\n\n".join(formatted_errors))
        else:
             self.config_valid = True
             self.config_dirty = False  # Applied successfully
             self.gui_questions = parsed_questions
             self.gui_weights = parsed_weights
             self.gui_penalty = parsed_penalty
             self.gui_per_error_penalty = parsed_per_error_penalty
             self.gui_rar_support = parsed_rar_support
             self.gui_simple_naming = self.simple_naming_var.get()
             status_text = "Status: Valid ✓"
             status_color = COLORS["secondary"]  # Green
             # apply_border_color remains default
             log("GUI Configuration Applied and Validated.", "info")

        self.config_status_label.configure(text=status_text, text_color=status_color)
        # Reset Apply button appearance
        self.apply_config_button.configure(border_color=apply_border_color, border_width=apply_border_width)
        self.update_dependent_button_states()

    def update_dependent_button_states(self):
        """Enable/disable buttons based on config validity with enhanced visual feedback."""
        if self.config_valid:
            # Check the preprocess button state separately
            self.check_preprocess_button_state()
            
            # Enable run button only if VS path is valid
            if not self.vs_path_dirty:
                self.run_button.configure(
                    state="normal",
                    fg_color=COLORS["accent"],
                    hover_color=("#8649a3", "#61347a")
                )
            else:
                self.run_button.configure(
                    state="disabled",
                    fg_color=("gray80", "gray30")
                )
            
            # Enable clear buttons if questions exist
            if self.gui_questions:
                clear_state = "normal"
                self.clear_grades_button.configure(state=clear_state)
                self.clear_output_button.configure(state=clear_state)
                self.clear_c_button.configure(state=clear_state)
                self.clear_all_button.configure(state=clear_state)
            else:
                clear_state = "disabled"
                self.clear_grades_button.configure(state=clear_state)
                self.clear_output_button.configure(state=clear_state)
                self.clear_c_button.configure(state=clear_state)
                self.clear_all_button.configure(state=clear_state)
        else:
            # If config is invalid, disable most buttons
            disabled_color = ("gray80", "gray30")
            
            # Disable run button if config is invalid
            self.run_button.configure(
                state="disabled",
                fg_color=disabled_color
            )
            
            # Disable question-dependent clear buttons if config is invalid
            clear_state = "disabled"
            self.clear_grades_button.configure(state=clear_state)
            self.clear_output_button.configure(state=clear_state)
            self.clear_c_button.configure(state=clear_state)
            self.clear_all_button.configure(state=clear_state)
            
            # Check preprocess button state separately
            self.check_preprocess_button_state()

    def browse_vs_path(self):
        filepath = filedialog.askopenfilename(
            title="Select Visual Studio vcvars64.bat",
            filetypes=(("Batch files", "*.bat"), ("All files", "*.*"))
        )
        if filepath:
            # Check if it's a .bat file
            if not filepath.lower().endswith('.bat'):
                messagebox.showwarning("Invalid File Type", "Please select a .bat file for Visual Studio path.")
                return
            self.vs_path_var.set(filepath)
            self.mark_vs_path_dirty()
    
    def browse_winrar_path(self):
        filepath = filedialog.askopenfilename(
            title="Select WinRAR Executable",
            filetypes=(("Executable files", "*.exe"), ("All files", "*.*"))
        )
        if filepath:
            # Check if it's an .exe file
            if not filepath.lower().endswith('.exe'):
                messagebox.showwarning("Invalid File Type", "Please select an .exe file for WinRAR path.")
                return
            self.winrar_path_var.set(filepath)
            self.mark_winrar_path_dirty()
    
    def mark_vs_path_dirty(self):
        """Updates UI to show VS path needs applying."""
        if self.vs_path_dirty: return  # Already marked
        self.vs_path_dirty = True
        self.vs_path_status_label.configure(text="Status: Path changed (unapplied)", text_color=COLORS["warning"])
        self.apply_vs_path_button.configure(border_color=COLORS["warning"], border_width=2)
        # Disable run grading button when VS path is dirty
        self.run_button.configure(state="disabled")
        log("Visual Studio path changed, please Apply.", "info")
        self.update_dependent_button_states()
    
    def mark_winrar_path_dirty(self):
        """Updates UI to show WinRAR path needs applying."""
        if self.winrar_path_dirty: return  # Already marked
        self.winrar_path_dirty = True
        self.winrar_path_status_label.configure(text="Status: Path changed (unapplied)", text_color=COLORS["warning"])
        self.apply_winrar_path_button.configure(border_color=COLORS["warning"], border_width=2)
        
        # Disable preprocess button when WinRAR path is dirty AND RAR support is enabled
        if self.rar_support_var.get():
            self.preprocess_button.configure(state="disabled")
            log("RAR support enabled but WinRAR path is not applied. Please Apply the WinRAR path.", "info")
        else:
            log("RAR support disabled, preprocessor will not use WinRAR path.", "info")
        
        self.update_dependent_button_states()
    
    def apply_vs_path(self):
        """Validates and applies the VS path."""
        vs_path = self.vs_path_var.get().strip()
        if not vs_path:
            messagebox.showerror("Error", "Visual Studio path cannot be empty.")
            self.vs_path_status_label.configure(text="Status: Invalid (empty path)", text_color=COLORS["danger"])
            return
        
        # Check if path has the correct extension
        if not vs_path.lower().endswith('.bat'):
            messagebox.showerror("Error", "Visual Studio path must be a .bat file.")
            self.vs_path_status_label.configure(text="Status: Invalid (not a .bat file)", text_color=COLORS["danger"])
            return
        
        # Check if file exists
        if not os.path.exists(vs_path):
            messagebox.showerror("Error", f"Visual Studio path does not exist: {vs_path}")
            self.vs_path_status_label.configure(text="Status: Invalid (file not found)", text_color=COLORS["danger"])
            return
        
        # Update status to show we're validating
        self.vs_path_status_label.configure(text="Status: Validating...", text_color=COLORS["warning"])
        self.apply_vs_path_button.configure(state="disabled")
        
        # Run validation in a background thread
        threading.Thread(target=self._validate_vs_path_thread, args=(vs_path,), daemon=True).start()

    def _validate_vs_path_thread(self, vs_path):
        """Background thread for VS path validation"""
        try:
            # Basic test - just check if the file can be executed
            test_cmd = f'cmd /c ""{vs_path}" && echo Success"'
            result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
            
            # Schedule UI updates on the main thread
            if result.returncode != 0:
                self.after(0, lambda: self._handle_vs_validation_failure(vs_path, f"Failed to execute batch file:\n{result.stderr}"))
                return
            
            # Check if "cl.exe" is in the path after running vcvars64.bat
            test_cmd = f'cmd /c ""{vs_path}" && where cl.exe"'
            result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode != 0:
                self.after(0, lambda: self._handle_vs_validation_warning(vs_path, "Visual Studio environment doesn't include cl.exe compiler.\nMake sure Visual C++ build tools are installed."))
            else:
                self.after(0, lambda: self._handle_vs_validation_success(vs_path))
                
        except Exception as e:
            self.after(0, lambda: self._handle_vs_validation_failure(vs_path, f"Validation error: {str(e)}"))

    def _handle_vs_validation_success(self, vs_path):
        """Handle successful VS path validation (runs on main thread)"""
        self.gui_vs_path = vs_path
        self.vs_path_dirty = False
        self.vs_path_status_label.configure(text="Status: Valid ✓", text_color=COLORS["secondary"])
        self.apply_vs_path_button.configure(border_color=self._default_border_color, border_width=1, state="normal")
        log(f"Visual Studio path applied and validated: {vs_path}", "success")
        self.update_dependent_button_states()

    def _handle_vs_validation_warning(self, vs_path, message):
        """Handle VS path validation with warnings (runs on main thread)"""
        messagebox.showwarning("Warning", message)
        self.gui_vs_path = vs_path
        self.vs_path_dirty = False
        self.vs_path_status_label.configure(text="Status: Applied with warnings", text_color=COLORS["warning"])
        self.apply_vs_path_button.configure(border_color=self._default_border_color, border_width=1, state="normal")
        log(f"Visual Studio path applied with warnings: {vs_path}", "warning")
        self.update_dependent_button_states()

    def _handle_vs_validation_failure(self, vs_path, error_message):
        """Handle VS path validation failure (runs on main thread)"""
        messagebox.showerror("Error", error_message)
        self.vs_path_status_label.configure(text="Status: Validation failed", text_color=COLORS["danger"])
        self.apply_vs_path_button.configure(state="normal")

    def apply_winrar_path(self):
        """Validates and applies the WinRAR path."""
        winrar_path = self.winrar_path_var.get().strip()
        if not winrar_path:
            messagebox.showerror("Error", "WinRAR path cannot be empty.")
            self.winrar_path_status_label.configure(text="Status: Invalid (empty path)", text_color=COLORS["danger"])
            return
        
        # Check if path has the correct extension
        if not winrar_path.lower().endswith('.exe'):
            messagebox.showerror("Error", "WinRAR path must be an .exe file.")
            self.winrar_path_status_label.configure(text="Status: Invalid (not an .exe file)", text_color=COLORS["danger"])
            return
        
        # Check if file exists
        if not os.path.exists(winrar_path):
            messagebox.showerror("Error", f"WinRAR path does not exist: {winrar_path}")
            self.winrar_path_status_label.configure(text="Status: Invalid (file not found)", text_color=COLORS["danger"])
            return
        
        # Check if it contains 'rar' in the path to ensure it's likely a WinRAR executable
        if 'rar' not in winrar_path.lower():
            if not messagebox.askyesno("Warning", f"Path doesn't appear to be a RAR executable: {winrar_path}\n\nContinue anyway?"):
                self.winrar_path_status_label.configure(text="Status: Warning (not RAR-related)", text_color=COLORS["warning"])
                return
        
        # Basic test - just check if the file can be executed
        try:
            # For UnRAR.exe, try to get version info
            if 'unrar.exe' in winrar_path.lower():
                test_cmd = f'"{winrar_path}" -v'
            # For WinRAR.exe, try with /? parameter
            else:
                test_cmd = f'"{winrar_path}" /?'
                
            result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
            if result.returncode != 0 and 'unrar.exe' in winrar_path.lower():
                messagebox.showerror("Error", f"Failed to execute UnRAR executable:\n{result.stderr}")
                self.winrar_path_status_label.configure(text="Status: Invalid (execution failed)", text_color=COLORS["danger"])
                return
                
            # Success!
            self.gui_winrar_path = winrar_path
            self.winrar_path_dirty = False
            self.winrar_path_status_label.configure(text="Status: Valid ✓", text_color=COLORS["secondary"])
            self.apply_winrar_path_button.configure(border_color=self._default_border_color, border_width=1)
            log(f"WinRAR path applied and validated: {winrar_path}", "success")
            self.update_dependent_button_states()
            
        except Exception as e:
            messagebox.showwarning("Warning", f"Cannot verify WinRAR executable:\n{str(e)}\n\nPath will be applied but might not work correctly.")
            self.winrar_path_status_label.configure(text="Status: Applied with warnings", text_color=COLORS["warning"])
            self.gui_winrar_path = winrar_path
            self.winrar_path_dirty = False
            self.apply_winrar_path_button.configure(border_color=self._default_border_color, border_width=1)
            log(f"WinRAR path applied with warnings: {winrar_path}", "warning")
            self.update_dependent_button_states()

    def update_rar_dependency_state(self):
        """Updates button states when RAR support is toggled"""
        # Update preprocess button state
        self.check_preprocess_button_state()
        
        # Log appropriate message
        if self.rar_support_var.get() and self.winrar_path_dirty:
            log("RAR support enabled but WinRAR path is not validated. Please Apply the WinRAR path.", "info")
        elif not self.rar_support_var.get() and self.winrar_path_dirty:
            log("RAR support disabled, preprocessor will not use WinRAR path.", "info")

    def validate_initial_paths(self):
        """Validate VS and WinRAR paths when the GUI first opens."""
        log("Performing initial dependency validation...", "info")
        
        # Validate VS path
        vs_path = self.vs_path_var.get().strip()
        if vs_path and os.path.exists(vs_path) and vs_path.lower().endswith('.bat'):
            # Start validation in background thread
            self.vs_path_status_label.configure(text="Status: Validating...", text_color=COLORS["warning"])
            self.vs_path_dirty = True  # Mark as dirty until validation completes
            self.run_button.configure(state="disabled")  # Disable Run Grading until validation is successful
            threading.Thread(target=self._validate_initial_vs_path, args=(vs_path,), daemon=True).start()
        else:
            # VS path is invalid, disable Run Grading button
            self.vs_path_dirty = True
            self.vs_path_status_label.configure(text="Status: Not validated", text_color=COLORS["warning"])
            self.run_button.configure(state="disabled")
            log("Initial VS path validation failed. Please validate VS path before running grading.", "warning")
        
        # Validate WinRAR path regardless of RAR support setting
        winrar_path = self.winrar_path_var.get().strip()
        if winrar_path and os.path.exists(winrar_path) and winrar_path.lower().endswith('.exe'):
            # Start validation in background thread
            self.winrar_path_status_label.configure(text="Status: Validating...", text_color=COLORS["warning"])
            self.winrar_path_dirty = True  # Mark as dirty until validation completes
            threading.Thread(target=self._validate_initial_winrar_path, args=(winrar_path,), daemon=True).start()
        else:
            # WinRAR path is invalid
            self.winrar_path_dirty = True
            self.winrar_path_status_label.configure(text="Status: Not validated", text_color=COLORS["warning"])
            log("Initial WinRAR path validation failed.", "warning")
            
            # Only disable Preprocess button if RAR support is enabled
            if self.rar_support_var.get():
                self.preprocess_button.configure(state="disabled")
                log("RAR support is enabled but WinRAR path is invalid. Preprocess button disabled.", "warning")
        
        # Update button states
        self.update_dependent_button_states()

    def _validate_initial_vs_path(self, vs_path):
        """Background thread for initial VS path validation"""
        try:
            # Basic test - just check if the file can be executed
            test_cmd = f'cmd /c ""{vs_path}" && echo Success"'
            result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode != 0:
                self.after(0, lambda: self._handle_initial_vs_validation_failure())
                return
            
            # Check if "cl.exe" is in the path after running vcvars64.bat
            test_cmd = f'cmd /c ""{vs_path}" && where cl.exe"'
            result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode != 0:
                self.after(0, lambda: self._handle_initial_vs_validation_warning())
            else:
                self.after(0, lambda: self._handle_initial_vs_validation_success())
                
        except Exception as e:
            self.after(0, lambda: self._handle_initial_vs_validation_failure())

    def _handle_initial_vs_validation_success(self):
        """Handle successful initial VS path validation (runs on main thread)"""
        self.gui_vs_path = self.vs_path_var.get().strip()
        self.vs_path_dirty = False
        self.vs_path_status_label.configure(text="Status: Valid ✓", text_color=COLORS["secondary"])
        log("Visual Studio path initially validated successfully.", "success")
        self.update_dependent_button_states()

    def _handle_initial_vs_validation_warning(self):
        """Handle initial VS path validation with warnings (runs on main thread)"""
        self.gui_vs_path = self.vs_path_var.get().strip()
        self.vs_path_dirty = False
        self.vs_path_status_label.configure(text="Status: Valid with warnings", text_color=COLORS["warning"])
        log("Visual Studio path initially validated with warnings. cl.exe not found.", "warning")
        self.update_dependent_button_states()

    def _handle_initial_vs_validation_failure(self):
        """Handle initial VS path validation failure (runs on main thread)"""
        self.vs_path_dirty = True
        self.vs_path_status_label.configure(text="Status: Invalid", text_color=COLORS["danger"])
        log("Initial Visual Studio path validation failed. Run Grading will be disabled.", "error")
        self.run_button.configure(state="disabled")

    def _validate_initial_winrar_path(self, winrar_path):
        """Background thread for initial WinRAR path validation"""
        try:
            # For UnRAR.exe, try to get version info
            if 'unrar.exe' in winrar_path.lower():
                test_cmd = f'"{winrar_path}" -v'
            # For WinRAR.exe, try with /? parameter
            else:
                test_cmd = f'"{winrar_path}" /?'
                
            result = subprocess.run(test_cmd, capture_output=True, text=True, shell=True)
            if result.returncode != 0 and 'unrar.exe' in winrar_path.lower():
                self.after(0, lambda: self._handle_initial_winrar_validation_failure())
                return
            
            # Success
            self.after(0, lambda: self._handle_initial_winrar_validation_success())
        except Exception as e:
            self.after(0, lambda: self._handle_initial_winrar_validation_failure())

    def _handle_initial_winrar_validation_success(self):
        """Handle successful initial WinRAR path validation (runs on main thread)"""
        self.gui_winrar_path = self.winrar_path_var.get().strip()
        self.winrar_path_dirty = False
        self.winrar_path_status_label.configure(text="Status: Valid ✓", text_color=COLORS["secondary"])
        log("WinRAR path initially validated successfully.", "success")
        self.update_dependent_button_states()

    def _handle_initial_winrar_validation_failure(self):
        """Handle initial WinRAR path validation failure (runs on main thread)"""
        self.winrar_path_dirty = True
        self.winrar_path_status_label.configure(text="Status: Invalid", text_color=COLORS["danger"])
        log("Initial WinRAR path validation failed. RAR support will be disabled.", "error")
        if self.rar_support_var.get():
            self.preprocess_button.configure(state="disabled")

    def update_simple_naming_state(self):
        """Updates the simple naming state and logs the change."""
        new_state = self.simple_naming_var.get()
        if new_state != self.gui_simple_naming:
            self.gui_simple_naming = new_state
            configuration.use_simple_naming = new_state
            log(f"Simple naming mode {'enabled' if new_state else 'disabled'}. Files will be treated as {'hw[0-9].c' if new_state else 'hw[0-9]_q[0-9].c'}.", "info")


class CheckerManagerWindow(ctk.CTkToplevel):
    def __init__(self, parent: App):
        super().__init__(parent)
        self.parent = parent
        self.title("Checker Manager")
        self.geometry("1100x780")
        self.minsize(950, 650)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.checker_config = load_checker_config(DEFAULT_CHECKER_CONFIG_PATH)
        self.assignment_path_var = tk.StringVar(value="")
        self.provider_var = tk.StringVar(value="Gemini")
        self.gemini_model_var = tk.StringVar(value=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))
        self.gemini_model_values = [self.gemini_model_var.get(), "gemini-2.0-flash", "gemini-1.5-flash"]
        self.audit_size_var = tk.StringVar(value="15")
        self.question_var = tk.StringVar(value=parent.gui_questions[0] if parent.gui_questions else "Q1")

        top = ctk.CTkFrame(self, corner_radius=8)
        top.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Question:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.question_menu = ctk.CTkOptionMenu(
            top,
            values=parent.gui_questions or ["Q1"],
            variable=self.question_var,
            command=lambda _value: self.load_question_config(),
        )
        self.question_menu.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(top, text="LLM Provider:").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self.provider_menu = ctk.CTkOptionMenu(
            top,
            values=["Fake/Offline", "Gemini"],
            variable=self.provider_var,
            command=lambda _value: self.update_gemini_key_status(),
        )
        self.provider_menu.grid(row=0, column=3, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(top, text="Gemini model:").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        self.gemini_model_menu = ctk.CTkOptionMenu(top, values=self.gemini_model_values, variable=self.gemini_model_var)
        self.gemini_model_menu.grid(row=1, column=1, columnspan=2, padx=8, pady=8, sticky="ew")
        self.refresh_models_button = ctk.CTkButton(top, text="Refresh Models", command=self.refresh_gemini_models)
        self.refresh_models_button.grid(row=1, column=3, padx=8, pady=8)

        ctk.CTkLabel(top, text="Optional assignment file:").grid(row=2, column=0, padx=8, pady=8, sticky="w")
        self.assignment_entry = ctk.CTkEntry(top, textvariable=self.assignment_path_var)
        self.assignment_entry.grid(row=2, column=1, columnspan=2, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(top, text="Browse", command=self.browse_assignment_file).grid(row=2, column=3, padx=8, pady=8)

        ctk.CTkLabel(top, text="Audit sample size:").grid(row=3, column=0, padx=8, pady=8, sticky="w")
        self.audit_size_entry = ctk.CTkEntry(top, textvariable=self.audit_size_var, width=80)
        self.audit_size_entry.grid(row=3, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(top, text="Tip: use 3-5 for a cheap smoke audit, 10-15 for a stronger review.", text_color="gray").grid(row=3, column=2, columnspan=2, padx=8, pady=8, sticky="w")

        self.gemini_key_status_label = ctk.CTkLabel(top, text="", anchor="w", justify="left")
        self.gemini_key_status_label.grid(row=4, column=0, columnspan=3, padx=8, pady=(0, 8), sticky="ew")
        self.copy_gemini_setup_button = ctk.CTkButton(
            top,
            text="Copy Setup Command",
            command=self.copy_gemini_setup_command,
            width=160,
        )
        self.copy_gemini_setup_button.grid(row=4, column=3, padx=8, pady=(0, 8), sticky="e")

        buttons = ctk.CTkFrame(self, corner_radius=8)
        buttons.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        for idx in range(5):
            buttons.grid_columnconfigure(idx, weight=1)
        self.suggest_checker_button = ctk.CTkButton(buttons, text="1. Suggest with LLM", command=self.suggest_with_llm)
        self.suggest_checker_button.grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        self.test_checker_button = ctk.CTkButton(buttons, text="2. Test Draft", command=self.test_checker)
        self.test_checker_button.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        self.save_checker_button = ctk.CTkButton(buttons, text="3. Save Checker", command=self.save_current_checker)
        self.save_checker_button.grid(row=0, column=2, padx=8, pady=8, sticky="ew")
        self.run_audit_button = ctk.CTkButton(buttons, text="4. Run Audit", command=self.run_audit)
        self.run_audit_button.grid(row=0, column=3, padx=8, pady=8, sticky="ew")
        self.reload_checker_button = ctk.CTkButton(buttons, text="Reload", command=self.load_question_config)
        self.reload_checker_button.grid(row=0, column=4, padx=8, pady=8, sticky="ew")
        ctk.CTkLabel(
            buttons,
            text=(
                "Recommended flow: Suggest, review/edit JSON, Test Draft, Save Checker, run grading, then Run Audit. "
                "The assignment file is optional LLM context, not an audit folder."
            ),
            text_color="gray",
            anchor="w",
            justify="left",
            wraplength=950,
        ).grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 8), sticky="ew")

        activity_frame = ctk.CTkFrame(self, corner_radius=8)
        activity_frame.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="ew")
        activity_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(activity_frame, text="LLM activity:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.llm_activity_label = ctk.CTkLabel(activity_frame, text="Idle", anchor="w")
        self.llm_activity_label.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        self.llm_activity_progress = ctk.CTkProgressBar(activity_frame, mode="indeterminate", height=8)
        self.llm_activity_progress.grid(row=1, column=0, columnspan=2, padx=8, pady=(0, 8), sticky="ew")
        self.llm_activity_progress.set(0)
        self.llm_activity_running = False
        self.llm_activity_started_at = None
        self.llm_activity_step = "Idle"

        self.tabview = ctk.CTkTabview(self, corner_radius=8)
        self.tabview.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="nsew")
        for tab_name in ["Configure", "Test Results", "Audit", "Prompt / Response"]:
            self.tabview.add(tab_name)

        configure_tab = self.tabview.tab("Configure")
        configure_tab.grid_columnconfigure((0, 1), weight=1)
        configure_tab.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(
            configure_tab,
            text="Quick path: choose a question, suggest a checker, review/edit the JSON, test it, then save it.",
            text_color="gray",
        ).grid(row=0, column=0, columnspan=2, padx=8, pady=(8, 0), sticky="w")
        ctk.CTkLabel(configure_tab, text="Checker Config JSON", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(configure_tab, text="Available Checker Templates", font=ctk.CTkFont(weight="bold")).grid(row=1, column=1, padx=8, pady=8, sticky="w")
        self.config_textbox = ctk.CTkTextbox(configure_tab, wrap="word")
        self.config_textbox.grid(row=2, column=0, padx=8, pady=8, sticky="nsew")
        self.templates_textbox = ctk.CTkTextbox(configure_tab, wrap="word")
        self.templates_textbox.grid(row=2, column=1, padx=8, pady=8, sticky="nsew")

        test_tab = self.tabview.tab("Test Results")
        test_tab.grid_columnconfigure(0, weight=1)
        test_tab.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            test_tab,
            text="Tests the draft JSON currently shown in Configure. Save only after these rows look right.",
            text_color="gray",
        ).grid(row=0, column=0, padx=8, pady=(8, 0), sticky="w")
        self.test_table_frame = ctk.CTkScrollableFrame(test_tab, corner_radius=6)
        self.test_table_frame.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        self.test_table_frame.grid_columnconfigure(4, weight=1)
        self.test_row_index = 0

        audit_tab = self.tabview.tab("Audit")
        audit_tab.grid_columnconfigure(0, weight=1)
        audit_tab.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(
            audit_tab,
            text="After grading, samples generated grade/Excel rows and asks the LLM to review them. No folder selection is required.",
            text_color="gray",
        ).grid(row=0, column=0, padx=8, pady=(8, 0), sticky="w")
        self.audit_progress_label = ctk.CTkLabel(audit_tab, text="Audit not run yet", anchor="w")
        self.audit_progress_label.grid(row=1, column=0, padx=8, pady=8, sticky="ew")
        audit_actions = ctk.CTkFrame(audit_tab, fg_color="transparent")
        audit_actions.grid(row=1, column=0, padx=8, pady=8, sticky="e")
        self.audit_open_excel_button = ctk.CTkButton(
            audit_actions,
            text="Open Final Excel",
            width=140,
            command=self.parent.open_final_excel,
            state="normal" if os.path.exists("final_grades.xlsx") else "disabled",
        )
        self.audit_open_excel_button.pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkButton(
            audit_actions,
            text="Open Folder",
            width=120,
            command=self.parent.open_output_folder,
        ).pack(side=tk.LEFT)
        self.audit_table_frame = ctk.CTkScrollableFrame(audit_tab, corner_radius=6)
        self.audit_table_frame.grid(row=2, column=0, padx=8, pady=8, sticky="nsew")
        self.audit_table_frame.grid_columnconfigure(4, weight=1)
        self.audit_row_index = 0

        raw_tab = self.tabview.tab("Prompt / Response")
        raw_tab.grid_columnconfigure((0, 1), weight=1)
        raw_tab.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(raw_tab, text="Last Prompt Sent", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(raw_tab, text="Last Raw Response / Payload", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, padx=8, pady=8, sticky="w")
        self.prompt_textbox = ctk.CTkTextbox(raw_tab, wrap="word")
        self.prompt_textbox.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        self.response_textbox = ctk.CTkTextbox(raw_tab, wrap="word")
        self.response_textbox.grid(row=1, column=1, padx=8, pady=8, sticky="nsew")

        self.status_label = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.status_label.grid(row=4, column=0, padx=12, pady=(0, 12), sticky="ew")

        self.load_question_config()
        self.show_available_checkers()
        self.update_gemini_key_status()

    def show_on_top(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

    def close_window(self):
        self.parent.checker_manager_window = None
        self.destroy()

    @staticmethod
    def gemini_setup_command():
        return "[Environment]::SetEnvironmentVariable('GOOGLE_API_KEY', 'your_api_key_here', 'User')"

    @staticmethod
    def has_gemini_api_key():
        return bool(get_google_api_key())

    def update_gemini_key_status(self):
        has_key = self.has_gemini_api_key()
        using_gemini = self.provider_var.get() == "Gemini"
        if has_key:
            self.gemini_key_status_label.configure(
                text="Gemini key detected. Click Refresh Models to load the models available for this key.",
                text_color=COLORS["secondary"],
            )
            self.copy_gemini_setup_button.configure(state="disabled")
            self.refresh_models_button.configure(state="normal")
            self.gemini_model_menu.configure(state="normal")
        else:
            self.gemini_key_status_label.configure(
                text=(
                    "Gemini key is not configured. In PowerShell run: "
                    f"{self.gemini_setup_command()} then restart the GUI."
                ),
                text_color=COLORS["warning"],
            )
            self.copy_gemini_setup_button.configure(state="normal")
            self.refresh_models_button.configure(state="normal")
            self.gemini_model_menu.configure(state="normal")

        llm_action_state = "disabled" if using_gemini and not has_key else "normal"
        self.suggest_checker_button.configure(state=llm_action_state)
        self.run_audit_button.configure(state=llm_action_state)

    def copy_gemini_setup_command(self):
        self.clipboard_clear()
        self.clipboard_append(self.gemini_setup_command())
        self.set_status("Copied GOOGLE_API_KEY setup command. Replace your_api_key_here, run it in PowerShell, then restart the GUI.")

    def browse_assignment_file(self):
        path = filedialog.askopenfilename(
            title="Select Assignment Description",
            filetypes=(
                ("Assignment files", "*.pdf *.docx *.txt *.md"),
                ("All files", "*.*"),
            ),
        )
        if path:
            self.assignment_path_var.set(path)

    def refresh_gemini_models(self):
        if not self.has_gemini_api_key():
            self.show_gemini_key_missing()
            return
        self.set_status("Loading Gemini models from GOOGLE_API_KEY...")
        threading.Thread(target=self._refresh_gemini_models_worker, daemon=True).start()

    def _refresh_gemini_models_worker(self):
        try:
            models = list_gemini_models()
            if not models:
                raise RuntimeError("No generateContent-capable Gemini models returned for this key.")
            self.after(0, lambda: self.apply_gemini_models(models))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Gemini Model Load Failed", captured_exc))

    def apply_gemini_models(self, models):
        current = self.gemini_model_var.get()
        self.gemini_model_values = models
        self.gemini_model_menu.configure(values=models)
        if current in models:
            self.gemini_model_var.set(current)
        elif DEFAULT_GEMINI_MODEL in models:
            self.gemini_model_var.set(DEFAULT_GEMINI_MODEL)
        else:
            flash_models = [model for model in models if "flash" in model.lower()]
            self.gemini_model_var.set(flash_models[0] if flash_models else models[0])
        self.set_status(f"Loaded {len(models)} Gemini models")

    def load_question_config(self):
        question = self.question_var.get()
        question_config = self.checker_config.get("questions", {}).get(question, {"checker": "exact", "config": {}})
        self.config_textbox.delete("1.0", tk.END)
        self.config_textbox.insert("1.0", json.dumps(question_config, indent=2, sort_keys=True))
        self.set_status(f"Loaded checker config for {question}")

    def save_current_checker(self):
        try:
            question_config = json.loads(self.config_textbox.get("1.0", tk.END).strip())
        except json.JSONDecodeError as exc:
            messagebox.showerror("Invalid JSON", str(exc))
            return
        checker_name = question_config.get("checker")
        if checker_name not in available_checker_templates():
            messagebox.showerror("Unknown Checker", f"Checker '{checker_name}' is not available.")
            return
        question = self.question_var.get()
        self.checker_config.setdefault("questions", {})[question] = question_config
        save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)
        self.set_status(f"Saved checker for {question}")
        messagebox.showinfo("Checker Saved", f"Saved checker config for {question}.")

    def suggest_with_llm(self):
        self.run_background("Suggesting checker...", self._suggest_with_llm_worker, "Preparing LLM suggestion")

    def test_checker(self):
        self.run_background("Testing checker...", self._test_checker_worker)

    def run_audit(self):
        self.run_background("Running sampled LLM audit...", self._run_audit_worker, "Preparing LLM audit")

    def run_background(self, status, worker, activity_message=None):
        self.set_status(status)
        if activity_message:
            self.start_llm_activity(activity_message)

        def runner():
            try:
                worker()
            finally:
                if activity_message:
                    self.after(0, self.stop_llm_activity)

        threading.Thread(target=runner, daemon=True).start()

    def start_llm_activity(self, message):
        self.llm_activity_running = True
        self.llm_activity_started_at = time.monotonic()
        self.llm_activity_step = message
        self.llm_activity_progress.start()
        self.update_llm_activity_label()

    def set_llm_activity_step(self, message):
        self.llm_activity_step = message
        self.update_llm_activity_label()

    def update_llm_activity_label(self):
        if not self.llm_activity_running:
            return
        elapsed = int(time.monotonic() - self.llm_activity_started_at)
        self.llm_activity_label.configure(text=f"{self.llm_activity_step}... {elapsed}s elapsed")
        self.after(500, self.update_llm_activity_label)

    def stop_llm_activity(self):
        if not self.llm_activity_running:
            return
        elapsed = int(time.monotonic() - self.llm_activity_started_at)
        self.llm_activity_running = False
        self.llm_activity_progress.stop()
        self.llm_activity_progress.set(0)
        self.llm_activity_label.configure(text=f"Done in {elapsed}s")

    def _suggest_with_llm_worker(self):
        try:
            question = self.question_var.get()
            self.after(0, lambda: self.set_llm_activity_step("Compiling reference solution and collecting examples"))
            original_code, inputs, expected_outputs = self.collect_question_context(question)
            self.after(0, lambda: self.set_llm_activity_step("Parsing assignment PDF/DOCX text and images"))
            assignment_context = parse_assignment_context(self.assignment_path_var.get().strip() or None)
            focused_context = assignment_context_for_question(assignment_context, question)
            image_count = len(focused_context.images)
            self.after(0, lambda: self.set_llm_activity_step(f"Building prompt with {image_count} assignment image(s)"))
            prompt = build_suggestion_prompt(
                question,
                original_code,
                inputs,
                expected_outputs,
                focused_context.text,
                focused_context.images,
            )
            self.after(0, lambda: self.show_prompt(prompt))
            provider = self.make_provider()
            self.after(0, lambda: self.set_llm_activity_step("Waiting for Gemini checker suggestion"))
            suggestion = suggest_checker(
                question,
                original_code,
                inputs,
                expected_outputs,
                provider,
                focused_context.text,
                focused_context.images,
            )
            self.after(0, lambda: self.apply_suggestion(suggestion))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Checker Suggestion Failed", captured_exc))

    def _test_checker_worker(self):
        try:
            question_config = json.loads(self.config_textbox.get("1.0", tk.END).strip())
            question = self.question_var.get()
            _, _inputs, expected_outputs = self.collect_question_context(question)
            rows = run_checker_tests(question_config, expected_outputs)
            self.after(0, lambda: self.show_test_rows(rows))
            self.after(0, lambda: self.set_status(f"Checker test finished: {len(rows)} rows"))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Checker Test Failed", captured_exc))

    def _run_audit_worker(self):
        try:
            provider = self.make_provider()
            self.after(0, lambda: self.set_llm_activity_step("Parsing assignment context for audit"))
            assignment_context = parse_assignment_context(self.assignment_path_var.get().strip() or None)
            self.after(0, lambda: self.set_llm_activity_step("Selecting representative graded students"))
            cases = select_audit_cases(self.parent.gui_questions, max_cases=self.get_audit_size())
            checker_configs = self.checker_config.get("questions", {})
            if cases:
                focused_context = assignment_context_for_question(assignment_context, cases[0].question)
                sample_prompt = build_audit_prompt(
                    cases[0],
                    checker_configs.get(cases[0].question, {}),
                    focused_context.text,
                    focused_context.images,
                )
                self.after(0, lambda: self.show_prompt(sample_prompt))
                self.after(0, lambda: self.start_audit_display(cases))
            self.after(0, lambda: self.set_llm_activity_step(f"Waiting for Gemini audit reviews ({len(cases)} call(s))"))
            results = audit_cases_with_llm(
                cases,
                checker_configs,
                provider,
                assignment_context,
                max_workers=4,
                progress_callback=lambda result, done, total: self.after(0, lambda: self.add_audit_result(result, done, total)),
            )
            overall = self.audit_overall_status(results)
            payload = {
                "overall": overall,
                "reviewed": len(results),
                "results": [result.__dict__ for result in results],
            }
            self.after(0, lambda: self.show_json_result(payload))
            self.after(0, lambda: self.set_status(f"Audit finished: {overall}"))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Audit Failed", captured_exc))

    def collect_question_context(self, question):
        original_path = os.path.join(question, "original_sol.c")
        with open(original_path, "r", encoding="utf-8", errors="ignore") as original_file:
            original_code = original_file.read()
        inputs = read_inputs_from_file(question)[:8]
        setup_visual_studio_environment()
        expected_outputs = get_ground_truth(question, inputs)
        return original_code, inputs, expected_outputs

    def make_provider(self):
        if self.provider_var.get() == "Gemini":
            if not self.has_gemini_api_key():
                raise ValueError(self.gemini_key_missing_message())
            return GeminiProvider(model=self.gemini_model_var.get().strip() or None)
        return FakeLLMProvider()

    def gemini_key_missing_message(self):
        return (
            "GOOGLE_API_KEY is not set.\n\n"
            "In PowerShell, run:\n"
            f"{self.gemini_setup_command()}\n\n"
            "Replace your_api_key_here with the real key, then restart the GUI so Python can read it."
        )

    def show_gemini_key_missing(self):
        self.update_gemini_key_status()
        messagebox.showinfo("Gemini Key Not Configured", self.gemini_key_missing_message())
        self.set_status("Gemini key missing. Setup command is shown in the Checker Manager.")

    def get_audit_size(self):
        try:
            return max(1, min(50, int(self.audit_size_var.get().strip())))
        except ValueError:
            return 15

    def apply_suggestion(self, suggestion):
        if suggestion.status != "supported" or not suggestion.checker:
            self.show_json_result(suggestion.__dict__)
            self.set_status("LLM did not find a supported checker")
            return
        question_config = {"checker": suggestion.checker, "config": suggestion.config}
        self.config_textbox.delete("1.0", tk.END)
        self.config_textbox.insert("1.0", json.dumps(question_config, indent=2, sort_keys=True))
        self.show_json_result(suggestion.__dict__)
        self.set_status(f"Suggested {suggestion.checker}; click Save Checker to apply")
        self.tabview.set("Configure")

    def show_available_checkers(self):
        self.templates_textbox.delete("1.0", tk.END)
        self.templates_textbox.insert("1.0", json.dumps(available_checker_templates(), indent=2, ensure_ascii=False))

    def show_json_result(self, payload):
        self.response_textbox.delete("1.0", tk.END)
        self.response_textbox.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False, default=str))

    def show_prompt(self, prompt):
        self.prompt_textbox.delete("1.0", tk.END)
        self.prompt_textbox.insert("1.0", prompt)

    def show_test_rows(self, rows):
        self.clear_test_table()
        self.add_test_header()
        for row in rows:
            self.add_test_row(row)
        self.show_json_result({"test_rows": rows})
        self.tabview.set("Test Results")

    def clear_test_table(self):
        for child in self.test_table_frame.winfo_children():
            child.destroy()
        self.test_row_index = 0

    def add_test_header(self):
        headers = ["Variant", "Input", "Status", "Reason", "Expected -> Actual"]
        for column, header in enumerate(headers):
            label = ctk.CTkLabel(
                self.test_table_frame,
                text=header,
                font=ctk.CTkFont(weight="bold"),
                anchor="w",
            )
            label.grid(row=0, column=column, padx=6, pady=(4, 6), sticky="ew")
        self.test_row_index = 1

    def add_test_row(self, row):
        passed = bool(row.get("passed"))
        status_text = "PASS" if passed else "FAIL"
        status_color = COLORS["secondary"] if passed else COLORS["danger"]
        parsed_values = f"{row.get('expected_canonical')} -> {row.get('actual_canonical')}"
        row_values = [
            row.get("variant", ""),
            row.get("input", ""),
            status_text,
            row.get("reason", ""),
            parsed_values,
        ]
        for column, value in enumerate(row_values):
            label = ctk.CTkLabel(
                self.test_table_frame,
                text=str(value),
                text_color=status_color if column == 2 else None,
                anchor="w",
                justify="left",
                wraplength=460 if column in (3, 4) else 130,
            )
            label.grid(row=self.test_row_index, column=column, padx=6, pady=3, sticky="ew")
        self.test_row_index += 1

    def start_audit_display(self, cases):
        self.clear_audit_table()
        self.add_audit_header()
        self.audit_open_excel_button.configure(state="normal" if os.path.exists("final_grades.xlsx") else "disabled")
        self.audit_progress_label.configure(text=f"Queued {len(cases)} audit cases...")
        self.tabview.set("Audit")

    def add_audit_result(self, result, done, total):
        self.audit_progress_label.configure(text=f"Reviewed {done}/{total} audit cases")
        self.add_audit_row(result)

    def clear_audit_table(self):
        for child in self.audit_table_frame.winfo_children():
            child.destroy()
        self.audit_row_index = 0

    def add_audit_header(self):
        headers = ["Student", "Question", "Status", "Risk", "Reason"]
        for column, header in enumerate(headers):
            label = ctk.CTkLabel(
                self.audit_table_frame,
                text=header,
                font=ctk.CTkFont(weight="bold"),
                anchor="w",
            )
            label.grid(row=0, column=column, padx=6, pady=(4, 6), sticky="ew")
        self.audit_row_index = 1

    def add_audit_row(self, result):
        status_color = {
            "passed": COLORS["secondary"],
            "flagged": COLORS["danger"],
            "error": COLORS["danger"],
        }.get(result.status, COLORS["warning"])
        row_values = [
            result.student_id,
            result.question,
            result.status.upper(),
            result.risk,
            result.reason,
        ]
        for column, value in enumerate(row_values):
            label = ctk.CTkLabel(
                self.audit_table_frame,
                text=str(value),
                text_color=status_color if column == 2 else None,
                anchor="w",
                justify="left",
                wraplength=520 if column == 4 else 140,
            )
            label.grid(row=self.audit_row_index, column=column, padx=6, pady=3, sticky="ew")
        self.audit_row_index += 1

    def show_error(self, title, exc):
        self.set_status(f"{title}: {exc}")
        messagebox.showerror(title, str(exc))

    def set_status(self, message):
        self.status_label.configure(text=message)

    @staticmethod
    def audit_overall_status(results):
        if not results:
            return "yellow: no audit cases found"
        if any(result.status == "flagged" for result in results):
            return "red: one or more reviews flagged"
        if any(result.status == "error" for result in results):
            return "yellow: one or more reviews errored"
        return "green: all sampled reviews passed"


if __name__ == "__main__":
    app = App()
    app.mainloop() 