import importlib.util
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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

UI_FONT_FAMILY = "Segoe UI"
REVIEW_TREE_STYLE = "Review.Treeview"
REVIEW_TREE_HEADING_STYLE = f"{REVIEW_TREE_STYLE}.Heading"


def missing_required_packages():
    return [
        package_name
        for import_name, package_name in REQUIRED_IMPORTS.items()
        if importlib.util.find_spec(import_name) is None
    ]


def show_requirements_error(missing_packages):
    install_command = f'& "{sys.executable}" -m pip install -r requirements.txt'
    root = tk.Tk()
    root.title("Missing Python Requirements")
    root.geometry("720x360")
    root.minsize(620, 300)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(2, weight=1)

    tk.Label(
        root,
        text="Some Python packages required by the grader are missing.",
        font=(UI_FONT_FAMILY, 13, "bold"),
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
import shutil
import time

try:
    from pygments import lex
    from pygments.lexers import CLexer
    from pygments.token import Comment, Keyword, Name, Number, String
except ImportError:
    lex = None
    CLexer = None
    Comment = Keyword = Name = Number = String = None

# Import backend functions & default config
# Import defaults from configuration.py now
from .configuration import questions as default_questions
from .configuration import folder_weights as default_weights
from .configuration import penalty as default_penalty # Import default penalty
from .configuration import per_error_penalty as default_per_error_penalty # Import default per-error-penalty flag
from .configuration import test_scoring_mode as default_test_scoring_mode
from .configuration import test_error_deduction as default_test_error_deduction
from .configuration import llm_compile_repair_enabled as default_llm_compile_repair_enabled
from .configuration import llm_compile_repair_penalty as default_llm_compile_repair_penalty
from .configuration import llm_compile_repair_max_attempts as default_llm_compile_repair_max_attempts
from .configuration import llm_compile_repair_provider as default_llm_compile_repair_provider
from .configuration import llm_compile_repair_model as default_llm_compile_repair_model
from .configuration import vs_path as default_vs_path # Import default VS path
from .configuration import winrar_path as default_winrar_path # Import default WinRAR path
# Import validator from configuration now
from .configuration import validate_config
from . import configuration
from .preprocess import detect_submission_naming, preprocess_submissions
from .process import run_tests, setup_visual_studio_environment, read_inputs_from_file, get_ground_truth
from .create_excel import create_excels
from .checker_assistant import (
    DEFAULT_GEMINI_MODEL,
    FakeLLMProvider,
    GeminiProvider,
    SuggestionResult,
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
from .post_scoring_review import (
    ReviewCase,
    build_score_review_prompt,
    load_review_cases,
    review_cases_with_llm,
    default_grading_policy,
)
from .semantic_grading import DEFAULT_CHECKER_CONFIG_PATH, load_checker_config, save_checker_config
from .structural_analysis import structural_requirements_errors
from .clear_utils import (
    clear_grades,
    clear_output,
    clear_excels,
    clear_c_files,
    clear_all,
    clear_build_files,
    clear_repair_files,
    clear_review_files,
)
from .utils import log # For direct logging if needed, though most comes via redirect

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
FAKE_PROVIDER_LABEL = "Fake/Offline"
GEMINI_FALLBACK_MODELS = ("gemini-2.0-flash", "gemini-1.5-flash")

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
        if os.getenv("C_TESTER_SUPPRESS_TK_BGERRORS"):
            self.tk.eval("proc bgerror {msg} {}")

        self.title("C Auto Grader")
        self.geometry("1050x760")
        self.minsize(960, 680)
        
        # Add application icon (if available)
        try:
            self.iconbitmap("app_icon.ico")  # You'd need to create this icon file
        except tk.TclError:
            pass  # Silently fail if icon not found

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)  # Progress/Cancel
        self.grid_rowconfigure(2, weight=0, minsize=54)  # Logs

        # --- App State (Initialize with defaults) --- 
        self.gui_questions = default_questions[:]  # Make copies
        self.gui_weights = default_weights.copy()
        self.gui_penalty = default_penalty  # Initialize GUI penalty
        self.gui_per_error_penalty = default_per_error_penalty  # Initialize per-error penalty flag
        self.gui_test_scoring_mode = default_test_scoring_mode
        self.gui_test_error_deduction = default_test_error_deduction
        self.gui_llm_compile_repair_enabled = default_llm_compile_repair_enabled
        self.gui_llm_compile_repair_penalty = default_llm_compile_repair_penalty
        self.gui_llm_compile_repair_max_attempts = default_llm_compile_repair_max_attempts
        self.gui_llm_compile_repair_provider = default_llm_compile_repair_provider
        self.gui_llm_compile_repair_model = default_llm_compile_repair_model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.gui_rar_support = configuration.isRarSupportActive  # New RAR support variable
        self.gui_vs_path = default_vs_path  # Initialize VS path
        self.gui_winrar_path = default_winrar_path  # Initialize WinRAR path
        self.gui_simple_naming = configuration.use_simple_naming  # Initialize simple naming flag
        self.slim_output_var = tk.BooleanVar(value=False)  # Variable for slim checkbox
        self.per_error_penalty_var = tk.BooleanVar(value=default_per_error_penalty)  # Variable for per-error penalty checkbox
        self.test_scoring_mode_var = tk.StringVar(value=default_test_scoring_mode)
        self.llm_compile_repair_var = tk.BooleanVar(value=default_llm_compile_repair_enabled)
        self.llm_compile_repair_provider_var = tk.StringVar(value=default_llm_compile_repair_provider)
        self.llm_compile_repair_model_var = tk.StringVar(value=self.gui_llm_compile_repair_model)
        self.config_valid = False
        self.config_dirty = False  # Track unapplied changes
        self.vs_path_dirty = False  # Track unapplied VS path
        self.winrar_path_dirty = False  # Track unapplied WinRAR path
        self.current_task_thread = None
        self.cancel_event = None
        self.config_rows = []  # To store row widgets [q_entry, w_entry]
        self.setup_assistant_window = None
        self.score_review_window = None
        self.console_collapsed = False

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
        self.log_frame.grid_rowconfigure(0, weight=0)
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(1, weight=0)

        # --- Top Frame Content (Controls) ---
        self.workspace_tabs = ctk.CTkTabview(self.top_frame, corner_radius=8)
        self.workspace_tabs.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.run_tab = self.workspace_tabs.add("Run")
        self.options_tab = self.workspace_tabs.add("Scoring Options")
        self.maintenance_tab = self.workspace_tabs.add("Maintenance")
        self.run_tab.grid_columnconfigure(0, weight=1)
        self.options_tab.grid_columnconfigure(0, weight=1)
        self.maintenance_tab.grid_columnconfigure(0, weight=1)

        self.controls_frame = ctk.CTkFrame(self.run_tab, fg_color="transparent")
        self.controls_frame.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        self.controls_frame.grid_columnconfigure(0, weight=4, minsize=390)
        self.controls_frame.grid_columnconfigure(1, weight=2, minsize=200)
        self.controls_frame.grid_columnconfigure(2, weight=2, minsize=200)
        self.controls_frame.grid_rowconfigure(0, weight=1)

        self.maintenance_frame = ctk.CTkFrame(self.maintenance_tab, fg_color="transparent")
        self.maintenance_frame.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        self.maintenance_frame.grid_columnconfigure(0, weight=1, minsize=300)
        self.maintenance_frame.grid_columnconfigure(1, weight=2, minsize=520)
        self.maintenance_frame.grid_rowconfigure(0, weight=1)

        self.scoring_options_frame = ctk.CTkFrame(self.options_tab, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.scoring_options_frame.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        self.scoring_options_frame.grid_columnconfigure(0, weight=1)

        self.scoring_options_label = ctk.CTkLabel(
            self.scoring_options_frame,
            text="⚙️ Scoring and LLM Options",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["primary"],
        )
        self.scoring_options_label.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")

        self.setup_status_frame = ctk.CTkFrame(self.top_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.setup_status_frame.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.setup_status_frame.grid_columnconfigure(0, weight=1)
        self.setup_status_frame.grid_rowconfigure((0, 1), weight=0)
        self.setup_status_label = ctk.CTkLabel(
            self.setup_status_frame,
            text="Setup readiness: checking...",
            anchor="w",
            justify="left",
            wraplength=900,
        )
        self.setup_status_label.grid(row=0, column=0, padx=12, pady=(8, 0), sticky="ew")
        self.checker_status_label = ctk.CTkLabel(
            self.setup_status_frame,
            text="Checker audit: checking...",
            anchor="w",
            justify="left",
            wraplength=900,
        )
        self.checker_status_label.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        self.setup_status_frame.bind("<Configure>", self._resize_setup_status_label)
        self.global_apply_config_button = ctk.CTkButton(
            self.setup_status_frame,
            text="Apply Config",
            command=self.apply_gui_configuration,
            width=140,
            height=30,
            corner_radius=6,
        )
        self.global_apply_config_button.grid(row=0, column=1, rowspan=2, padx=(12, 6), pady=8, sticky="e")
        self.setup_assistant_button = ctk.CTkButton(
            self.setup_status_frame,
            text="Setup Assistant",
            command=self.open_setup_assistant,
            width=150,
            height=30,
            corner_radius=6,
        )
        self.setup_assistant_button.grid(row=0, column=2, rowspan=2, padx=(6, 12), pady=8, sticky="e")

        # Section 0: Configuration
        self.config_frame = ctk.CTkFrame(self.controls_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.config_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.config_frame.grid_columnconfigure((0, 1), weight=1)  # Columns for table
        # Keep the question list compact; it scrolls when many questions are configured.
        self.config_frame.grid_rowconfigure(2, weight=0)

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
        self.config_table_frame = ctk.CTkScrollableFrame(self.config_frame, fg_color=("gray95", "gray17"), height=96)
        self.config_table_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.config_table_frame.grid_columnconfigure((0, 1), weight=1)  # Columns expand
        
        # Penalty Input with cleaner layout
        self.penalty_frame = ctk.CTkFrame(self.scoring_options_frame, fg_color="transparent")
        self.penalty_frame.grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.penalty_label = ctk.CTkLabel(self.penalty_frame, text="Submission Error Penalty (%):", anchor="w")
        self.penalty_label.pack(side=tk.LEFT, padx=(0,10))
        self.penalty_entry = ctk.CTkEntry(self.penalty_frame, width=60, border_width=1)
        self.penalty_entry.pack(side=tk.LEFT)
        self.penalty_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty()) 
        
        # Add Per-Error Penalty Checkbox with improved spacing
        self.per_error_penalty_frame = ctk.CTkFrame(self.scoring_options_frame, fg_color="transparent")
        self.per_error_penalty_frame.grid(row=2, column=0, padx=12, pady=6, sticky="w")
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

        self.test_scoring_frame = ctk.CTkFrame(self.scoring_options_frame, fg_color="transparent")
        self.test_scoring_frame.grid(row=3, column=0, padx=12, pady=6, sticky="ew")
        self.test_scoring_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.test_scoring_frame, text="Test Case Scoring:", anchor="w").grid(row=0, column=0, padx=(0, 10), pady=3, sticky="w")
        self.test_scoring_menu = ctk.CTkOptionMenu(
            self.test_scoring_frame,
            variable=self.test_scoring_mode_var,
            values=["percentage", "per_error_deduction"],
            command=lambda _choice: self.on_test_scoring_mode_changed(),
            width=170,
        )
        self.test_scoring_menu.grid(row=0, column=1, padx=(0, 10), pady=3, sticky="ew")
        self.test_error_deduction_label = ctk.CTkLabel(self.test_scoring_frame, text="Deduct per failed test:", anchor="w")
        self.test_error_deduction_label.grid(row=1, column=0, padx=(0, 10), pady=3, sticky="w")
        self.test_error_deduction_entry = ctk.CTkEntry(self.test_scoring_frame, width=60, border_width=1)
        self.test_error_deduction_entry.grid(row=1, column=1, padx=(0, 10), pady=3, sticky="w")
        self.test_error_deduction_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty())

        self.compile_repair_frame = ctk.CTkFrame(self.scoring_options_frame, fg_color="transparent")
        self.compile_repair_frame.grid(row=4, column=0, padx=12, pady=6, sticky="ew")
        self.compile_repair_frame.grid_columnconfigure(1, weight=1)
        self.compile_repair_frame.grid_columnconfigure(3, weight=1)
        self.compile_repair_checkbox = ctk.CTkCheckBox(
            self.compile_repair_frame,
            text="Enable LLM compile repair",
            variable=self.llm_compile_repair_var,
            onvalue=True,
            offvalue=False,
            command=self.mark_config_dirty,
            border_width=2,
            hover=True,
        )
        self.compile_repair_checkbox.grid(row=0, column=0, columnspan=4, padx=(0, 10), pady=3, sticky="w")
        ctk.CTkLabel(self.compile_repair_frame, text="Repair penalty:").grid(row=1, column=0, padx=(0, 5), pady=3, sticky="w")
        self.compile_repair_penalty_entry = ctk.CTkEntry(self.compile_repair_frame, width=55, border_width=1)
        self.compile_repair_penalty_entry.grid(row=1, column=1, padx=(0, 10), pady=3, sticky="w")
        self.compile_repair_penalty_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty())
        ctk.CTkLabel(self.compile_repair_frame, text="Max attempts:").grid(row=1, column=2, padx=(0, 5), pady=3, sticky="w")
        self.compile_repair_attempts_entry = ctk.CTkEntry(self.compile_repair_frame, width=45, border_width=1)
        self.compile_repair_attempts_entry.grid(row=1, column=3, padx=(0, 10), pady=3, sticky="w")
        self.compile_repair_attempts_entry.bind("<KeyRelease>", lambda event: self.mark_config_dirty())
        ctk.CTkLabel(self.compile_repair_frame, text="Provider:").grid(row=2, column=0, padx=(0, 5), pady=3, sticky="w")
        self.compile_repair_provider_menu = ctk.CTkOptionMenu(
            self.compile_repair_frame,
            variable=self.llm_compile_repair_provider_var,
            values=["Gemini", "Fake"],
            command=lambda _choice: self.mark_config_dirty(),
            width=90,
        )
        self.compile_repair_provider_menu.grid(row=2, column=1, padx=(0, 10), pady=3, sticky="w")
        ctk.CTkLabel(self.compile_repair_frame, text="Model:").grid(row=2, column=2, padx=(0, 5), pady=3, sticky="w")
        self.compile_repair_model_menu = ctk.CTkOptionMenu(
            self.compile_repair_frame,
            variable=self.llm_compile_repair_model_var,
            values=self.default_model_options(self.gui_llm_compile_repair_model),
            command=lambda _choice: self.mark_config_dirty(),
        )
        self.compile_repair_model_menu.grid(row=2, column=3, padx=(0, 10), pady=3, sticky="ew")
        
        # Buttons with improved styling and spacing
        self.config_buttons_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        self.config_buttons_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=10)
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
        self.config_status_label.grid(row=4, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="ew")

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
        
        self.rar_support_var = tk.BooleanVar(value=self.gui_rar_support)
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
            text="Needs rarfile + WinRAR/UnRAR",
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
            text="Simple naming (hwN.c)",
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
            text="Auto-detected; one C file is copied to all configured questions",
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
            command=self.start_grading,
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
            text="Slim output",
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

        self.score_review_button = ctk.CTkButton(
            self.grading_frame,
            text="🔎 LLM Score Review",
            command=self.open_post_scoring_review,
            height=32,
            width=200,
            corner_radius=6,
            hover=True,
            border_spacing=6,
            state="disabled"
        )
        self.score_review_button.grid(row=5, column=0, padx=15, pady=(0, 8))

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
        self.open_folder_button.grid(row=6, column=0, padx=15, pady=(0, 15))

        # Section 3: Clear Actions
        self.clear_frame = ctk.CTkFrame(self.maintenance_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.clear_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.clear_frame.grid_columnconfigure((0, 1), weight=1)
        
        self.clear_label = ctk.CTkLabel(
            self.clear_frame, 
            text="🧹 Clear Actions", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["primary"]
        )
        self.clear_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 15))
        
        button_height = 32
        button_corner = 6
        button_width = 140
        
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

        self.clear_repair_button = ctk.CTkButton(
            self.clear_frame,
            text="Clear Repair",
            command=lambda: self.run_task(lambda: clear_repair_files(self.gui_questions)),
            height=button_height,
            width=button_width,
            corner_radius=button_corner,
            hover=True
        )
        self.clear_repair_button.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        self.clear_review_button = ctk.CTkButton(
            self.clear_frame,
            text="Clear Reviews",
            command=lambda: self.run_task(lambda: clear_review_files(self.gui_questions)),
            height=button_height,
            width=button_width,
            corner_radius=button_corner,
            hover=True
        )
        self.clear_review_button.grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        
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
        self.clear_all_button.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # Section 4: Dependencies
        self.dependencies_frame = ctk.CTkFrame(self.maintenance_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.dependencies_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.dependencies_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

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
        self.console_toggle_button = ctk.CTkButton(
            self.log_frame,
            text="Hide Console",
            command=self.toggle_console,
            height=28,
            width=120,
            corner_radius=6,
        )
        self.console_toggle_button.grid(row=0, column=1, sticky="e", padx=15, pady=(10, 5))
        
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
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=15, pady=(0, 15))

        # Configure tags for log levels with enhanced colors
        self.log_textbox.tag_config("info_tag", foreground=COLORS["primary"])       # Blue
        self.log_textbox.tag_config("success_tag", foreground=COLORS["secondary"])  # Green
        self.log_textbox.tag_config("warning_tag", foreground=COLORS["warning"])    # Orange
        self.log_textbox.tag_config("error_tag", foreground=COLORS["danger"])       # Red
        self.toggle_console()

        # Store active buttons to disable during tasks
        self.active_buttons = [
            self.apply_config_button, self.global_apply_config_button,
            self.browse_button, self.preprocess_button, self.run_button, self.checker_manager_button,
            self.open_excel_button, self.score_review_button, self.open_folder_button,
            self.clear_grades_button, self.clear_output_button, self.clear_c_button,
            self.clear_excels_button, self.clear_build_button, self.clear_repair_button,
            self.clear_review_button, self.clear_all_button
        ]

        self.setup_button_commands() # Bind commands AFTER initial validation might disable them

        # --- Populate initial config & Validate --- 
        self.populate_config_fields()
        self.apply_gui_configuration(show_dialogs=False) # Validate initial config without blocking startup
        
        # Perform initial validation of VS and WinRAR paths when the GUI starts
        # Use after() to ensure GUI is fully initialized first
        if not os.getenv("C_TESTER_SKIP_STARTUP_VALIDATION"):
            self.after(100, self.validate_initial_paths)
            self.after(250, self.maybe_show_setup_assistant)

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
                text=(
                    f"Detected simple naming: {counts['simple']} file(s). "
                    "When multiple questions are configured and a submission has one real C file, "
                    "preprocess copies it to every question."
                ),
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
                "Preprocess handles both: hw123_qN.c goes to QN; a single plain C file in a multi-question "
                "submission is copied to every configured question."
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

        if not self.config_valid or self.config_dirty:
            self.preprocess_button.configure(state="disabled")
            self.update_setup_readiness_banner()
            return
        
        # First check if a zip file is selected
        if not zip_path:
            self.preprocess_button.configure(state="disabled")
            self.update_setup_readiness_banner()
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
        self.update_setup_readiness_banner()

    def set_controls_state(self, state):
        """Enable or disable all control buttons."""
        for button in self.active_buttons:
            button.configure(state=state)
        if state == "normal":
            self.update_excel_button_state()
            self.update_dependent_button_states()
        # Special handling for entry?
        # self.zip_entry.configure(state=state)
        # Enable/disable cancel button based on task running
        self.cancel_button.configure(state="normal" if state == "disabled" else "disabled")

    def shutdown_for_tests(self):
        """Drain pending Tk work before tests destroy the root window."""
        try:
            self.update()
            self.update_idletasks()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    def toggle_console(self):
        self.console_collapsed = not self.console_collapsed
        if self.console_collapsed:
            self.log_textbox.grid_remove()
            self.log_frame.grid_rowconfigure(1, weight=0)
            self.grid_rowconfigure(2, weight=0, minsize=54)
            self.console_toggle_button.configure(text="Show Console")
        else:
            self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=15, pady=(0, 15))
            self.log_frame.grid_rowconfigure(1, weight=1)
            self.grid_rowconfigure(2, weight=1, minsize=130)
            self.console_toggle_button.configure(text="Hide Console")

    def update_excel_button_state(self):
        state = "normal" if os.path.exists("final_grades.xlsx") else "disabled"
        self.open_excel_button.configure(state=state)
        self.score_review_button.configure(state=state)

    def _resize_setup_status_label(self, event):
        wraplength = max(300, event.width - 330)
        self.setup_status_label.configure(wraplength=wraplength)
        self.checker_status_label.configure(wraplength=wraplength)

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

    def get_setup_readiness(self):
        """Return readiness checks used by the setup assistant and main banner."""
        zip_path = self.zip_path_var.get().strip()
        packages_ready = not missing_required_packages()
        config_ready = self.config_valid and not self.config_dirty
        zip_ready = bool(zip_path and os.path.exists(zip_path) and zip_path.lower().endswith(".zip"))
        rar_ready = (not self.rar_support_var.get()) or (not self.winrar_path_dirty and bool(self.gui_winrar_path))
        vs_ready = not self.vs_path_dirty and bool(self.gui_vs_path)
        gemini_ready = bool(get_google_api_key())
        checker_config_ready = isinstance(load_checker_config(DEFAULT_CHECKER_CONFIG_PATH), dict)
        compile_repair_api_ready = (
            (not self.llm_compile_repair_var.get())
            or self.llm_compile_repair_provider_var.get() == "Fake"
            or gemini_ready
        )
        scoring_ready = packages_ready and config_ready and vs_ready and checker_config_ready and compile_repair_api_ready
        checker_ready = packages_ready and checker_config_ready
        return {
            "packages": packages_ready,
            "assignment": config_ready,
            "visual_studio": vs_ready,
            "submissions_zip": zip_ready,
            "rar": rar_ready,
            "checker_config": checker_config_ready,
            "gemini_api": gemini_ready,
            "compile_repair_api": compile_repair_api_ready,
            "preprocess": packages_ready and config_ready and zip_ready and rar_ready,
            "scoring": scoring_ready,
            "checker": checker_ready,
            "grading": scoring_ready,
        }

    def checker_status_summary(self):
        checker_config = load_checker_config(DEFAULT_CHECKER_CONFIG_PATH)
        question_configs = checker_config.get("questions", {}) if isinstance(checker_config, dict) else {}
        audited = []
        needs_audit = []
        needs_checker = []
        for question in self.gui_questions:
            question_config = question_configs.get(question) or question_configs.get(question.upper())
            metadata = question_config.get("metadata", {}) if isinstance(question_config, dict) else {}
            if metadata.get("audit_status") == "passed":
                audited.append(question)
            elif question_config:
                needs_audit.append(question)
            else:
                needs_checker.append(question)
        statuses = []
        if audited:
            statuses.append(f"audited: {', '.join(audited)}")
        if needs_audit:
            statuses.append(f"needs audit: {', '.join(needs_audit)}")
        if needs_checker:
            statuses.append(f"needs checker: {', '.join(needs_checker)}")
        return "; ".join(statuses) if statuses else "no configured questions"

    def update_setup_readiness_banner(self):
        if not hasattr(self, "setup_status_label"):
            return
        readiness = self.get_setup_readiness()
        preprocess_status = "ready" if readiness["preprocess"] else "needs setup"
        scoring_status = "ready" if readiness["scoring"] else "needs setup"
        checker_status = "ready" if readiness["checker"] else "needs setup"
        missing = []
        if not readiness["packages"]:
            missing.append("Python packages")
        if not readiness["assignment"]:
            missing.append("assignment folders/files")
        if not readiness["visual_studio"]:
            missing.append("Visual Studio path")
        if not readiness["submissions_zip"]:
            missing.append("submissions zip")
        if not readiness["rar"]:
            missing.append("WinRAR/UnRAR")
        if not readiness["checker_config"]:
            missing.append("checker configuration")
        if not readiness["compile_repair_api"]:
            missing.append("GOOGLE_API_KEY or Fake provider for compile repair")
        detail = "All required checks are ready." if not missing else "Missing: " + ", ".join(missing)
        color = COLORS["secondary"] if readiness["preprocess"] and readiness["scoring"] and readiness["checker"] else COLORS["warning"]
        self.setup_status_label.configure(
            text=f"Setup readiness: Preprocess {preprocess_status}; Scoring {scoring_status}; Checker {checker_status}. {detail}",
            text_color=color,
        )
        self.checker_status_label.configure(
            text=f"Checker audit: {self.checker_status_summary()}",
            text_color=color,
        )

    def open_setup_assistant(self):
        if self.setup_assistant_window and self.setup_assistant_window.winfo_exists():
            self.setup_assistant_window.focus()
            return
        self.setup_assistant_window = SetupAssistantWindow(self)

    def maybe_show_setup_assistant(self):
        readiness = self.get_setup_readiness()
        if readiness["scoring"]:
            return
        if os.path.exists("final_grades.xlsx"):
            return
        self.open_setup_assistant()

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
                log("\n--- TASK FAILED --- \n", level="error")
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

    def start_grading(self):
        if self.config_dirty:
            self.apply_gui_configuration(show_dialogs=True)
        if not self.config_valid or self.config_dirty:
            messagebox.showwarning(
                "Apply Configuration First",
                "Fix/apply the current configuration before running grading. "
                "This includes scoring mode and LLM compile repair options.",
            )
            return
        self.run_task(self.task_run_grading_internal)

    @staticmethod
    def default_model_options(current_model=""):
        models = [current_model, os.getenv("GEMINI_MODEL", ""), DEFAULT_GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]
        unique_models = []
        for model in models:
            if model and model not in unique_models:
                unique_models.append(model)
        return unique_models or [DEFAULT_GEMINI_MODEL]

    def on_test_scoring_mode_changed(self):
        self.update_test_error_deduction_state()
        self.mark_config_dirty()

    def update_test_error_deduction_state(self):
        enabled = self.test_scoring_mode_var.get() == "per_error_deduction"
        state = "normal" if enabled else "disabled"
        color = COLORS["text_light"] if ctk.get_appearance_mode() == "Dark" else COLORS["text_dark"]
        if not enabled:
            color = "gray"
        self.test_error_deduction_entry.configure(state=state)
        self.test_error_deduction_label.configure(text_color=color)

    def configure_apply_buttons(self, **kwargs):
        self.apply_config_button.configure(**kwargs)
        self.global_apply_config_button.configure(**kwargs)

    def current_gui_config(self):
        """Return the settings that should be restored on the next GUI startup."""
        return {
            "questions": self.gui_questions,
            "folder_weights": self.gui_weights,
            "penalty": self.gui_penalty,
            "per_error_penalty": self.gui_per_error_penalty,
            "test_scoring_mode": self.gui_test_scoring_mode,
            "test_error_deduction": self.gui_test_error_deduction,
            "llm_compile_repair_enabled": self.gui_llm_compile_repair_enabled,
            "llm_compile_repair_penalty": self.gui_llm_compile_repair_penalty,
            "llm_compile_repair_max_attempts": self.gui_llm_compile_repair_max_attempts,
            "llm_compile_repair_provider": self.gui_llm_compile_repair_provider,
            "llm_compile_repair_model": self.gui_llm_compile_repair_model,
            "rar_support": self.gui_rar_support,
            "simple_naming": self.gui_simple_naming,
            "vs_path": self.gui_vs_path,
            "winrar_path": self.gui_winrar_path,
        }

    def save_current_gui_config(self):
        """Persist current GUI settings without interrupting the user on failure."""
        try:
            configuration.save_gui_config(self.current_gui_config())
        except OSError as exc:
            log(f"Could not save GUI configuration: {exc}", "warning")

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
        self.save_current_gui_config()
        
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
            self.after(10, lambda: self.configure_apply_buttons(border_color=COLORS["danger"], border_width=2))
            return # Stop the task
        else:
            log("Configuration validated successfully.", "info")
            self.save_current_gui_config()
            
        # --- Proceed with Grading Task --- 
        compile_repair_provider = self.make_compile_repair_provider()
        run_tests(
            self.gui_questions,
            progress_callback,
            cancel_event,
            scoring_mode=self.gui_test_scoring_mode,
            deduction_per_error=self.gui_test_error_deduction,
            llm_compile_repair_enabled=self.gui_llm_compile_repair_enabled,
            llm_compile_repair_provider=compile_repair_provider,
            llm_compile_repair_penalty=self.gui_llm_compile_repair_penalty,
            llm_compile_repair_max_attempts=self.gui_llm_compile_repair_max_attempts,
            vs_path_override=self.gui_vs_path,
        )
        if not (cancel_event and cancel_event.is_set()):
             # Get slim state from checkbox variable
             slim_mode = self.slim_output_var.get()
             per_error_penalty_mode = self.gui_per_error_penalty
             
             # Log the modes being used
             mode_str = "per error" if per_error_penalty_mode else "once per student"
             scoring_details = self.gui_test_scoring_mode
             if self.gui_test_scoring_mode == "per_error_deduction":
                 scoring_details += f" ({self.gui_test_error_deduction:g} point(s) per failed test)"
             repair_details = "disabled"
             if self.gui_llm_compile_repair_enabled:
                 repair_details = (
                     f"{self.gui_llm_compile_repair_provider}, "
                     f"{self.gui_llm_compile_repair_max_attempts} attempt(s), "
                     f"-{self.gui_llm_compile_repair_penalty:g}"
                 )
             log(f"Creating Excel output (Slim mode: {slim_mode}, Penalty mode: {mode_str}, Test scoring: {scoring_details}, Compile repair: {repair_details})...", "info")
             
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
        self.run_button.configure(command=self.start_grading)
        self.checker_manager_button.configure(command=self.open_checker_manager)
        self.score_review_button.configure(command=self.open_post_scoring_review)
        # Section 3: Clear Actions
        self.clear_grades_button.configure(command=lambda: self.run_task(lambda: clear_grades(self.gui_questions)))
        self.clear_output_button.configure(command=lambda: self.run_task(lambda: clear_output(self.gui_questions)))
        self.clear_c_button.configure(command=lambda: self.run_task(lambda: clear_c_files(self.gui_questions)))
        self.clear_excels_button.configure(command=lambda: self.run_task(self.task_clear_excels_internal))
        self.clear_build_button.configure(command=lambda: self.run_task(clear_build_files))
        self.clear_repair_button.configure(command=lambda: self.run_task(lambda: clear_repair_files(self.gui_questions)))
        self.clear_review_button.configure(command=lambda: self.run_task(lambda: clear_review_files(self.gui_questions)))
        self.clear_all_button.configure(command=lambda: self.run_task(lambda: clear_all(self.gui_questions)))

    def make_compile_repair_provider(self):
        if not self.gui_llm_compile_repair_enabled:
            return None
        if self.gui_llm_compile_repair_provider == "Fake":
            return FakeLLMProvider()
        if not get_google_api_key():
            raise ValueError(
                "GOOGLE_API_KEY is not set.\n\n"
                "Open the Checker Manager for setup instructions, or choose Fake for deterministic tests."
            )
        return GeminiProvider(model=self.gui_llm_compile_repair_model or None)

    def open_checker_manager(self):
        existing_window = getattr(self, "checker_manager_window", None)
        if existing_window is not None and existing_window.winfo_exists():
            existing_window.show_on_top()
            return
        self.checker_manager_window = CheckerManagerWindow(self)
        self.checker_manager_window.show_on_top()

    def open_post_scoring_review(self):
        existing_window = getattr(self, "score_review_window", None)
        if existing_window is not None and existing_window.winfo_exists():
            existing_window.show_on_top()
            return
        if not os.path.exists("final_grades.xlsx"):
            messagebox.showwarning("No Final Grades", "Run grading first so final_grades.xlsx exists.")
            return
        self.score_review_window = PostScoringReviewWindow(self)
        self.score_review_window.show_on_top()

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
        self.configure_apply_buttons(border_color=COLORS["warning"], border_width=2) 
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
        self.test_scoring_mode_var.set(self.gui_test_scoring_mode)
        self.test_error_deduction_entry.delete(0, tk.END)
        self.test_error_deduction_entry.insert(0, str(self.gui_test_error_deduction))
        self.update_test_error_deduction_state()
        self.llm_compile_repair_var.set(self.gui_llm_compile_repair_enabled)
        self.compile_repair_penalty_entry.delete(0, tk.END)
        self.compile_repair_penalty_entry.insert(0, str(self.gui_llm_compile_repair_penalty))
        self.compile_repair_attempts_entry.delete(0, tk.END)
        self.compile_repair_attempts_entry.insert(0, str(self.gui_llm_compile_repair_max_attempts))
        self.llm_compile_repair_provider_var.set(self.gui_llm_compile_repair_provider)
        self.llm_compile_repair_model_var.set(self.gui_llm_compile_repair_model)
        self.compile_repair_model_menu.configure(values=self.default_model_options(self.gui_llm_compile_repair_model))
        # Set RAR support checkbox
        self.rar_support_var.set(self.gui_rar_support)
        # Set simple naming checkbox
        self.simple_naming_var.set(self.gui_simple_naming)

    def apply_gui_configuration(self, show_dialogs=True):
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

        parsed_test_scoring_mode = self.test_scoring_mode_var.get()
        if parsed_test_scoring_mode not in {"percentage", "per_error_deduction"}:
            parse_errors.append(f"Invalid test scoring mode: '{parsed_test_scoring_mode}'.")

        test_error_deduction_str = self.test_error_deduction_entry.get().strip()
        parsed_test_error_deduction = None
        try:
            parsed_test_error_deduction = float(test_error_deduction_str)
            if parsed_test_error_deduction < 0:
                parse_errors.append("Test error deduction cannot be negative.")
                parsed_test_error_deduction = None
        except ValueError:
            parse_errors.append(f"Invalid numeric value for test error deduction: '{test_error_deduction_str}'.")

        parsed_compile_repair_enabled = self.llm_compile_repair_var.get()
        parsed_compile_repair_provider = self.llm_compile_repair_provider_var.get()
        parsed_compile_repair_model = self.llm_compile_repair_model_var.get().strip()
        if parsed_compile_repair_provider not in {"Gemini", "Fake"}:
            parse_errors.append(f"Invalid compile repair provider: '{parsed_compile_repair_provider}'.")

        parsed_compile_repair_penalty = None
        try:
            parsed_compile_repair_penalty = float(self.compile_repair_penalty_entry.get().strip())
            if parsed_compile_repair_penalty < 0:
                parse_errors.append("Compile repair penalty cannot be negative.")
                parsed_compile_repair_penalty = None
        except ValueError:
            parse_errors.append(
                f"Invalid numeric value for compile repair penalty: '{self.compile_repair_penalty_entry.get().strip()}'."
            )

        parsed_compile_repair_attempts = None
        try:
            parsed_compile_repair_attempts = int(self.compile_repair_attempts_entry.get().strip())
            if parsed_compile_repair_attempts < 1:
                parse_errors.append("Compile repair max attempts must be at least 1.")
                parsed_compile_repair_attempts = None
        except ValueError:
            parse_errors.append(
                f"Invalid numeric value for compile repair max attempts: '{self.compile_repair_attempts_entry.get().strip()}'."
            )
        
        # Get RAR support value
        parsed_rar_support = self.rar_support_var.get()

        if parse_errors:
            if show_dialogs:
                messagebox.showerror("Configuration Parse Error", "\n".join(parse_errors))
            self.config_status_label.configure(text="Status: Invalid Input", text_color=COLORS["danger"])
            self.config_valid = False
            self.config_dirty = True  # Still dirty, needs fixing
            self.configure_apply_buttons(border_color=COLORS["danger"], border_width=2)  # Error border
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
             
             if show_dialogs:
                 messagebox.showwarning("Configuration Validation Error", "\n\n".join(formatted_errors))
        else:
             self.config_valid = True
             self.config_dirty = False  # Applied successfully
             self.gui_questions = parsed_questions
             self.gui_weights = parsed_weights
             self.gui_penalty = parsed_penalty
             self.gui_per_error_penalty = parsed_per_error_penalty
             self.gui_test_scoring_mode = parsed_test_scoring_mode
             self.gui_test_error_deduction = parsed_test_error_deduction
             self.gui_llm_compile_repair_enabled = parsed_compile_repair_enabled
             self.gui_llm_compile_repair_penalty = parsed_compile_repair_penalty
             self.gui_llm_compile_repair_max_attempts = parsed_compile_repair_attempts
             self.gui_llm_compile_repair_provider = parsed_compile_repair_provider
             self.gui_llm_compile_repair_model = parsed_compile_repair_model
             self.gui_rar_support = parsed_rar_support
             self.gui_simple_naming = self.simple_naming_var.get()
             self.save_current_gui_config()
             status_text = "Status: Valid ✓"
             status_color = COLORS["secondary"]  # Green
             # apply_border_color remains default
             log("GUI Configuration Applied and Validated.", "info")

        self.config_status_label.configure(text=status_text, text_color=status_color)
        # Reset Apply button appearance
        self.configure_apply_buttons(border_color=apply_border_color, border_width=apply_border_width)
        self.update_dependent_button_states()

    def update_dependent_button_states(self):
        """Enable/disable buttons based on config validity with enhanced visual feedback."""
        if self.config_valid and not self.config_dirty:
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
                self.clear_repair_button.configure(state=clear_state)
                self.clear_review_button.configure(state=clear_state)
                self.clear_all_button.configure(state=clear_state)
            else:
                clear_state = "disabled"
                self.clear_grades_button.configure(state=clear_state)
                self.clear_output_button.configure(state=clear_state)
                self.clear_c_button.configure(state=clear_state)
                self.clear_repair_button.configure(state=clear_state)
                self.clear_review_button.configure(state=clear_state)
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
            self.clear_repair_button.configure(state=clear_state)
            self.clear_review_button.configure(state=clear_state)
            self.clear_all_button.configure(state=clear_state)
            
            # Check preprocess button state separately
            self.check_preprocess_button_state()
        self.update_excel_button_state()

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
        self.save_current_gui_config()
        self.update_dependent_button_states()

    def _handle_vs_validation_warning(self, vs_path, message):
        """Handle VS path validation with warnings (runs on main thread)"""
        messagebox.showwarning("Warning", message)
        self.gui_vs_path = vs_path
        self.vs_path_dirty = False
        self.vs_path_status_label.configure(text="Status: Applied with warnings", text_color=COLORS["warning"])
        self.apply_vs_path_button.configure(border_color=self._default_border_color, border_width=1, state="normal")
        log(f"Visual Studio path applied with warnings: {vs_path}", "warning")
        self.save_current_gui_config()
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
            self.save_current_gui_config()
            self.update_dependent_button_states()
            
        except Exception as e:
            messagebox.showwarning("Warning", f"Cannot verify WinRAR executable:\n{str(e)}\n\nPath will be applied but might not work correctly.")
            self.winrar_path_status_label.configure(text="Status: Applied with warnings", text_color=COLORS["warning"])
            self.gui_winrar_path = winrar_path
            self.winrar_path_dirty = False
            self.apply_winrar_path_button.configure(border_color=self._default_border_color, border_width=1)
            log(f"WinRAR path applied with warnings: {winrar_path}", "warning")
            self.save_current_gui_config()
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
                
        except Exception:
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
        except Exception:
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
            self.save_current_gui_config()


class SetupAssistantWindow(ctk.CTkToplevel):
    """Guided first-run setup that reuses the main app's validation state."""

    def __init__(self, parent: App):
        super().__init__(parent)
        self.parent = parent
        self.title("Setup Assistant")
        self.geometry("860x620")
        self.minsize(760, 560)
        self.transient(parent)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.title_label = ctk.CTkLabel(
            self,
            text="Setup Assistant",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["primary"],
            anchor="w",
        )
        self.title_label.grid(row=0, column=0, padx=18, pady=(16, 4), sticky="ew")
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Follow these steps once per assignment. When the readiness checks pass, continue to the main grader screen.",
            anchor="w",
            justify="left",
            wraplength=780,
        )
        self.subtitle_label.grid(row=1, column=0, padx=18, pady=(0, 8), sticky="ew")
        self.subtitle_label.bind("<Configure>", lambda event: self.subtitle_label.configure(wraplength=max(360, event.width - 10)))

        self.global_status_frame = ctk.CTkFrame(self, corner_radius=8, border_width=1, border_color=COLORS["border"])
        self.global_status_frame.grid(row=2, column=0, padx=18, pady=(0, 8), sticky="ew")
        self.global_status_frame.grid_columnconfigure(0, weight=1)
        self.global_status_label = ctk.CTkLabel(
            self.global_status_frame,
            text="Checking setup readiness...",
            anchor="w",
            justify="left",
            wraplength=780,
        )
        self.global_status_label.grid(row=0, column=0, padx=12, pady=8, sticky="ew")
        self.global_status_frame.bind(
            "<Configure>",
            lambda event: self.global_status_label.configure(wraplength=max(360, event.width - 24)),
        )

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=3, column=0, padx=18, pady=(0, 10), sticky="nsew")
        self.tabs = {
            "Assignment": self.tabview.add("1. Assignment"),
            "Dependencies": self.tabview.add("2. Dependencies"),
            "Submissions": self.tabview.add("3. Submissions"),
            "Options": self.tabview.add("4. Options"),
            "Readiness": self.tabview.add("5. Readiness"),
        }
        for tab in self.tabs.values():
            tab.grid_columnconfigure(0, weight=1)

        self.question_var = tk.StringVar(value=self._first_question())
        self.readiness_label = None
        self.next_button = None
        self._build_assignment_tab()
        self._build_dependencies_tab()
        self._build_submissions_tab()
        self._build_options_tab()
        self._build_readiness_tab()
        self.refresh()

    def _first_question(self):
        questions = self._question_names()
        return questions[0] if questions else "Q1"

    def _question_names(self):
        names = []
        for row_widgets in self.parent.config_rows:
            q_name = row_widgets[0].get().strip()
            if q_name:
                names.append(q_name)
        return names or list(self.parent.gui_questions)

    def _section_text(self, parent, text, row):
        label = ctk.CTkLabel(parent, text=text, anchor="w", justify="left", wraplength=760)
        label.grid(row=row, column=0, padx=12, pady=(8, 4), sticky="ew")
        label.bind("<Configure>", lambda event, current_label=label: current_label.configure(wraplength=max(340, event.width - 24)))
        return label

    def _build_assignment_tab(self):
        tab = self.tabs["Assignment"]
        self._section_text(
            tab,
            "Define the questions and weights on the main screen, then use these actions to create local assignment folders and attach private local assets.",
            0,
        )
        ctk.CTkButton(tab, text="Apply Main-Screen Config", command=self._apply_parent_config).grid(
            row=1, column=0, padx=12, pady=6, sticky="w"
        )
        ctk.CTkButton(tab, text="Create Missing Q*/C Folders", command=self._create_scaffolds).grid(
            row=2, column=0, padx=12, pady=6, sticky="w"
        )

        selector_frame = ctk.CTkFrame(tab, fg_color="transparent")
        selector_frame.grid(row=3, column=0, padx=12, pady=(18, 6), sticky="ew")
        ctk.CTkLabel(selector_frame, text="Question:").pack(side=tk.LEFT, padx=(0, 8))
        self.question_menu = ctk.CTkOptionMenu(selector_frame, variable=self.question_var, values=self._question_names() or ["Q1"])
        self.question_menu.pack(side=tk.LEFT)

        ctk.CTkButton(tab, text="Choose input.txt For Selected Question", command=self._copy_input_file).grid(
            row=4, column=0, padx=12, pady=6, sticky="w"
        )
        ctk.CTkButton(tab, text="Choose original_sol.c For Selected Question", command=self._copy_solution_file).grid(
            row=5, column=0, padx=12, pady=6, sticky="w"
        )
        self.assignment_status_label = self._section_text(tab, "", 6)

    def _build_dependencies_tab(self):
        tab = self.tabs["Dependencies"]
        self._section_text(
            tab,
            "Validate compiler and optional tools. Grading requires a valid Visual Studio C++ environment. RAR and Gemini are only required when enabled.",
            0,
        )
        ctk.CTkButton(tab, text="Validate Visual Studio Path", command=self.parent.apply_vs_path).grid(
            row=1, column=0, padx=12, pady=6, sticky="w"
        )
        ctk.CTkButton(tab, text="Validate WinRAR/UnRAR Path", command=self.parent.apply_winrar_path).grid(
            row=2, column=0, padx=12, pady=6, sticky="w"
        )
        self.dependencies_status_label = self._section_text(tab, "", 3)

    def _build_submissions_tab(self):
        tab = self.tabs["Submissions"]
        self._section_text(
            tab,
            "Select the main submissions zip. The assistant will reuse the existing filename detector and show whether preprocessing is ready.",
            0,
        )
        ctk.CTkButton(tab, text="Browse Submissions Zip", command=self._browse_zip).grid(row=1, column=0, padx=12, pady=6, sticky="w")
        ctk.CTkButton(tab, text="Detect Naming Mode", command=lambda: self.parent.detect_and_apply_naming(show_dialog=True)).grid(
            row=2, column=0, padx=12, pady=6, sticky="w"
        )
        self.submissions_status_label = self._section_text(tab, "", 3)

    def _build_options_tab(self):
        tab = self.tabs["Options"]
        self._section_text(
            tab,
            "Use the main screen for detailed grading options: penalty mode, test scoring mode, slim Excel output, and LLM compile repair. Click Apply Config after changing them.",
            0,
        )
        ctk.CTkButton(tab, text="Apply Current Options", command=self._apply_parent_config).grid(row=1, column=0, padx=12, pady=6, sticky="w")
        self.options_status_label = self._section_text(tab, "", 2)

    def _build_readiness_tab(self):
        tab = self.tabs["Readiness"]
        self.readiness_label = self._section_text(tab, "", 0)
        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.grid(row=1, column=0, padx=12, pady=14, sticky="ew")
        ctk.CTkButton(button_frame, text="Refresh Checks", command=self.refresh).pack(side=tk.LEFT, padx=(0, 8))
        self.next_button = ctk.CTkButton(button_frame, text="Next To Main Screen", command=self._continue_to_main)
        self.next_button.pack(side=tk.LEFT)

    def _apply_parent_config(self):
        self.parent.apply_gui_configuration()
        self.refresh()

    def _create_scaffolds(self):
        for question in self._question_names():
            os.makedirs(os.path.join(question, "C"), exist_ok=True)
        self.parent.apply_gui_configuration()
        self.refresh()

    def _copy_input_file(self):
        self._copy_assignment_file("input.txt", (("Text files", "*.txt"), ("All files", "*.*")))

    def _copy_solution_file(self):
        self._copy_assignment_file("original_sol.c", (("C files", "*.c"), ("All files", "*.*")))

    def _copy_assignment_file(self, target_name, filetypes):
        question = self.question_var.get().strip()
        if not question:
            messagebox.showwarning("Question Missing", "Choose a question first.")
            return
        source = filedialog.askopenfilename(title=f"Choose {target_name}", filetypes=filetypes)
        if not source:
            return
        os.makedirs(question, exist_ok=True)
        shutil.copy2(source, os.path.join(question, target_name))
        self.parent.apply_gui_configuration()
        self.refresh()

    def _browse_zip(self):
        self.parent.browse_zip()
        self.refresh()

    def _continue_to_main(self):
        readiness = self.parent.get_setup_readiness()
        if not readiness["assignment"]:
            messagebox.showwarning("Setup Incomplete", "Fix assignment setup before continuing to the main screen.")
            return
        self.parent.update_setup_readiness_banner()
        self.destroy()

    def refresh(self):
        question_names = self._question_names()
        if question_names:
            self.question_menu.configure(values=question_names)
            if self.question_var.get() not in question_names:
                self.question_var.set(question_names[0])

        readiness = self.parent.get_setup_readiness()
        self._refresh_global_status(readiness)
        missing_assignment = []
        for question in question_names:
            if not os.path.isdir(os.path.join(question, "C")):
                missing_assignment.append(f"{question}/C")
            if not os.path.isfile(os.path.join(question, "input.txt")):
                missing_assignment.append(f"{question}/input.txt")
            if not os.path.isfile(os.path.join(question, "original_sol.c")):
                missing_assignment.append(f"{question}/original_sol.c")

        assignment_text = "Assignment ready." if readiness["assignment"] else "Assignment needs: " + ", ".join(missing_assignment or ["valid folders, files, and weights"])
        self.assignment_status_label.configure(text=assignment_text, text_color=COLORS["secondary"] if readiness["assignment"] else COLORS["warning"])

        dependency_lines = [
            f"Python packages: {'ready' if readiness['packages'] else 'missing packages'}",
            f"Visual Studio: {'ready' if readiness['visual_studio'] else 'needs validation'}",
            f"RAR support: {'ready/not required' if readiness['rar'] else 'needs WinRAR/UnRAR validation'}",
            f"Checker config: {'ready/default available' if readiness['checker_config'] else 'needs valid checker configuration'}",
            f"Gemini API: {'ready' if readiness['gemini_api'] else 'not set; choose Fake/offline mode or set GOOGLE_API_KEY'}",
            f"Compile repair: {'ready/disabled' if readiness['compile_repair_api'] else 'needs GOOGLE_API_KEY or Fake provider'}",
        ]
        self.dependencies_status_label.configure(text="\n".join(dependency_lines))

        zip_path = self.parent.zip_path_var.get().strip()
        submissions_text = f"Zip: {zip_path or 'not selected'}\nPreprocess: {'ready' if readiness['preprocess'] else 'needs setup'}"
        self.submissions_status_label.configure(text=submissions_text)

        self.options_status_label.configure(
            text=(
                f"Scoring: {self.parent.test_scoring_mode_var.get()}\n"
                f"Compile repair: {'enabled' if self.parent.llm_compile_repair_var.get() else 'disabled'}\n"
                "Use the main screen for advanced edits, then return here or watch the readiness banner."
            )
        )

        readiness_text = (
            f"Ready for Preprocess: {'yes' if readiness['preprocess'] else 'no'}\n"
            f"Ready for Scoring: {'yes' if readiness['scoring'] else 'no'}\n"
            f"Ready for Checker Manager: {'yes' if readiness['checker'] else 'no'}\n"
            f"Ready for LLM Checker/Audit: {'yes' if readiness['gemini_api'] else 'no; Fake/manual checker mode is still available'}\n"
            f"Ready for Compile Repair: {'yes' if readiness['compile_repair_api'] else 'no'}\n\n"
            "When assignment setup is valid, continue to the main screen. The main action buttons remain gated by these checks."
        )
        self.readiness_label.configure(text=readiness_text, text_color=COLORS["secondary"] if readiness["assignment"] else COLORS["warning"])
        self.next_button.configure(state="normal" if readiness["assignment"] else "disabled")
        self.parent.update_setup_readiness_banner()

    def _refresh_global_status(self, readiness):
        items = [
            f"Assignment: {'ready' if readiness['assignment'] else 'needs setup'}",
            f"Dependencies: {'ready' if readiness['scoring'] else 'needs setup'}",
            f"Submissions: {'ready' if readiness['preprocess'] else 'optional/not ready'}",
            f"Checker: {'ready' if readiness['checker'] else 'needs setup'}",
            f"Compile repair API: {'ready/disabled' if readiness['compile_repair_api'] else 'needs setup'}",
        ]
        all_core_ready = readiness["assignment"] and readiness["scoring"] and readiness["checker"]
        self.global_status_label.configure(
            text=" | ".join(items),
            text_color=COLORS["secondary"] if all_core_ready else COLORS["warning"],
        )


class PostScoringReviewWindow(ctk.CTkToplevel):
    """Review scored rows with an LLM while keeping student identity out of prompts."""

    def __init__(self, parent: App):
        super().__init__(parent)
        self.parent = parent
        self.title("Post-Scoring LLM Review")
        self.geometry("1250x820")
        self.minsize(1050, 700)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.provider_var = tk.StringVar(value="Gemini")
        self.gemini_model_var = tk.StringVar(value=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))
        self.status_var = tk.StringVar(value="Loading scored rows...")
        self.only_deductions_var = tk.BooleanVar(value=True)
        self.attention_only_var = tk.BooleanVar(value=False)
        self.id_search_var = tk.StringVar(value="")
        self.cases: list[ReviewCase] = []
        self.visible_cases: list[ReviewCase] = []
        self.selected_vars: dict[tuple[str, str], tk.BooleanVar] = {}
        self.table_case_by_iid: dict[str, ReviewCase] = {}
        self.review_sort_column = "student_id"
        self.review_sort_descending = False
        self.current_case: ReviewCase | None = None
        self.review_running = False

        top = ctk.CTkFrame(self, corner_radius=8)
        top.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        top.grid_columnconfigure(7, weight=1)

        ctk.CTkLabel(top, text="LLM Provider:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.provider_menu = ctk.CTkOptionMenu(
            top,
            values=[FAKE_PROVIDER_LABEL, "Gemini"],
            variable=self.provider_var,
            command=lambda _value: self.update_gemini_key_status(),
        )
        self.provider_menu.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(top, text="Gemini model:").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self.model_menu = ctk.CTkOptionMenu(
            top,
            values=App.default_model_options(self.gemini_model_var.get()),
            variable=self.gemini_model_var,
        )
        self.model_menu.grid(row=0, column=3, padx=8, pady=8, sticky="ew")

        self.only_deductions_checkbox = ctk.CTkCheckBox(
            top,
            text="Show rows below 100 only",
            variable=self.only_deductions_var,
            command=self.render_table,
        )
        self.only_deductions_checkbox.grid(row=0, column=4, padx=8, pady=8, sticky="w")

        self.refresh_button = ctk.CTkButton(top, text="Refresh Rows", command=self.reload_cases)
        self.refresh_button.grid(row=0, column=5, padx=8, pady=8, sticky="ew")

        self.review_selected_button = ctk.CTkButton(top, text="Review Selected", command=self.review_selected)
        self.review_selected_button.grid(row=0, column=6, padx=8, pady=8, sticky="ew")

        ctk.CTkLabel(top, text="Search ID:").grid(row=1, column=0, padx=8, pady=(0, 8), sticky="w")
        self.id_search_entry = ctk.CTkEntry(
            top,
            textvariable=self.id_search_var,
            placeholder_text="student ID",
            width=180,
        )
        self.id_search_entry.grid(row=1, column=1, padx=8, pady=(0, 8), sticky="ew")
        self.id_search_var.trace_add("write", lambda *_args: self.render_table())
        self.clear_id_search_button = ctk.CTkButton(top, text="Clear Search", width=110, command=self.clear_id_search)
        self.clear_id_search_button.grid(row=1, column=2, padx=8, pady=(0, 8), sticky="w")

        self.attention_only_checkbox = ctk.CTkCheckBox(
            top,
            text="Attention needed only",
            variable=self.attention_only_var,
            command=self.render_table,
        )
        self.attention_only_checkbox.grid(row=1, column=3, columnspan=2, padx=8, pady=(0, 8), sticky="w")

        self.key_status_label = ctk.CTkLabel(top, text="", anchor="w", justify="left")
        self.key_status_label.grid(row=2, column=0, columnspan=8, padx=8, pady=(0, 8), sticky="ew")

        self.status_label = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w", justify="left")
        self.status_label.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        body = ctk.CTkFrame(self, corner_radius=8)
        body.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=0)
        body.grid_rowconfigure(1, weight=1)

        self.table_frame = ctk.CTkFrame(body, corner_radius=6)
        self.table_frame.grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        self.table_frame.grid_columnconfigure(0, weight=1)
        self.table_style = ttk.Style(self)
        self.configure_review_tree_style()
        self.review_tree = ttk.Treeview(
            self.table_frame,
            columns=("student_id", "question", "score", "final", "status", "notes"),
            show="headings",
            selectmode="extended",
            height=5,
            style=REVIEW_TREE_STYLE,
        )
        self.configure_review_tree_headings()
        self.review_tree.column("student_id", width=120, stretch=False, anchor="w")
        self.review_tree.column("question", width=80, stretch=False, anchor="w")
        self.review_tree.column("score", width=70, stretch=False, anchor="w")
        self.review_tree.column("final", width=70, stretch=False, anchor="w")
        self.review_tree.column("status", width=110, stretch=False, anchor="w")
        self.review_tree.column("notes", width=720, stretch=True, anchor="w")
        self.review_tree.grid(row=0, column=0, padx=(8, 0), pady=8, sticky="ew")
        self.review_tree.bind("<<TreeviewSelect>>", self.on_review_tree_select)
        self.review_tree.bind("<Double-1>", lambda _event: self.detail_tabview.set("Notes"))
        self.review_tree.bind("<Control-c>", self.copy_selected_student_ids)
        self.review_tree.bind("<Control-C>", self.copy_selected_student_ids)
        self.review_tree.tag_configure("original", foreground=COLORS["text_light"])
        self.review_tree.tag_configure("repaired", foreground=COLORS["accent"])
        self.review_tree.tag_configure("reviewed", foreground=COLORS["secondary"])
        self.review_scrollbar = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.review_tree.yview)
        self.review_scrollbar.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="ns")
        self.review_tree.configure(yscrollcommand=self.review_scrollbar.set)

        self.detail_tabview = ctk.CTkTabview(body, corner_radius=6)
        self.detail_tabview.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        for tab_name in ["Code", "Notes", "Review", "Failures", "Prompt"]:
            self.detail_tabview.add(tab_name)

        self.code_textbox = ctk.CTkTextbox(self.detail_tabview.tab("Code"), wrap="none")
        self.code_textbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._configure_code_tags()

        self.notes_textbox = ctk.CTkTextbox(self.detail_tabview.tab("Notes"), wrap="word")
        self.notes_textbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.review_textbox = ctk.CTkTextbox(self.detail_tabview.tab("Review"), wrap="word")
        self.review_textbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.review_textbox.tag_config("summary", foreground=COLORS["primary"])
        self.review_textbox.tag_config("warning", foreground=COLORS["warning"])
        self.review_textbox.tag_config("good", foreground=COLORS["secondary"])

        self.failures_textbox = ctk.CTkTextbox(self.detail_tabview.tab("Failures"), wrap="word")
        self.failures_textbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.prompt_textbox = ctk.CTkTextbox(self.detail_tabview.tab("Prompt"), wrap="word")
        self.prompt_textbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.update_gemini_key_status()
        self.reload_cases()

    def configure_review_tree_style(self):
        try:
            self.table_style.theme_use("clam")
        except tk.TclError:
            pass
        self.table_style.configure(
            REVIEW_TREE_STYLE,
            background="#1f1f1f",
            fieldbackground="#1f1f1f",
            foreground=COLORS["text_light"],
            bordercolor=COLORS["border"],
            lightcolor="#1f1f1f",
            darkcolor="#1f1f1f",
            rowheight=28,
            font=(UI_FONT_FAMILY, 10),
        )
        self.table_style.configure(
            REVIEW_TREE_HEADING_STYLE,
            background="#2c3e50",
            foreground=COLORS["text_light"],
            relief="flat",
            font=(UI_FONT_FAMILY, 10, "bold"),
        )
        self.table_style.map(
            REVIEW_TREE_STYLE,
            background=[("selected", COLORS["primary"])],
            foreground=[("selected", COLORS["text_light"])],
        )
        self.table_style.map(
            REVIEW_TREE_HEADING_STYLE,
            background=[("active", COLORS["primary"])],
            foreground=[("active", COLORS["text_light"])],
        )

    def configure_review_tree_headings(self):
        for column, label in self.review_tree_columns():
            self.review_tree.heading(
                column,
                text=self.review_heading_text(column, label),
                command=lambda selected_column=column: self.sort_review_table(selected_column),
            )

    @staticmethod
    def review_tree_columns():
        return [
            ("student_id", "Student ID"),
            ("question", "Question"),
            ("score", "Score"),
            ("final", "Final"),
            ("status", "Status"),
            ("notes", "Notes Preview"),
        ]

    def review_heading_text(self, column, label):
        if column != self.review_sort_column:
            return label
        arrow = "▼" if self.review_sort_descending else "▲"
        return f"{label} {arrow}"

    def show_on_top(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

    def close_window(self):
        self.parent.score_review_window = None
        self.destroy()

    def update_gemini_key_status(self):
        using_gemini = self.provider_var.get() == "Gemini"
        has_key = bool(get_google_api_key())
        if using_gemini and not has_key:
            self.key_status_label.configure(
                text=f"Gemini key is not configured. Choose {FAKE_PROVIDER_LABEL} for deterministic testing or set GOOGLE_API_KEY.",
                text_color=COLORS["warning"],
            )
            self.review_selected_button.configure(state="disabled")
        else:
            self.key_status_label.configure(
                text="Ready. Reviewed rows are locked and require deleting their review JSON to re-run.",
                text_color=COLORS["secondary"],
            )
            self.review_selected_button.configure(state="normal" if not self.review_running else "disabled")

    def reload_cases(self):
        try:
            self.cases = load_review_cases(self.parent.gui_questions, grading_policy=self.active_grading_policy())
        except Exception as exc:
            self.status_var.set(f"Could not load review rows: {exc}")
            self.cases = []
        self.selected_vars.clear()
        self.render_table()

    def clear_id_search(self):
        self.id_search_var.set("")

    def render_table(self):
        previous_key = self._case_identity(self.current_case) if self.current_case else None
        self.review_tree.delete(*self.review_tree.get_children())
        self.table_case_by_iid.clear()
        id_query = self.id_search_var.get().strip().lower()
        attention_threshold = self.attention_threshold()
        self.visible_cases = [
            case for case in self.cases
            if (not self.only_deductions_var.get() or case.question_score < 100 or case.notes)
            and (not self.attention_only_var.get() or self.is_attention_case(case, attention_threshold))
            and (not id_query or id_query in case.student_id.lower())
        ]
        self.visible_cases.sort(key=self.review_sort_key, reverse=self.review_sort_descending)
        self.configure_review_tree_headings()
        reviewed = sum(1 for case in self.visible_cases if case.reviewed)
        filters = []
        if id_query:
            filters.append(f"ID search '{self.id_search_var.get().strip()}'")
        if self.attention_only_var.get():
            filters.append("attention needed")
        filter_text = f" matching {', '.join(filters)}" if filters else ""
        self.status_var.set(
            f"Loaded {len(self.visible_cases)} row(s){filter_text}, {reviewed} already reviewed. "
            "Click a notes preview to open the full Notes tab."
        )

        selected_iid = self.populate_review_tree(previous_key)
        self.select_review_tree_item(selected_iid)

    def populate_review_tree(self, previous_key):
        self.review_tree.configure(height=max(2, min(8, len(self.visible_cases) + 1)))
        first_iid = ""
        preferred_iid = ""
        for row_index, case in enumerate(self.visible_cases):
            iid = f"review-{row_index}"
            first_iid = first_iid or iid
            preferred_iid = iid if self._case_identity(case) == previous_key else preferred_iid
            self.table_case_by_iid[iid] = case
            self.insert_review_tree_row(iid, case)
        self.review_tree.yview_moveto(0)
        return preferred_iid or first_iid

    def attention_threshold(self):
        grades_by_student = {}
        for case in self.cases:
            grades_by_student[case.student_id] = case.final_grade
        grades = sorted(float(grade) for grade in grades_by_student.values())
        if not grades:
            return 50
        middle = len(grades) // 2
        median = grades[middle] if len(grades) % 2 else (grades[middle - 1] + grades[middle]) / 2
        return median - 30

    @staticmethod
    def is_attention_case(case: ReviewCase, attention_threshold):
        return case.final_grade < 50 or case.final_grade <= attention_threshold

    def insert_review_tree_row(self, iid, case):
        status_text = "Reviewed" if case.reviewed else case.code_source.title()
        tag = "reviewed" if case.reviewed else case.code_source
        self.review_tree.insert(
            "",
            "end",
            iid=iid,
            tags=(tag,),
            values=(
                case.student_id,
                case.question,
                f"{case.question_score:g}",
                f"{case.final_grade:g}",
                status_text,
                self._shorten(case.notes or case.grade_text, 120),
            ),
        )

    def select_review_tree_item(self, selected_iid):
        if not selected_iid:
            self.current_case = None
            self.clear_detail()
            return
        self.review_tree.selection_set(selected_iid)
        self.review_tree.focus(selected_iid)
        self.review_tree.see(selected_iid)
        self.show_case(self.table_case_by_iid[selected_iid])

    @staticmethod
    def _case_sort_key(case: ReviewCase):
        return (PostScoringReviewWindow._natural_sort_key(case.student_id), case.question)

    def sort_review_table(self, column):
        if self.review_sort_column == column:
            self.review_sort_descending = not self.review_sort_descending
        else:
            self.review_sort_column = column
            self.review_sort_descending = False
        self.render_table()

    def review_sort_key(self, case: ReviewCase):
        values = {
            "student_id": self._natural_sort_key(case.student_id),
            "question": self._natural_sort_key(case.question),
            "score": case.question_score,
            "final": case.final_grade,
            "status": "Reviewed" if case.reviewed else case.code_source.title(),
            "notes": (case.notes or case.grade_text).lower(),
        }
        return (values.get(self.review_sort_column), self._case_sort_key(case))

    @staticmethod
    def _natural_sort_key(value: str):
        return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value))

    @staticmethod
    def _case_identity(case: ReviewCase | None):
        if not case:
            return None
        return (case.question, case.student_id)

    def selected_review_cases(self):
        return [
            self.table_case_by_iid[iid]
            for iid in self.review_tree.selection()
            if iid in self.table_case_by_iid
        ]

    def on_review_tree_select(self, _event=None):
        selected = self.selected_review_cases()
        if selected:
            self.show_case(selected[0])

    def copy_selected_student_ids(self, _event=None):
        student_ids = []
        for case in self.selected_review_cases():
            if case.student_id not in student_ids:
                student_ids.append(case.student_id)
        if not student_ids:
            return None
        self.clipboard_clear()
        self.clipboard_append("\n".join(student_ids))
        suffix = "s" if len(student_ids) != 1 else ""
        self.status_var.set(f"Copied {len(student_ids)} student ID{suffix}.")
        return "break"

    def review_selected(self):
        if self.review_running:
            return
        selected = [case for case in self.selected_review_cases() if not case.reviewed]
        if not selected:
            messagebox.showinfo("No Rows Selected", "Select one or more unlocked rows to review.")
            return
        try:
            provider = self.make_provider()
        except Exception as exc:
            messagebox.showerror("LLM Setup Error", str(exc))
            return
        self.review_running = True
        self.review_selected_button.configure(state="disabled")
        self.status_var.set(f"Reviewing {len(selected)} selected row(s)...")
        threading.Thread(target=self._review_worker, args=(selected, provider), daemon=True).start()

    def _review_worker(self, selected: list[ReviewCase], provider):
        try:
            review_cases_with_llm(selected, provider, max_workers=2, progress_callback=self._review_progress)
            self.after(0, self._review_finished)
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self._review_failed(captured_exc))

    def _review_progress(self, result, done, total):
        self.after(0, lambda: self.status_var.set(f"Reviewed {done}/{total}: {result.question} {result.anonymized_label}"))

    def _review_finished(self):
        self.review_running = False
        self.reload_cases()
        self.update_gemini_key_status()
        self.status_var.set("Review complete. Reviewed rows are now locked.")

    def _review_failed(self, exc):
        self.review_running = False
        self.update_gemini_key_status()
        self.status_var.set(f"Review failed: {exc}")
        messagebox.showerror("Review Failed", str(exc))

    def make_provider(self):
        if self.provider_var.get() == FAKE_PROVIDER_LABEL:
            return FakeLLMProvider()
        if not get_google_api_key():
            raise ValueError(f"GOOGLE_API_KEY is not set. Choose {FAKE_PROVIDER_LABEL} or configure Gemini first.")
        return GeminiProvider(model=self.gemini_model_var.get() or None)

    def active_grading_policy(self):
        policy = default_grading_policy()
        policy["test_case_scoring"]["mode"] = self.parent.gui_test_scoring_mode
        policy["test_case_scoring"]["deduction_per_failed_input"] = self.parent.gui_test_error_deduction
        policy["test_case_scoring"]["per_error_deduction_formula"] = (
            f"max(0, 100 - {self.parent.gui_test_error_deduction:g} * failed_tests) "
            "when mode is per_error_deduction"
        )
        policy["submission_error_penalty"]["points_per_error"] = self.parent.gui_penalty
        policy["submission_error_penalty"]["mode"] = (
            "cumulative_per_error" if self.parent.gui_per_error_penalty else "once_per_student"
        )
        policy["compile_repair"]["enabled"] = self.parent.gui_llm_compile_repair_enabled
        policy["compile_repair"]["penalty_after_successful_repair"] = self.parent.gui_llm_compile_repair_penalty
        policy["compile_repair"]["max_attempts"] = self.parent.gui_llm_compile_repair_max_attempts
        return policy

    def show_case(self, case: ReviewCase, show_notes=False):
        self.current_case = case
        self._set_text(self.code_textbox, self._numbered_code(case.code_text))
        self._highlight_code(case.code_text)
        self._set_text(self.notes_textbox, self._format_notes(case))
        self._set_text(self.failures_textbox, self._format_failures(case))
        self._set_text(self.prompt_textbox, build_score_review_prompt(case))
        saved_response = (case.saved_review or {}).get("response") if case.saved_review else None
        self._set_text(self.review_textbox, self._format_review(saved_response, case))
        if show_notes:
            self.detail_tabview.set("Notes")

    def clear_detail(self):
        for textbox in [self.code_textbox, self.notes_textbox, self.review_textbox, self.failures_textbox, self.prompt_textbox]:
            self._set_text(textbox, "")

    def _format_notes(self, case: ReviewCase) -> str:
        sections = [
            f"Question: {case.question}",
            f"Student label: {case.anonymized_label}",
            f"Question score: {case.question_score:g}",
            f"Final grade: {case.final_grade:g}",
            f"Code source: {case.code_source}",
            "",
            "Final Excel notes/comments:",
            case.notes or "(no final comments)",
            "",
            "Per-question Excel fields:",
            json.dumps(case.excel_fields, indent=2, ensure_ascii=False, default=str),
            "",
            "Final Excel fields:",
            json.dumps(case.final_fields, indent=2, ensure_ascii=False, default=str),
        ]
        if case.saved_review:
            sections.extend(["", "Saved review JSON:", json.dumps(case.saved_review, indent=2, ensure_ascii=False, default=str)])
        return "\n".join(sections)

    def _format_review(self, response: dict | None, case: ReviewCase) -> str:
        if not response:
            return (
                f"{case.question} {case.anonymized_label}\n"
                f"Score: {case.question_score:g}, Final: {case.final_grade:g}\n"
                f"Code source: {case.code_source}\n\n"
                "Select this row and click Review Selected to ask the LLM for an explanation."
            )
        lines = [
            f"{case.question} {case.anonymized_label}",
            f"Deduction plausible: {response.get('deduction_is_plausible')}",
            "",
            "Summary:",
            str(response.get("summary", "")),
            "",
            "Root causes:",
        ]
        for cause in response.get("root_causes", []) or []:
            lines.append(f"- {cause.get('issue', '')}")
            lines.append(f"  Inputs: {', '.join(map(str, cause.get('failed_inputs', []) or []))}")
            lines.append(f"  Impact: {cause.get('deduction_impact', '')}")
        lines.extend(["", "Inline comments:"])
        for comment in response.get("inline_comments", []) or []:
            line = comment.get("line")
            prefix = f"Line {line}: " if line else ""
            lines.append(f"- {prefix}{comment.get('comment', '')}")
        lines.extend(["", "Fix to full score:", str(response.get("fix_to_full_score", ""))])
        if response.get("risk_note"):
            lines.extend(["", "Risk note:", str(response.get("risk_note", ""))])
        return "\n".join(lines)

    def _format_failures(self, case: ReviewCase) -> str:
        lines = [
            f"Question: {case.question}",
            f"Score: {case.question_score:g}",
            f"Notes: {case.notes}",
            f"Code source: {case.code_source}",
            f"Code path: {case.code_path}",
            "",
        ]
        if case.repair_metadata:
            lines.extend(["Repair metadata:", json.dumps(case.repair_metadata, indent=2, ensure_ascii=False), ""])
        if not case.failed_cases:
            lines.append("No parsed discrepancy blocks were found in the grade text.")
        for index, failure in enumerate(case.failed_cases, start=1):
            lines.extend(
                [
                    f"Failed case {index}",
                    f"Input: {failure.input_value}",
                    f"Expected: {failure.expected_output}",
                    f"Actual: {failure.actual_output}",
                    f"Reason: {failure.reason}",
                    "",
                ]
            )
        if case.student_output_text:
            lines.extend(["Student output by input:", case.student_output_text, ""])
        if case.expected_output_text:
            lines.extend(["Expected/reference output by input:", case.expected_output_text, ""])
        lines.extend(["Raw grade text:", case.grade_text])
        return "\n".join(lines)

    def _configure_code_tags(self):
        self.code_textbox.tag_config("keyword", foreground=COLORS["primary"])
        self.code_textbox.tag_config("name", foreground=COLORS["text_dark"])
        self.code_textbox.tag_config("comment", foreground=COLORS["secondary"])
        self.code_textbox.tag_config("string", foreground=COLORS["warning"])
        self.code_textbox.tag_config("number", foreground=COLORS["accent"])

    def _highlight_code(self, code: str):
        if lex and CLexer:
            self._highlight_code_with_pygments(code)
            return
        keywords = {"int", "return", "if", "else", "for", "while", "do", "void", "float", "double", "char", "include", "define"}
        lines = code.splitlines()
        for idx, line in enumerate(lines, start=1):
            comment_col = line.find("//")
            if comment_col >= 0:
                self.code_textbox.tag_add("comment", f"{idx}.{comment_col + 5}", f"{idx}.end")
            for match in re.finditer(r'"[^"]*"', line):
                self.code_textbox.tag_add("string", f"{idx}.{match.start() + 5}", f"{idx}.{match.end() + 5}")
            for match in re.finditer(r"\b[A-Za-z_]\w*\b", line):
                if match.group(0) in keywords:
                    self.code_textbox.tag_add("keyword", f"{idx}.{match.start() + 5}", f"{idx}.{match.end() + 5}")

    def _highlight_code_with_pygments(self, code: str):
        line = 1
        column = 5
        for token_type, value in lex(code, CLexer()):
            start_line, start_column = line, column
            for char in value:
                if char == "\n":
                    line += 1
                    column = 5
                else:
                    column += 1
            tag = self._pygments_tag(token_type)
            if tag and value:
                self.code_textbox.tag_add(tag, f"{start_line}.{start_column}", f"{line}.{column}")

    @staticmethod
    def _pygments_tag(token_type):
        if token_type in Keyword:
            return "keyword"
        if token_type in Comment:
            return "comment"
        if token_type in String:
            return "string"
        if token_type in Number:
            return "number"
        if token_type in Name:
            return "name"
        return None

    def _set_text(self, textbox, text: str):
        textbox.configure(state="normal")
        textbox.delete("1.0", tk.END)
        textbox.insert("1.0", text or "")
        textbox.configure(state="disabled")

    @staticmethod
    def _numbered_code(code: str) -> str:
        return "\n".join(f"{index:>3}: {line}" for index, line in enumerate(code.splitlines(), start=1))

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        compact = " ".join(str(text).split())
        return compact if len(compact) <= limit else compact[: limit - 3] + "..."


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
        self.grid_rowconfigure(4, weight=1)

        self.checker_config = load_checker_config(DEFAULT_CHECKER_CONFIG_PATH)
        self.latest_checker_test_status = {}
        self.assignment_path_var = tk.StringVar(value="")
        self.provider_var = tk.StringVar(value="Gemini")
        self.gemini_model_var = tk.StringVar(value=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))
        self.gemini_model_values = App.default_model_options(self.gemini_model_var.get())
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
            values=[FAKE_PROVIDER_LABEL, "Gemini"],
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
        self.auto_current_button = ctk.CTkButton(buttons, text="Auto Setup Current Question", command=self.auto_setup_current_question)
        self.auto_current_button.grid(row=2, column=0, columnspan=2, padx=8, pady=(0, 8), sticky="ew")
        self.auto_all_button = ctk.CTkButton(buttons, text="Auto Setup All Questions", command=self.auto_setup_all_questions)
        self.auto_all_button.grid(row=2, column=2, columnspan=3, padx=8, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(
            buttons,
            text=(
                "Recommended flow: Suggest, review/edit JSON, Test Draft, Save Checker, run grading, then Run Audit. "
                "Auto Setup does Suggest -> Test Draft -> Save, and runs Audit only when grade/Excel outputs already exist. "
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

        self.checker_state_frame = ctk.CTkFrame(self, corner_radius=8)
        self.checker_state_frame.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.checker_state_frame.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self, corner_radius=8)
        self.tabview.grid(row=4, column=0, padx=12, pady=(0, 12), sticky="nsew")
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
        self.status_label.grid(row=5, column=0, padx=12, pady=(0, 12), sticky="ew")

        self.load_question_config()
        self.show_available_checkers()
        self.update_gemini_key_status()
        self.refresh_checker_status_strip()

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

    def refresh_checker_status_strip(self):
        for child in self.checker_state_frame.winfo_children():
            child.destroy()
        self.checker_state_frame.grid_columnconfigure(0, weight=0)
        ctk.CTkLabel(
            self.checker_state_frame,
            text="Checker readiness:",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=(8, 6), pady=6, sticky="w")
        questions = self.parent.gui_questions or ["Q1"]
        for index, question in enumerate(questions, start=1):
            status_text, status_color = self.compact_checker_status_for_question(question)
            self.checker_state_frame.grid_columnconfigure(index, weight=0)
            ctk.CTkLabel(
                self.checker_state_frame,
                text=status_text,
                text_color=status_color,
                anchor="w",
                justify="left",
            ).grid(row=0, column=index, padx=6, pady=6, sticky="w")
        self.checker_state_frame.grid_columnconfigure(len(questions) + 1, weight=1)
        ctk.CTkLabel(
            self.checker_state_frame,
            text="Green=audited, yellow=needs audit, red=needs checker",
            text_color="gray",
            anchor="w",
            justify="left",
        ).grid(row=0, column=len(questions) + 1, padx=8, pady=6, sticky="e")

    def compact_checker_status_for_question(self, question):
        question_config = self.checker_config.get("questions", {}).get(question) or self.checker_config.get("questions", {}).get(question.upper())
        if not question_config:
            return f"{question}: needs checker", COLORS["danger"]
        metadata = question_config.get("metadata", {}) if isinstance(question_config, dict) else {}
        audit_status = metadata.get("audit_status", "not_run")
        test_status = metadata.get("test_status", "not_run")
        if audit_status == "passed":
            return f"{question}: audited", COLORS["secondary"]
        if audit_status == "partial":
            return f"{question}: audit partial", COLORS["warning"]
        if audit_status in {"flagged", "error"}:
            return f"{question}: audit {audit_status}", COLORS["danger"]
        if test_status == "passed":
            return f"{question}: needs audit", COLORS["warning"]
        return f"{question}: saved", COLORS["warning"]

    def checker_status_for_question(self, question):
        question_config = self.checker_config.get("questions", {}).get(question) or self.checker_config.get("questions", {}).get(question.upper())
        if not question_config:
            return f"{question}: checker not configured yet", COLORS["danger"]
        metadata = question_config.get("metadata", {}) if isinstance(question_config, dict) else {}
        checker_name = question_config.get("checker", "unknown")
        audit_status = metadata.get("audit_status", "not_run")
        test_status = metadata.get("test_status", "not_run")
        if audit_status == "passed":
            return f"{question}: audit passed, checker saved ({checker_name})", COLORS["secondary"]
        if audit_status == "partial":
            return f"{question}: audit partial; some LLM reviews errored but none flagged ({checker_name})", COLORS["warning"]
        if audit_status in {"flagged", "error"}:
            return f"{question}: audit {audit_status}; review checker before trusting scores ({checker_name})", COLORS["danger"]
        if test_status == "passed":
            return f"{question}: checker saved and draft tests passed; run grading/audit next ({checker_name})", COLORS["warning"]
        return f"{question}: checker saved; run Test Draft then Audit ({checker_name})", COLORS["warning"]

    def update_checker_metadata(self, question, **metadata_updates):
        question_config = self.checker_config.setdefault("questions", {}).setdefault(question, {"checker": "exact", "config": {}})
        metadata = question_config.setdefault("metadata", {})
        metadata.update(metadata_updates)
        save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)
        self.after(0, self.refresh_checker_status_strip)
        self.after(0, self.parent.update_setup_readiness_banner)

    def mark_checker_saved(self, question, question_config, test_status="not_run"):
        existing_metadata = {}
        existing_config = self.checker_config.get("questions", {}).get(question, {})
        if isinstance(existing_config, dict):
            existing_metadata = existing_config.get("metadata", {})
        saved_config = dict(question_config)
        saved_config["metadata"] = {
            **existing_metadata,
            "saved": True,
            "test_status": test_status,
            "audit_status": "not_run",
        }
        self.checker_config.setdefault("questions", {})[question] = saved_config
        save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)
        self.after(0, self.refresh_checker_status_strip)
        self.after(0, self.parent.update_setup_readiness_banner)

    def load_question_config(self):
        question = self.question_var.get()
        question_config = self.checker_config.get("questions", {}).get(question, {"checker": "exact", "config": {}})
        self.config_textbox.delete("1.0", tk.END)
        editable_config = {key: value for key, value in question_config.items() if key != "metadata"}
        self.config_textbox.insert("1.0", json.dumps(editable_config, indent=2, sort_keys=True))
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
        structural_errors = structural_requirements_errors(question_config)
        if structural_errors:
            messagebox.showerror("Structural Requirement Needs Input", "\n".join(structural_errors))
            self.set_status("Structural requirement needs a deduction before saving.")
            return
        question = self.question_var.get()
        test_status = self.latest_checker_test_status.get(question, "not_run")
        self.mark_checker_saved(question, question_config, test_status=test_status)
        next_step = "Run grading, then Run Audit." if test_status == "passed" else "Run Test Draft, then grading/audit."
        self.set_status(f"Saved checker for {question}. Next: {next_step}")
        messagebox.showinfo("Checker Saved", f"Saved checker config for {question}.")

    def suggest_with_llm(self):
        self.run_background("Suggesting checker...", self._suggest_with_llm_worker, "Preparing LLM suggestion")

    def test_checker(self):
        self.run_background("Testing checker...", self._test_checker_worker)

    def run_audit(self):
        self.run_background("Running sampled LLM audit...", self._run_audit_worker, "Preparing LLM audit")

    def auto_setup_current_question(self):
        self.run_background("Auto-setting checker for current question...", self._auto_setup_current_worker, "Preparing auto setup")

    def auto_setup_all_questions(self):
        self.run_background("Auto-setting checkers for all questions...", self._auto_setup_all_worker, "Preparing auto setup for all questions")

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
            tests_ok, warnings = self.evaluate_checker_test_rows(rows)
            self.latest_checker_test_status[question] = "passed" if tests_ok else "failed"
            if question in self.checker_config.get("questions", {}):
                self.update_checker_metadata(
                    question,
                    test_status=self.latest_checker_test_status[question],
                    audit_status="not_run",
                    test_warnings=warnings,
                )
            self.after(0, lambda: self.show_test_rows(rows))
            status = "passed" if tests_ok else "needs review"
            self.after(0, lambda: self.set_status(f"Checker test {status}: {len(rows)} rows"))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Checker Test Failed", captured_exc))

    def _run_audit_worker(self):
        try:
            provider = self.make_provider()
            self.after(0, lambda: self.set_llm_activity_step("Parsing assignment context for audit"))
            assignment_context = parse_assignment_context(self.assignment_path_var.get().strip() or None)
            self.ensure_grade_outputs_for_audit(self.parent.gui_questions)
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
            self.record_audit_results(results, overall)
            payload = {
                "overall": overall,
                "reviewed": len(results),
                "results": [result.__dict__ for result in results],
            }
            self.after(0, lambda: self.show_json_result(payload))
            self.after(0, lambda: self.set_status(f"Audit finished: {overall}"))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Audit Failed", captured_exc))

    def _auto_setup_current_worker(self):
        try:
            provider = self.make_provider()
            assignment_context = parse_assignment_context(self.assignment_path_var.get().strip() or None)
            question = self.question_var.get()
            result = self.auto_configure_question(question, provider, assignment_context, show_prompt=True)
            audit_summary = self.run_optional_audit([question], provider, assignment_context)
            payload = {"question_results": [self.serializable_auto_result(result)], "audit": audit_summary}
            self.after(0, lambda captured_result=result: self.apply_auto_config_result(captured_result))
            self.after(0, lambda captured_payload=payload: self.show_json_result(captured_payload))
            self.after(0, lambda: self.set_status(self.auto_setup_status_message([result], audit_summary)))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Auto Setup Failed", captured_exc))

    def _auto_setup_all_worker(self):
        try:
            provider = self.make_provider()
            assignment_context = parse_assignment_context(self.assignment_path_var.get().strip() or None)
            results = []
            for question in self.parent.gui_questions:
                self.after(0, lambda current_question=question: self.set_llm_activity_step(f"Auto setup for {current_question}"))
                try:
                    result = self.auto_configure_question(question, provider, assignment_context, show_prompt=not results)
                except Exception as exc:
                    result = self.failed_auto_config_result(question, exc)
                results.append(result)
            try:
                audit_summary = self.run_optional_audit(self.parent.gui_questions, provider, assignment_context)
            except Exception as exc:
                audit_summary = {
                    "status": "error",
                    "reason": str(exc),
                    "reviewed": 0,
                    "results": [],
                }
            payload = {
                "question_results": [self.serializable_auto_result(result) for result in results],
                "audit": audit_summary,
            }
            first_displayable = next((result for result in results if result["question_config"] or result["test_rows"]), None)
            if first_displayable:
                self.after(0, lambda captured_result=first_displayable: self.apply_auto_config_result(captured_result))
            self.after(0, lambda captured_payload=payload: self.show_json_result(captured_payload))
            self.after(0, lambda: self.set_status(self.auto_setup_status_message(results, audit_summary)))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Auto Setup All Failed", captured_exc))

    def auto_configure_question(self, question, provider, assignment_context, show_prompt=False):
        self.after(0, lambda: self.set_llm_activity_step(f"{question}: compiling reference and collecting examples"))
        original_code, inputs, expected_outputs = self.collect_question_context(question)
        focused_context = assignment_context_for_question(assignment_context, question)
        image_count = len(focused_context.images)
        self.after(0, lambda: self.set_llm_activity_step(f"{question}: building prompt with {image_count} assignment image(s)"))
        prompt = build_suggestion_prompt(
            question,
            original_code,
            inputs,
            expected_outputs,
            focused_context.text,
            focused_context.images,
        )
        if show_prompt:
            self.after(0, lambda captured_prompt=prompt: self.show_prompt(captured_prompt))
        self.after(0, lambda: self.set_llm_activity_step(f"{question}: waiting for Gemini suggestion"))
        suggestion = suggest_checker(
            question,
            original_code,
            inputs,
            expected_outputs,
            provider,
            focused_context.text,
            focused_context.images,
        )
        question_config = None
        rows = []
        tests_ok = False
        warnings = []
        saved = False
        if suggestion.status == "supported" and suggestion.checker:
            question_config = {"checker": suggestion.checker, "config": suggestion.config}
            if suggestion.structural_requirements:
                question_config["structural_requirements"] = suggestion.structural_requirements
            self.after(0, lambda: self.set_llm_activity_step(f"{question}: running deterministic checker tests"))
            rows = run_checker_tests(question_config, expected_outputs)
            tests_ok, warnings = self.evaluate_checker_test_rows(rows)
            structural_errors = structural_requirements_errors(question_config)
            warnings.extend(structural_errors)
            if tests_ok and not structural_errors:
                self.mark_checker_saved(question, question_config, test_status="passed")
                saved = True
        return {
            "question": question,
            "suggestion": suggestion,
            "question_config": question_config,
            "test_rows": rows,
            "tests_ok": tests_ok,
            "warnings": warnings,
            "saved": saved,
            "error": "",
        }

    @staticmethod
    def failed_auto_config_result(question, exc):
        return {
            "question": question,
            "suggestion": SuggestionResult(
                status="error",
                question=question,
                checker=None,
                config={},
                confidence=0.0,
                reason=str(exc),
            ),
            "question_config": None,
            "test_rows": [],
            "tests_ok": False,
            "warnings": [f"{question}: auto setup failed: {exc}"],
            "saved": False,
            "error": str(exc),
        }

    def evaluate_checker_test_rows(self, rows):
        required_rows = [row for row in rows if row["variant"] in {"exact", "prompted"}]
        wrong_rows = [row for row in rows if row["variant"] == "wrong"]
        tests_ok = bool(required_rows) and all(row["passed"] for row in required_rows)
        warnings = []
        if any(row["passed"] for row in wrong_rows):
            warnings.append("One or more synthetic wrong-output rows passed; review manually if this is unexpected.")
        return tests_ok, warnings

    def run_optional_audit(self, questions, provider, assignment_context):
        self.ensure_grade_outputs_for_audit(questions)
        self.after(0, lambda: self.set_llm_activity_step("Selecting representative graded students for audit"))
        cases = select_audit_cases(questions, max_cases=self.get_audit_size())
        if not cases:
            for question in questions:
                if question in self.checker_config.get("questions", {}):
                    self.update_checker_metadata(question, audit_status="skipped")
            return {
                "status": "skipped",
                "reason": "No audit cases found in generated grade/Excel outputs.",
                "reviewed": 0,
                "results": [],
            }
        focused_context = assignment_context_for_question(assignment_context, cases[0].question)
        sample_prompt = build_audit_prompt(
            cases[0],
            self.checker_config.get("questions", {}).get(cases[0].question, {}),
            focused_context.text,
            focused_context.images,
        )
        self.after(0, lambda captured_prompt=sample_prompt: self.show_prompt(captured_prompt))
        self.after(0, lambda captured_cases=cases: self.start_audit_display(captured_cases))
        self.after(0, lambda: self.set_llm_activity_step(f"Waiting for Gemini audit reviews ({len(cases)} call(s))"))
        results = audit_cases_with_llm(
            cases,
            self.checker_config.get("questions", {}),
            provider,
            assignment_context,
            max_workers=4,
            progress_callback=lambda result, done, total: self.after(0, lambda: self.add_audit_result(result, done, total)),
        )
        status = self.audit_overall_status(results)
        self.record_audit_results(results, status)
        return {
            "status": status,
            "reviewed": len(results),
            "results": [result.__dict__ for result in results],
        }

    def record_audit_results(self, results, overall_status):
        if not results:
            for question in self.parent.gui_questions:
                if question in self.checker_config.get("questions", {}):
                    self.update_checker_metadata(question, audit_status="skipped")
            return
        results_by_question = {}
        for result in results:
            results_by_question.setdefault(result.question, []).append(result)
        for question, question_results in results_by_question.items():
            if any(result.status == "flagged" for result in question_results):
                audit_status = "flagged"
            elif all(result.status == "passed" for result in question_results):
                audit_status = "passed"
            elif any(result.status == "passed" for result in question_results):
                audit_status = "partial"
            elif any(result.status == "error" for result in question_results):
                audit_status = "error"
            else:
                audit_status = "flagged"
            self.update_checker_metadata(
                question,
                audit_status=audit_status,
                audit_reviewed=len(question_results),
                audit_errors=sum(1 for result in question_results if result.status == "error"),
                audit_reasons=[result.reason for result in question_results],
            )

    def ensure_grade_outputs_for_audit(self, audit_questions):
        if self.has_grade_outputs(audit_questions):
            return

        self.after(0, lambda: self.set_llm_activity_step("No audit outputs found; running deterministic grading first"))
        config_errors = validate_config(self.parent.gui_questions, self.parent.gui_weights)
        if config_errors:
            raise RuntimeError(
                "Cannot run audit because grading configuration is invalid:\n"
                + "\n".join(f"- {error}" for error in config_errors)
            )

        run_tests(
            self.parent.gui_questions,
            scoring_mode=self.parent.gui_test_scoring_mode,
            deduction_per_error=self.parent.gui_test_error_deduction,
            llm_compile_repair_enabled=self.parent.gui_llm_compile_repair_enabled,
            llm_compile_repair_provider=self.parent.make_compile_repair_provider(),
            llm_compile_repair_penalty=self.parent.gui_llm_compile_repair_penalty,
            llm_compile_repair_max_attempts=self.parent.gui_llm_compile_repair_max_attempts,
            vs_path_override=self.parent.gui_vs_path,
        )
        self.after(0, lambda: self.set_llm_activity_step("Creating Excel files for audit sampling"))
        create_excels(
            self.parent.gui_questions,
            self.parent.gui_weights,
            self.parent.gui_penalty,
            slim=self.parent.slim_output_var.get(),
            per_error_penalty=self.parent.gui_per_error_penalty,
        )
        self.after(0, self.parent.update_excel_button_state)

    def has_grade_outputs(self, questions):
        return all(os.path.exists(os.path.join(question, f"{question}_grades_to_upload.xlsx")) for question in questions)

    def serializable_auto_result(self, result):
        suggestion = result["suggestion"]
        return {
            "question": result["question"],
            "suggestion": suggestion.__dict__,
            "question_config": result["question_config"],
            "tests_ok": result["tests_ok"],
            "warnings": result["warnings"],
            "saved": result["saved"],
            "error": result.get("error", ""),
            "test_rows": result["test_rows"],
        }

    def apply_auto_config_result(self, result):
        self.question_var.set(result["question"])
        if result["question_config"]:
            self.config_textbox.delete("1.0", tk.END)
            self.config_textbox.insert("1.0", json.dumps(result["question_config"], indent=2, sort_keys=True))
        if result["test_rows"]:
            self.show_test_rows(result["test_rows"])

    @staticmethod
    def auto_setup_status_message(results, audit_summary):
        saved_count = sum(1 for result in results if result["saved"])
        total = len(results)
        failed = [result["question"] for result in results if result.get("error")]
        audit_status = audit_summary.get("status", "not run")
        failed_text = f"; failed: {', '.join(failed)}" if failed else ""
        return f"Auto setup saved {saved_count}/{total} checker(s){failed_text}. Audit: {audit_status}"

    def collect_question_context(self, question):
        try:
            original_path = os.path.join(question, "original_sol.c")
            with open(original_path, "r", encoding="utf-8", errors="ignore") as original_file:
                original_code = original_file.read()
            inputs = read_inputs_from_file(question)[:8]
            setup_visual_studio_environment(self.parent.gui_vs_path)
            expected_outputs = get_ground_truth(question, inputs)
            return original_code, inputs, expected_outputs
        except Exception as exc:
            raise RuntimeError(f"{question}: failed to collect reference outputs: {exc}") from exc

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
        if suggestion.structural_requirements:
            question_config["structural_requirements"] = suggestion.structural_requirements
        self.config_textbox.delete("1.0", tk.END)
        self.config_textbox.insert("1.0", json.dumps(question_config, indent=2, sort_keys=True))
        self.show_json_result(suggestion.__dict__)
        structural_errors = structural_requirements_errors(question_config)
        if structural_errors:
            self.set_status(f"Suggested {suggestion.checker}; fill mandatory structural deduction before saving")
        else:
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