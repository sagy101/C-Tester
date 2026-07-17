import importlib.util
import queue
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
CODE_FONT_FAMILY = "Consolas"
CODE_BG = "#0f172a"
CODE_GUTTER_BG = "#111827"
CODE_FG = "#e5e7eb"
CODE_SELECTION_BG = "#264f78"
KEY_RELEASE_EVENT = "<KeyRelease>"
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
import tempfile
import difflib
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
from .process import run_tests, setup_visual_studio_environment, read_inputs_from_file, get_ground_truth, compile_file, run_executable
from .create_excel import create_excels
from .checker_assistant import (
    DEFAULT_GEMINI_MODEL,
    AuditResult,
    FakeLLMProvider,
    GeminiProvider,
    SuggestionResult,
    assignment_context_for_question,
    audit_cases_with_llm,
    available_checker_templates,
    build_audit_prompt,
    build_suggestion_prompt,
    complete_json_with_schema,
    corroborated_review_feedback_item,
    get_google_api_key,
    list_gemini_models,
    parse_assignment_context,
    refine_checker,
    review_feedback_test_rows,
    run_checker_tests,
    audit_population_records,
    load_audit_population,
    select_audit_cases,
    select_strict_audit_cases,
    suggest_checker,
)
from .post_scoring_review import (
    ReviewCase,
    build_score_review_prompt,
    load_review_cases,
    review_cases_with_llm,
    default_grading_policy,
)
from .workflow_status import (
    compute_workflow_status,
    review_cause_label,
    review_response_cause,
)
from .semantic_grading import (
    DEFAULT_CHECKER_CONFIG_PATH,
    checker_config_errors,
    compare_output,
    load_checker_config,
    save_checker_config,
)
from .checker_calibration import (
    SemanticAuditEvidence,
    anonymized_student_hashes,
    append_checker_version,
    candidate_preserves_audited_cases,
    checker_config_hash,
    editable_checker_config,
    evaluate_strict_population_confidence,
    validate_candidate_against_rows,
)
from .verification import (
    AUDIT_RUBRIC_VERSION,
    audit_metadata_is_current,
    editable_checker_hash,
    grade_population_evidence_fingerprint,
    latest_audit_evidence_mtime,
    stable_fingerprint,
    strict_confidence_metadata,
)
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
GEMINI_FALLBACK_MODELS = ("gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash")
REVIEW_FIX_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "fixed_code": {"type": "string"},
        "explanation": {"type": "string"},
        "changes_made": {"type": "array", "items": {"type": "string"}},
        "tests_to_run": {"type": "array", "items": {"type": "string"}},
        "risk_note": {"type": "string"},
    },
    "required": ["fixed_code", "explanation", "changes_made", "tests_to_run", "risk_note"],
}
MAX_CALIBRATION_ROUNDS = 5

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
        self.setup_status_frame.grid_rowconfigure((0, 1, 2), weight=0)

        self.workflow_title = ctk.CTkLabel(
            self.setup_status_frame,
            text="Grading workflow",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["primary"],
            anchor="w",
        )
        self.workflow_title.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self.workflow_steps_frame = ctk.CTkFrame(self.setup_status_frame, fg_color="transparent")
        self.workflow_steps_frame.grid(row=1, column=0, columnspan=3, padx=8, pady=(0, 4), sticky="ew")
        self.workflow_steps_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.workflow_step_buttons = {}
        self.workflow_step_details = {}
        for index, (step_id, title) in enumerate(
            (("setup", "1. Setup"), ("checker", "2. Checker"), ("grade", "3. Grade"), ("review", "4. Review"))
        ):
            card = ctk.CTkFrame(self.workflow_steps_frame, corner_radius=8, border_width=1, border_color=COLORS["border"])
            card.grid(row=0, column=index, padx=4, pady=4, sticky="nsew")
            card.grid_columnconfigure(0, weight=1)
            button = ctk.CTkButton(
                card,
                text=title,
                height=34,
                corner_radius=6,
                command=lambda selected=step_id: self.on_workflow_step_clicked(selected),
            )
            button.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="ew")
            detail = ctk.CTkLabel(
                card,
                text="…",
                anchor="w",
                justify="left",
                wraplength=180,
                font=ctk.CTkFont(size=11),
            )
            detail.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")
            self.workflow_step_buttons[step_id] = button
            self.workflow_step_details[step_id] = detail

        self.workflow_next_label = ctk.CTkLabel(
            self.setup_status_frame,
            text="Next: checking workflow…",
            anchor="w",
            justify="left",
            wraplength=900,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.workflow_next_label.grid(row=2, column=0, padx=12, pady=(0, 4), sticky="ew")

        # Keep legacy labels as hidden compatibility targets for older tests/tools.
        self.setup_status_label = ctk.CTkLabel(self.setup_status_frame, text="")
        self.checker_status_label = ctk.CTkLabel(self.setup_status_frame, text="")

        self.global_apply_config_button = ctk.CTkButton(
            self.setup_status_frame,
            text="Apply Config",
            command=self.apply_gui_configuration,
            width=140,
            height=30,
            corner_radius=6,
        )
        self.global_apply_config_button.grid(row=0, column=1, padx=(12, 6), pady=8, sticky="e")
        self.setup_assistant_button = ctk.CTkButton(
            self.setup_status_frame,
            text="Setup Assistant",
            command=self.open_setup_assistant,
            width=150,
            height=30,
            corner_radius=6,
        )
        self.setup_assistant_button.grid(row=0, column=2, padx=(6, 12), pady=8, sticky="e")
        self.setup_status_frame.bind("<Configure>", self._resize_setup_status_label)

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
        self.penalty_entry.bind(KEY_RELEASE_EVENT, lambda event: self.mark_config_dirty())

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
        self.test_error_deduction_entry.bind(KEY_RELEASE_EVENT, lambda event: self.mark_config_dirty())

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
        self.compile_repair_penalty_entry.bind(KEY_RELEASE_EVENT, lambda event: self.mark_config_dirty())
        ctk.CTkLabel(self.compile_repair_frame, text="Max attempts:").grid(row=1, column=2, padx=(0, 5), pady=3, sticky="w")
        self.compile_repair_attempts_entry = ctk.CTkEntry(self.compile_repair_frame, width=45, border_width=1)
        self.compile_repair_attempts_entry.grid(row=1, column=3, padx=(0, 10), pady=3, sticky="w")
        self.compile_repair_attempts_entry.bind(KEY_RELEASE_EVENT, lambda event: self.mark_config_dirty())
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
        self.vs_path_entry.bind(KEY_RELEASE_EVENT, lambda event: self.mark_vs_path_dirty())

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
        self.winrar_path_entry.bind(KEY_RELEASE_EVENT, lambda event: self.mark_winrar_path_dirty())

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
        self.update_setup_readiness_banner()

    def _resize_setup_status_label(self, event):
        wraplength = max(300, event.width - 330)
        if hasattr(self, "workflow_next_label"):
            self.workflow_next_label.configure(wraplength=wraplength)
        card_wrap = max(120, (event.width - 80) // 4 - 24)
        for detail in getattr(self, "workflow_step_details", {}).values():
            detail.configure(wraplength=card_wrap)

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
        if not hasattr(self, "workflow_next_label"):
            return
        readiness = self.get_setup_readiness()
        workflow = compute_workflow_status(
            self.gui_questions,
            setup_readiness=readiness,
            checker_config=load_checker_config(DEFAULT_CHECKER_CONFIG_PATH),
            final_grades_path="final_grades.xlsx",
            checker_config_path=DEFAULT_CHECKER_CONFIG_PATH,
        )
        status_colors = {
            "done": COLORS["secondary"],
            "ready": COLORS["primary"],
            "pending": "#7f8c8d",
            "stale": COLORS["warning"],
            "attention": COLORS["danger"],
        }
        status_labels = {
            "done": "Done",
            "ready": "Ready",
            "pending": "Pending",
            "stale": "Re-run",
            "attention": "Attention",
        }
        titles = {"setup": "1. Setup", "checker": "2. Checker", "grade": "3. Grade", "review": "4. Review"}
        next_step = workflow.get("next_step")
        for step_id, step in workflow["steps"].items():
            color = status_colors.get(step["status"], COLORS["primary"])
            label = status_labels.get(step["status"], step["status"])
            emphasize = step_id == next_step or step["status"] in {"attention", "stale"}
            self.workflow_step_buttons[step_id].configure(
                text=f"{titles[step_id]} · {label}",
                fg_color=color if emphasize else COLORS["dark_bg"],
                hover_color=COLORS["hover"],
                border_width=2 if step_id == next_step else 0,
                border_color=color,
            )
            self.workflow_step_details[step_id].configure(text=step["detail"], text_color=COLORS["text_light"])
        hint_color = status_colors.get(workflow["steps"][next_step]["status"], COLORS["primary"])
        self.workflow_next_label.configure(text=workflow["next_hint"], text_color=hint_color)
        self.setup_status_label.configure(
            text=f"Setup readiness: {workflow['steps']['setup']['status']}. {workflow['steps']['setup']['detail']}"
        )
        self.checker_status_label.configure(text=f"Checker audit: {self.checker_status_summary()}")

    def get_workflow_status(self):
        return compute_workflow_status(
            self.gui_questions,
            setup_readiness=self.get_setup_readiness(),
            checker_config=load_checker_config(DEFAULT_CHECKER_CONFIG_PATH),
            final_grades_path="final_grades.xlsx",
            checker_config_path=DEFAULT_CHECKER_CONFIG_PATH,
        )

    def on_workflow_step_clicked(self, step_id):
        if step_id == "setup":
            self.open_setup_assistant()
            return
        if step_id == "checker":
            self.open_checker_manager()
            return
        if step_id == "grade":
            status = self.get_workflow_status()["steps"]["grade"]["status"]
            if status == "pending":
                messagebox.showinfo(
                    "Grade Not Ready",
                    "Finish Setup and Checker calibration first, then click Grade again.",
                )
                return
            if status == "done":
                if messagebox.askyesno(
                    "Regrade All Students?",
                    "Grades already exist. Regrade all students with the current checker?",
                ):
                    self.start_grading()
                return
            self.start_grading()
            return
        if step_id == "review":
            self.open_post_scoring_review(attention_only=True)

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

    def open_checker_manager(self, question=None, review_feedback=None):
        existing_window = getattr(self, "checker_manager_window", None)
        if existing_window is not None and existing_window.winfo_exists():
            existing_window.show_on_top()
            if question or review_feedback:
                existing_window.apply_external_focus(question, review_feedback)
            return
        self.checker_manager_window = CheckerManagerWindow(
            self,
            initial_question=question,
            review_feedback=review_feedback,
        )
        self.checker_manager_window.show_on_top()

    def open_post_scoring_review(self, attention_only=False):
        existing_window = getattr(self, "score_review_window", None)
        if existing_window is not None and existing_window.winfo_exists():
            if attention_only:
                existing_window.attention_only_var.set(True)
                existing_window.render_table()
            existing_window.show_on_top()
            return
        if not os.path.exists("final_grades.xlsx"):
            messagebox.showwarning("No Final Grades", "Run grading first so final_grades.xlsx exists.")
            return
        self.score_review_window = PostScoringReviewWindow(self, attention_only=attention_only)
        self.score_review_window.show_on_top()

    def _add_config_row(self, question_name="", weight=""):
        """Adds a row of entry widgets and binds KeyRelease event."""
        row_index = len(self.config_rows)
        q_entry = ctk.CTkEntry(self.config_table_frame, border_width=1)
        q_entry.grid(row=row_index, column=0, padx=5, pady=3, sticky="ew")
        q_entry.insert(0, question_name)
        q_entry.bind(KEY_RELEASE_EVENT, lambda event: self.mark_config_dirty())

        w_entry = ctk.CTkEntry(self.config_table_frame, width=80, border_width=1)  # Fixed width for weight
        w_entry.grid(row=row_index, column=1, padx=5, pady=3, sticky="ew")
        w_entry.insert(0, str(weight))
        w_entry.bind(KEY_RELEASE_EVENT, lambda event: self.mark_config_dirty())

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

    def __init__(self, parent: App, attention_only: bool = False):
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
        self.attention_only_var = tk.BooleanVar(value=bool(attention_only))
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

        self.review_attention_button = ctk.CTkButton(
            top,
            text="Review All Attention Needed",
            command=self.review_all_attention_needed,
            fg_color=COLORS["accent"],
            hover_color=("#8649a3", "#61347a"),
        )
        self.review_attention_button.grid(row=0, column=7, padx=8, pady=8, sticky="ew")

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
        self.attention_only_checkbox.grid(row=1, column=3, padx=8, pady=(0, 8), sticky="w")

        self.select_visible_button = ctk.CTkButton(top, text="Select Visible", width=120, command=self.select_visible_rows)
        self.select_visible_button.grid(row=1, column=4, padx=8, pady=(0, 8), sticky="w")

        self.recalibrate_button = ctk.CTkButton(
            top,
            text="Recalibrate From Reviews",
            command=self.recalibrate_from_reviews,
            fg_color=COLORS["warning"],
            hover_color=("#d68910", "#b9770e"),
            state="disabled",
        )
        self.recalibrate_button.grid(row=1, column=5, padx=8, pady=(0, 8), sticky="ew")

        self.open_lab_button = ctk.CTkButton(top, text="Open Review Lab", command=self.open_review_lab)
        self.open_lab_button.grid(row=1, column=6, columnspan=2, padx=8, pady=(0, 8), sticky="ew")

        self.key_status_label = ctk.CTkLabel(top, text="", anchor="w", justify="left")
        self.key_status_label.grid(row=2, column=0, columnspan=8, padx=8, pady=(0, 8), sticky="ew")

        self.feedback_banner = ctk.CTkLabel(
            top,
            text="",
            anchor="w",
            justify="left",
            wraplength=1100,
            text_color=COLORS["danger"],
        )
        self.feedback_banner.grid(row=3, column=0, columnspan=8, padx=8, pady=(0, 8), sticky="ew")
        self.feedback_banner.grid_remove()

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
            columns=("student_id", "question", "score", "final", "status", "cause", "notes"),
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
        self.review_tree.column("status", width=100, stretch=False, anchor="w")
        self.review_tree.column("cause", width=90, stretch=False, anchor="w")
        self.review_tree.column("notes", width=640, stretch=True, anchor="w")
        self.review_tree.grid(row=0, column=0, padx=(8, 0), pady=8, sticky="ew")
        self.review_tree.bind("<<TreeviewSelect>>", self.on_review_tree_select)
        self.review_tree.bind("<Double-1>", lambda _event: self.detail_tabview.set("Notes"))
        self.review_tree.bind("<Control-c>", self.copy_selected_student_ids)
        self.review_tree.bind("<Control-C>", self.copy_selected_student_ids)
        self.review_tree.bind("<Control-a>", self.select_visible_rows)
        self.review_tree.bind("<Control-A>", self.select_visible_rows)
        self.review_tree.tag_configure("original", foreground=COLORS["text_light"])
        self.review_tree.tag_configure("repaired", foreground=COLORS["accent"])
        self.review_tree.tag_configure("reviewed", foreground=COLORS["secondary"])
        self.review_tree.tag_configure("checker_or_app", foreground=COLORS["danger"])
        self.review_tree.tag_configure("unclear", foreground=COLORS["warning"])
        self.review_scrollbar = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.review_tree.yview)
        self.review_scrollbar.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="ns")
        self.review_tree.configure(yscrollcommand=self.review_scrollbar.set)

        self.detail_tabview = ctk.CTkTabview(body, corner_radius=6)
        self.detail_tabview.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        for tab_name in ["Code", "Reviewed Code", "Notes", "Review", "Failures", "Prompt"]:
            self.detail_tabview.add(tab_name)

        code_font = (CODE_FONT_FAMILY, 12)
        self.code_line_numbers, self.code_textbox, self.code_scrollbar, self.code_x_scrollbar = self._create_code_view(
            self.detail_tabview.tab("Code"),
            code_font,
        )
        self._configure_code_tags(self.code_textbox)

        (
            self.reviewed_code_line_numbers,
            self.reviewed_code_textbox,
            self.reviewed_code_scrollbar,
            self.reviewed_code_x_scrollbar,
        ) = self._create_code_view(self.detail_tabview.tab("Reviewed Code"), code_font)
        self._configure_code_tags(self.reviewed_code_textbox)
        self.reviewed_code_textbox.tag_config("review_header", foreground="#93c5fd")
        self.reviewed_code_textbox.tag_config("review_comment", foreground="#fde68a", background="#422006")

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
            ("cause", "Cause"),
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
            if hasattr(self, "review_attention_button"):
                self.review_attention_button.configure(state="disabled")
        else:
            self.key_status_label.configure(
                text="Ready. Current reviews are locked; stale evidence is automatically unlocked for re-review.",
                text_color=COLORS["secondary"],
            )
            enabled = "normal" if not self.review_running else "disabled"
            self.review_selected_button.configure(state=enabled)
            if hasattr(self, "review_attention_button"):
                self.review_attention_button.configure(state=enabled)

    def _create_code_view(self, tab, code_font):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        line_numbers = tk.Text(
            tab,
            width=5,
            padx=4,
            pady=6,
            wrap="none",
            state="disabled",
            takefocus=0,
            cursor="arrow",
            font=code_font,
            bg=CODE_GUTTER_BG,
            fg="#94a3b8",
            relief="flat",
            borderwidth=0,
        )
        line_numbers.grid(row=0, column=0, sticky="nsw", padx=(8, 0), pady=8)
        for event_name in ("<Button-1>", "<B1-Motion>", "<Control-c>", "<Control-C>"):
            line_numbers.bind(event_name, lambda _event: "break")

        code_textbox = tk.Text(
            tab,
            wrap="none",
            padx=4,
            pady=6,
            font=code_font,
            bg=CODE_BG,
            fg=CODE_FG,
            insertbackground=CODE_FG,
            selectbackground=CODE_SELECTION_BG,
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            undo=False,
            tabs=("4c",),
        )
        code_textbox.grid(row=0, column=1, sticky="nsew", pady=8)
        vertical_scrollbar = ttk.Scrollbar(
            tab,
            orient="vertical",
            command=lambda *args: self._scroll_code_view(code_textbox, line_numbers, *args),
        )
        vertical_scrollbar.grid(row=0, column=2, sticky="ns", padx=(0, 8), pady=8)
        horizontal_scrollbar = ttk.Scrollbar(tab, orient="horizontal", command=code_textbox.xview)
        horizontal_scrollbar.grid(row=1, column=1, sticky="ew", padx=(0, 0), pady=(0, 8))
        code_textbox.configure(
            yscrollcommand=lambda first, last: self._sync_code_line_numbers(
                vertical_scrollbar,
                line_numbers,
                first,
                last,
            ),
            xscrollcommand=horizontal_scrollbar.set,
        )
        return line_numbers, code_textbox, vertical_scrollbar, horizontal_scrollbar

    @staticmethod
    def _configure_diff_tags(textbox):
        textbox.tag_config("diff_header", foreground="#93c5fd")
        textbox.tag_config("diff_hunk", foreground="#c4b5fd")
        textbox.tag_config("diff_add", foreground="#bbf7d0", background="#14532d")
        textbox.tag_config("diff_remove", foreground="#fecaca", background="#7f1d1d")
        textbox.tag_config("diff_note", foreground="#fde68a")

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
            "Use Review All Attention Needed for the recommended one-click path."
        )

        selected_iid = self.populate_review_tree(previous_key)
        self.select_review_tree_item(selected_iid)
        self.refresh_feedback_banner()

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
        return median - 40

    @staticmethod
    def is_attention_case(case: ReviewCase, attention_threshold):
        return case.final_grade < 50 or case.final_grade <= attention_threshold

    def insert_review_tree_row(self, iid, case):
        cause = ""
        tag = case.code_source
        status_text = case.code_source.title()
        if case.reviewed:
            response = (case.saved_review or {}).get("response", {})
            cause_key = review_response_cause(response if isinstance(response, dict) else {})
            cause = review_cause_label(cause_key)
            status_text = "Reviewed"
            tag = cause_key if cause_key in {"checker_or_app", "unclear"} else "reviewed"
        elif case.stale_review:
            status_text = "Stale — re-review"
            tag = "unclear"
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
                cause,
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
        response = ((case.saved_review or {}).get("response") if case.reviewed else {}) or {}
        values = {
            "student_id": self._natural_sort_key(case.student_id),
            "question": self._natural_sort_key(case.question),
            "score": case.question_score,
            "final": case.final_grade,
            "status": (
                "Reviewed"
                if case.reviewed
                else ("Stale — re-review" if case.stale_review else case.code_source.title())
            ),
            "cause": review_cause_label(review_response_cause(response if isinstance(response, dict) else {})),
            "notes": (case.notes or case.grade_text or "").lower(),
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

    def select_visible_rows(self, _event=None):
        iids = list(self.review_tree.get_children())
        if not iids:
            self.status_var.set("No visible rows to select.")
            return "break"
        self.review_tree.selection_set(iids)
        self.review_tree.focus(iids[0])
        self.show_case(self.table_case_by_iid[iids[0]])
        self.status_var.set(f"Selected {len(iids)} visible row(s).")
        return "break"

    def attention_cases(self):
        threshold = self.attention_threshold()
        return [case for case in self.cases if self.is_attention_case(case, threshold)]

    def checker_defect_cases(self):
        defects = []
        for case in self.cases:
            if not case.reviewed:
                continue
            response = (case.saved_review or {}).get("response", {})
            feedback = dict(response) if isinstance(response, dict) else {}
            feedback["cause"] = review_response_cause(feedback)
            if corroborated_review_feedback_item(feedback):
                defects.append(case)
        return defects

    def refresh_feedback_banner(self):
        defects = self.checker_defect_cases()
        if not defects:
            self.feedback_banner.configure(text="")
            self.feedback_banner.grid_remove()
            self.recalibrate_button.configure(state="disabled")
            return
        questions = sorted({case.question for case in defects})
        self.feedback_banner.configure(
            text=(
                f"{len(defects)} review(s) blame the checker/app on {', '.join(questions)}. "
                "Click Recalibrate From Reviews, then regrade, then re-review attention rows."
            )
        )
        self.feedback_banner.grid()
        self.recalibrate_button.configure(state="normal")

    def review_all_attention_needed(self):
        if self.review_running:
            return
        self.attention_only_var.set(True)
        self.render_table()
        pending = [case for case in self.attention_cases() if not case.reviewed]
        if not pending:
            messagebox.showinfo(
                "Attention Review Complete",
                "Every attention-needed student already has a review.",
            )
            return
        # Select the pending attention rows that are currently visible.
        pending_keys = {self._case_identity(case) for case in pending}
        iids = [
            iid
            for iid, case in self.table_case_by_iid.items()
            if self._case_identity(case) in pending_keys
        ]
        if iids:
            self.review_tree.selection_set(iids)
            self.review_tree.focus(iids[0])
            self.show_case(self.table_case_by_iid[iids[0]])
        self._start_review(pending, label=f"attention-needed ({len(pending)})")

    def recalibrate_from_reviews(self):
        defects = self.checker_defect_cases()
        if not defects:
            messagebox.showinfo("No Checker Defects", "No reviews currently blame the checker or app.")
            return
        by_question: dict[str, list[dict]] = {}
        for case in defects:
            response = (case.saved_review or {}).get("response", {}) if case.saved_review else {}
            by_question.setdefault(case.question, []).append(
                {
                    "question": case.question,
                    "student_id": case.student_id,
                    "anonymized_label": case.anonymized_label,
                    "cause": "checker_or_app",
                    "summary": str(response.get("summary", "")),
                    "risk_note": str(response.get("risk_note", "")),
                    "semantic_assessment": str(response.get("semantic_assessment", "unclear")),
                    "format_requirement": str(response.get("format_requirement", "unclear")),
                    "format_requirement_evidence": str(response.get("format_requirement_evidence", "")),
                    "root_causes": response.get("root_causes", []),
                }
            )
        # Prefer the currently selected question if it has defects; otherwise the densest question.
        selected = self.selected_review_cases()
        question = None
        if selected and selected[0].question in by_question:
            question = selected[0].question
        else:
            question = max(by_question, key=lambda key: len(by_question[key]))
        findings = by_question[question]
        if not messagebox.askyesno(
            "Recalibrate Checker?",
            (
                f"{len(findings)} review(s) say {question}'s checker caused unjustified deductions.\n\n"
                "Open Checker Manager and run one-click calibration for this question using those findings?"
            ),
        ):
            return
        self.parent.open_checker_manager(question=question, review_feedback={question: findings})

    def review_selected(self):
        if self.review_running:
            return
        selected = [case for case in self.selected_review_cases() if not case.reviewed]
        if not selected:
            messagebox.showinfo("No Rows Selected", "Select one or more unlocked rows to review.")
            return
        self._start_review(selected, label=f"selected ({len(selected)})")

    def _start_review(self, selected, label):
        try:
            provider = self.make_provider()
        except Exception as exc:
            messagebox.showerror("LLM Setup Error", str(exc))
            return
        self.review_running = True
        self.review_selected_button.configure(state="disabled")
        self.review_attention_button.configure(state="disabled")
        self.status_var.set(f"Reviewing {label}...")
        threading.Thread(target=self._review_worker, args=(selected, provider), daemon=True).start()

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

    def open_review_lab(self):
        selected = self.selected_review_cases()
        if not selected:
            messagebox.showinfo("No Row Selected", "Select one review row first.")
            return
        ReviewLabWindow(self, selected[0]).show_on_top()

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
        self.review_selected_button.configure(state="normal")
        self.review_attention_button.configure(state="normal")
        self.reload_cases()
        self.update_gemini_key_status()
        defects = self.checker_defect_cases()
        if defects:
            self.status_var.set(
                f"Review complete. {len(defects)} review(s) blame the checker/app — use Recalibrate From Reviews."
            )
        else:
            self.status_var.set("Review complete. Reviewed rows are now locked.")
        self.parent.update_setup_readiness_banner()

    def _review_failed(self, exc):
        self.review_running = False
        self.review_selected_button.configure(state="normal")
        self.review_attention_button.configure(state="normal")
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
        saved_response = (case.saved_review or {}).get("response") if case.saved_review else None
        self._set_text(self.code_line_numbers, self._line_numbers(case.code_text))
        self._set_text(self.code_textbox, case.code_text)
        self.code_textbox.yview_moveto(0)
        self.code_line_numbers.yview_moveto(0)
        self._highlight_code(case.code_text)
        reviewed_code, review_comment_lines = self._format_reviewed_code(case, saved_response)
        self._set_text(self.reviewed_code_line_numbers, self._line_numbers(reviewed_code))
        self._set_text(self.reviewed_code_textbox, reviewed_code)
        self.reviewed_code_textbox.yview_moveto(0)
        self.reviewed_code_line_numbers.yview_moveto(0)
        self._highlight_code(reviewed_code, self.reviewed_code_textbox)
        self._tag_reviewed_code(review_comment_lines)
        self._set_text(self.notes_textbox, self._format_notes(case))
        self._set_text(self.failures_textbox, self._format_failures(case))
        self._set_text(self.prompt_textbox, build_score_review_prompt(case))
        self._set_text(self.review_textbox, self._format_review(saved_response, case))
        if show_notes:
            self.detail_tabview.set("Notes")

    def clear_detail(self):
        self._set_text(self.code_line_numbers, "")
        self._set_text(self.reviewed_code_line_numbers, "")
        for textbox in [self.code_textbox, self.reviewed_code_textbox, self.notes_textbox, self.review_textbox, self.failures_textbox, self.prompt_textbox]:
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
            f"Caused by: {review_cause_label(response.get('deduction_caused_by'))}",
            "",
            "Summary:",
            str(response.get("summary", "")),
            "",
            "Root causes:",
        ]
        lines.extend(self._format_review_root_causes(response.get("root_causes", []) or []))
        lines.extend(["", "Inline comments:"])
        lines.extend(self._format_inline_comments(response.get("inline_comments", []) or []))
        lines.extend(["", "Fix to full score:", str(response.get("fix_to_full_score", ""))])
        if response.get("risk_note"):
            lines.extend(["", "Risk note:", str(response.get("risk_note", ""))])
        return "\n".join(lines)

    def _format_review_root_causes(self, root_causes: list) -> list[str]:
        lines = []
        for cause in root_causes:
            if not isinstance(cause, dict):
                continue
            lines.append(f"- {cause.get('issue', '')}")
            lines.append(f"  Inputs: {', '.join(map(str, cause.get('failed_inputs', []) or []))}")
            lines.append(f"  Impact: {cause.get('deduction_impact', '')}")
            lines.extend(self._format_review_examples(cause.get("examples", []) or []))
        return lines

    @staticmethod
    def _format_review_examples(examples: list) -> list[str]:
        if not examples:
            return []
        lines = ["  Examples:"]
        for example in examples[:3]:
            if not isinstance(example, dict):
                continue
            lines.extend(
                [
                    f"    Input: {example.get('input', '')}",
                    f"    Expected: {example.get('expected_output', '')}",
                    f"    Actual: {example.get('actual_output', '')}",
                    f"    Why: {example.get('why_it_failed', '')}",
                ]
            )
        return lines

    @staticmethod
    def _format_inline_comments(inline_comments: list) -> list[str]:
        lines = []
        for comment in inline_comments:
            if not isinstance(comment, dict):
                continue
            line = comment.get("line")
            prefix = f"Line {line}: " if line else ""
            lines.append(f"- {prefix}{comment.get('comment', '')}")
        return lines

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

    def _format_reviewed_code(self, case: ReviewCase, response: dict | None) -> tuple[str, list[int]]:
        source_lines = case.code_text.splitlines()
        if not response:
            header = [
                f"// No saved LLM review yet for {case.question}.",
                "// Select the row and click Review Selected to generate inline comments.",
                "",
            ]
            return "\n".join(header + source_lines), [1, 2]

        comments_by_line, general_comments = self._split_inline_review_comments(response, len(source_lines))
        rendered = [f"// Reviewed for {case.question} only. Inline comments explain the deterministic deduction.", ""]
        comment_line_numbers = [1]
        for line_number, source_line in enumerate(source_lines, start=1):
            rendered.append(source_line)
            self._append_review_comments(rendered, comment_line_numbers, comments_by_line.get(line_number, []))

        if general_comments:
            rendered.extend(["", "// General reviewer comments:"])
            comment_line_numbers.append(len(rendered))
            self._append_review_comments(rendered, comment_line_numbers, general_comments)
        if not comments_by_line and not general_comments:
            rendered.extend(["", "// The reviewer did not return line-specific comments for this row."])
            comment_line_numbers.append(len(rendered))

        return "\n".join(rendered), comment_line_numbers

    def _split_inline_review_comments(self, response: dict, line_count: int) -> tuple[dict[int, list[str]], list[str]]:
        comments_by_line = {}
        general_comments = []
        for comment in response.get("inline_comments", []) or []:
            comment_text = self._inline_comment_text(comment)
            if not comment_text:
                continue
            line_number = self._inline_comment_line(comment)
            if 1 <= line_number <= line_count:
                comments_by_line.setdefault(line_number, []).append(comment_text)
            else:
                general_comments.append(comment_text)
        return comments_by_line, general_comments

    @staticmethod
    def _inline_comment_text(comment) -> str:
        return str(comment.get("comment", "")).strip() if isinstance(comment, dict) else ""

    @staticmethod
    def _inline_comment_line(comment) -> int:
        if not isinstance(comment, dict):
            return 0
        try:
            return int(comment.get("line"))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _append_review_comments(rendered: list[str], comment_line_numbers: list[int], comments: list[str]):
        for comment_text in comments:
            rendered.append(f"// REVIEWER COMMENT: {comment_text}")
            comment_line_numbers.append(len(rendered))

    def _tag_reviewed_code(self, comment_line_numbers: list[int]):
        self.reviewed_code_textbox.configure(state="normal")
        for line_number in comment_line_numbers:
            tag_name = "review_header" if line_number == 1 else "review_comment"
            self.reviewed_code_textbox.tag_add(tag_name, f"{line_number}.0", f"{line_number}.end")
        self.reviewed_code_textbox.configure(state="disabled")

    def _configure_code_tags(self, textbox):
        textbox.tag_config("keyword", foreground="#60a5fa")
        textbox.tag_config("name", foreground=CODE_FG)
        textbox.tag_config("comment", foreground="#6ee7b7")
        textbox.tag_config("string", foreground="#fca5a5")
        textbox.tag_config("number", foreground="#c4b5fd")

    def _highlight_code(self, code: str, textbox=None):
        textbox = textbox or self.code_textbox
        if lex and CLexer:
            self._highlight_code_with_pygments(code, textbox)
            return
        keywords = {"int", "return", "if", "else", "for", "while", "do", "void", "float", "double", "char", "include", "define"}
        lines = code.splitlines()
        for idx, line in enumerate(lines, start=1):
            comment_col = line.find("//")
            if comment_col >= 0:
                textbox.tag_add("comment", f"{idx}.{comment_col}", f"{idx}.end")
            for match in re.finditer(r'"[^"]*"', line):
                textbox.tag_add("string", f"{idx}.{match.start()}", f"{idx}.{match.end()}")
            for match in re.finditer(r"\b[A-Za-z_]\w*\b", line):
                if match.group(0) in keywords:
                    textbox.tag_add("keyword", f"{idx}.{match.start()}", f"{idx}.{match.end()}")

    def _highlight_code_with_pygments(self, code: str, textbox):
        line = 1
        column = 0
        for token_type, value in lex(code, CLexer()):
            start_line, start_column = line, column
            for char in value:
                if char == "\n":
                    line += 1
                    column = 0
                else:
                    column += 1
            tag = self._pygments_tag(token_type)
            if tag and value:
                textbox.tag_add(tag, f"{start_line}.{start_column}", f"{line}.{column}")

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
    def _line_numbers(code: str) -> str:
        return "\n".join(f"{index:>3}:" for index, _line in enumerate(code.splitlines(), start=1))

    @staticmethod
    def _scroll_code_view(textbox, line_numbers, *args):
        textbox.yview(*args)
        line_numbers.yview(*args)

    @staticmethod
    def _sync_code_line_numbers(scrollbar, line_numbers, first, last):
        scrollbar.set(first, last)
        line_numbers.yview_moveto(first)

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        compact = " ".join(str(text).split())
        return compact if len(compact) <= limit else compact[: limit - 3] + "..."


class ReviewLabWindow(ctk.CTkToplevel):
    """Interactive scratchpad for testing and iterating on one reviewed submission."""

    def __init__(self, review_window: PostScoringReviewWindow, case: ReviewCase):
        super().__init__(review_window)
        self.review_window = review_window
        self.parent_app = review_window.parent
        self.case = case
        self.original_code = case.code_text
        self.last_run_results: list[dict] = []
        self.last_fix_response: dict = {}
        self.title(f"Review Lab - {case.question} {case.anonymized_label}")
        self.geometry("1350x850")
        self.minsize(1100, 720)
        self.transient(review_window)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=8)
        header.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text=f"{case.question} {case.anonymized_label} | Score {case.question_score:g}, Final {case.final_grade:g}",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, padx=10, pady=8, sticky="ew")
        self.status_var = tk.StringVar(value="Edit code, choose inputs, then run or ask the LLM to apply the reviewer suggestion.")
        ctk.CTkLabel(header, textvariable=self.status_var, anchor="w", justify="left").grid(
            row=1, column=0, columnspan=2, padx=10, pady=(0, 8), sticky="ew"
        )
        phase_frame = ctk.CTkFrame(header, fg_color="transparent")
        phase_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 8), sticky="ew")
        phase_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.llm_phase_var = tk.StringVar(value="LLM: idle")
        self.compile_phase_var = tk.StringVar(value="Compile: idle")
        self.run_phase_var = tk.StringVar(value="Run: idle")
        for column, phase_var in enumerate((self.llm_phase_var, self.compile_phase_var, self.run_phase_var)):
            ctk.CTkLabel(phase_frame, textvariable=phase_var, anchor="w").grid(
                row=0, column=column, padx=(0, 12), pady=0, sticky="ew"
            )

        controls = ctk.CTkFrame(self, corner_radius=8)
        controls.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        controls.grid_columnconfigure(0, weight=1)
        self.input_textbox = ctk.CTkTextbox(controls, height=72, wrap="word")
        self.input_textbox.grid(row=0, column=0, rowspan=2, padx=8, pady=8, sticky="ew")
        self._set_text(self.input_textbox, self._default_input_text(), readonly=False)
        ctk.CTkButton(controls, text="Run Custom Input", command=self.run_custom_inputs).grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkButton(controls, text="Run All Grading Inputs", command=self.run_all_inputs).grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkButton(controls, text="Apply Suggested Fix", command=self.apply_suggested_fix).grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkButton(controls, text="Reset Code", command=self.reset_code).grid(row=0, column=4, padx=8, pady=8)
        ctk.CTkButton(controls, text="Re-highlight Code", command=self.refresh_code_view).grid(row=0, column=5, padx=8, pady=8)
        ctk.CTkLabel(
            controls,
            text="Custom input: one test case per line, matching input.txt format.",
            text_color="gray",
            anchor="w",
        ).grid(row=1, column=1, columnspan=5, padx=8, pady=(0, 8), sticky="ew")

        body = ctk.CTkFrame(self, corner_radius=8)
        body.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        body.grid_columnconfigure((0, 1), weight=1)
        body.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(body, text="Editable Student Code", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=8, pady=(8, 0), sticky="w"
        )
        ctk.CTkLabel(body, text="Run Results / Diff / Fix Notes", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=1, padx=8, pady=(8, 0), sticky="w"
        )
        self.code_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.code_frame.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        self.code_line_numbers, self.code_textbox, self.code_scrollbar, self.code_x_scrollbar = review_window._create_code_view(
            self.code_frame,
            (CODE_FONT_FAMILY, 12),
        )
        review_window._configure_code_tags(self.code_textbox)
        self.code_textbox.insert("1.0", case.code_text)
        self.refresh_code_view()
        self.code_textbox.bind(KEY_RELEASE_EVENT, lambda _event: self.refresh_code_view(debounce=True))

        self.result_tabs = ctk.CTkTabview(body, corner_radius=6)
        self.result_tabs.grid(row=1, column=1, padx=8, pady=8, sticky="nsew")
        for tab_name in ["Compare", "Code Diff", "Output Diff", "Fix Notes"]:
            self.result_tabs.add(tab_name)
        self._build_compare_tab()
        self.code_diff_textbox = self._create_diff_textbox(self.result_tabs.tab("Code Diff"))
        self.output_diff_textbox = self._create_diff_textbox(self.result_tabs.tab("Output Diff"))
        self.fix_notes_textbox = ctk.CTkTextbox(self.result_tabs.tab("Fix Notes"), wrap="word")
        self.fix_notes_textbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.show_code_diff(self.original_code, self.current_code())
        self._set_styled_diff(self.output_diff_textbox, "(run inputs to see output diffs)")
        self._set_text(self.fix_notes_textbox, "No LLM fix has been applied yet.")

    def _build_compare_tab(self):
        tab = self.result_tabs.tab("Compare")
        tab.grid_columnconfigure((0, 1), weight=1)
        tab.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(tab, text="Expected / Reference").grid(row=0, column=0, padx=8, pady=(8, 0), sticky="w")
        ctk.CTkLabel(tab, text="Student / Current Code").grid(row=0, column=1, padx=8, pady=(8, 0), sticky="w")
        self.expected_textbox = ctk.CTkTextbox(tab, wrap="word")
        self.expected_textbox.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        self.actual_textbox = ctk.CTkTextbox(tab, wrap="word")
        self.actual_textbox.grid(row=1, column=1, padx=8, pady=8, sticky="nsew")

    def _create_diff_textbox(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        textbox = tk.Text(
            tab,
            wrap="none",
            padx=8,
            pady=8,
            font=(CODE_FONT_FAMILY, 11),
            bg=CODE_BG,
            fg=CODE_FG,
            insertbackground=CODE_FG,
            selectbackground=CODE_SELECTION_BG,
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
        )
        textbox.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        vertical_scrollbar = ttk.Scrollbar(tab, orient="vertical", command=textbox.yview)
        vertical_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=(8, 0))
        horizontal_scrollbar = ttk.Scrollbar(tab, orient="horizontal", command=textbox.xview)
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        textbox.configure(yscrollcommand=vertical_scrollbar.set, xscrollcommand=horizontal_scrollbar.set)
        self.review_window._configure_diff_tags(textbox)
        return textbox

    def show_on_top(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def current_code(self) -> str:
        return self.code_textbox.get("1.0", tk.END).rstrip()

    def refresh_code_view(self, debounce=False):
        if debounce:
            if getattr(self, "_refresh_code_after_id", None):
                self.after_cancel(self._refresh_code_after_id)
            self._refresh_code_after_id = self.after(250, self.refresh_code_view)
            return
        self._set_text(self.code_line_numbers, self.review_window._line_numbers(self.current_code()))
        self._clear_code_tags(self.code_textbox)
        self.review_window._highlight_code(self.current_code(), self.code_textbox)
        self.show_code_diff(self.original_code, self.current_code())

    @staticmethod
    def _clear_code_tags(textbox):
        for tag_name in ("keyword", "name", "comment", "string", "number"):
            textbox.tag_remove(tag_name, "1.0", tk.END)

    def reset_code(self):
        self.code_textbox.delete("1.0", tk.END)
        self.code_textbox.insert("1.0", self.original_code)
        self.refresh_code_view()
        self.status_var.set("Code reset to the reviewed source.")
        self._set_phase_status(compile_status="idle", run_status="idle")

    def _set_phase_status(self, llm_status=None, compile_status=None, run_status=None):
        phase_updates = (
            ("llm_phase_var", "LLM", llm_status),
            ("compile_phase_var", "Compile", compile_status),
            ("run_phase_var", "Run", run_status),
        )
        for variable_name, label, status in phase_updates:
            if status is not None and hasattr(self, variable_name):
                getattr(self, variable_name).set(f"{label}: {status}")

    def _queue_phase_status(self, llm_status=None, compile_status=None, run_status=None):
        if not any(hasattr(self, variable_name) for variable_name in ("llm_phase_var", "compile_phase_var", "run_phase_var")):
            return
        after = getattr(self, "after", None)
        if callable(after):
            after(0, lambda: self._set_phase_status(llm_status, compile_status, run_status))
        else:
            self._set_phase_status(llm_status, compile_status, run_status)

    def _default_input_text(self) -> str:
        if self.case.failed_cases:
            return "\n".join(failure.input_value for failure in self.case.failed_cases[:5])
        return "\n".join(read_inputs_from_file(self.case.question)[:5])

    def custom_inputs(self) -> list[str]:
        return [line.strip() for line in self.input_textbox.get("1.0", tk.END).splitlines() if line.strip()]

    def run_custom_inputs(self):
        inputs = self.custom_inputs()
        if not inputs:
            messagebox.showinfo("No Input", "Enter at least one input line.")
            return
        self._run_inputs_async(inputs, "custom input")

    def run_all_inputs(self):
        inputs = read_inputs_from_file(self.case.question)
        if not inputs:
            messagebox.showwarning("No Inputs", f"No inputs found for {self.case.question}.")
            return
        self._run_inputs_async(inputs, "all grading inputs")

    def _run_inputs_async(self, inputs: list[str], label: str):
        self.status_var.set(f"Running {label}...")
        self._set_phase_status(compile_status="running", run_status="waiting")
        code_snapshot = self.current_code()
        threading.Thread(target=self._run_inputs_worker, args=(inputs, label, code_snapshot), daemon=True).start()

    def _run_inputs_worker(self, inputs: list[str], label: str, code_snapshot: str):
        try:
            results = self._compile_and_run_inputs(inputs, code_snapshot)
            self.after(0, lambda: self._show_run_results(results, label))
        except Exception as exc:
            self.after(0, lambda captured=exc: self._show_run_error(captured))

    def _compile_and_run_inputs(self, inputs: list[str], code_snapshot: str) -> list[dict]:
        setup_visual_studio_environment(self.parent_app.gui_vs_path)
        with tempfile.TemporaryDirectory(prefix="review_lab_", dir=os.getcwd()) as temp_dir:
            student_path = os.path.join(temp_dir, "student.c")
            reference_path = os.path.join(temp_dir, "original_sol.c")
            with open(student_path, "w", encoding="utf-8") as student_file:
                student_file.write(code_snapshot)
            shutil.copy2(os.path.join(self.case.question, "original_sol.c"), reference_path)

            student_exe, student_compile_error = compile_file(student_path)
            reference_exe, reference_compile_error = compile_file(reference_path)
            if student_compile_error or reference_compile_error:
                self._queue_phase_status(compile_status="failed", run_status="skipped")
                return [
                    {
                        "input": "(compile)",
                        "expected": reference_compile_error or "Reference compiled successfully.",
                        "actual": student_compile_error or "Student code compiled successfully.",
                        "passed": False,
                        "reason": "Compilation failed.",
                    }
                ]

            self._queue_phase_status(compile_status="passed", run_status="running")
            results = []
            for input_value in inputs:
                expected = run_executable(reference_exe, input_value)
                actual = run_executable(student_exe, input_value)
                comparison = compare_output(self.case.question, input_value, expected, actual)
                results.append(
                    {
                        "input": input_value,
                        "expected": expected,
                        "actual": actual,
                        "passed": comparison.passed,
                        "reason": comparison.reason,
                    }
                )
            passed_count = sum(1 for result in results if result.get("passed"))
            self._queue_phase_status(run_status=f"{passed_count}/{len(results)} passed")
            return results

    def _show_run_results(self, results: list[dict], label: str):
        self.last_run_results = results
        failed = [result for result in results if not result.get("passed")]
        compile_failed = any(result.get("input") == "(compile)" for result in results)
        self._set_phase_status(
            compile_status="failed" if compile_failed else "passed",
            run_status="skipped" if compile_failed else f"{len(results) - len(failed)}/{len(results)} passed",
        )
        self._set_text(self.expected_textbox, self._format_side_output(results, "expected"))
        self._set_text(self.actual_textbox, self._format_side_output(results, "actual"))
        self._set_styled_diff(self.output_diff_textbox, self._format_output_diff(results) or "(all compared outputs matched)")
        self.show_code_diff(self.original_code, self.current_code())
        if failed:
            self.status_var.set(f"Ran {label}: {len(failed)}/{len(results)} input(s) still fail. You can Apply Suggested Fix again.")
        else:
            self.status_var.set(f"Ran {label}: all {len(results)} input(s) passed.")

    def _show_run_error(self, exc: Exception):
        self.status_var.set(f"Run failed: {exc}")
        self._set_phase_status(compile_status="failed", run_status="failed")
        self._set_text(self.actual_textbox, f"Run failed:\n{exc}")

    @staticmethod
    def _format_side_output(results: list[dict], key: str) -> str:
        sections = []
        for result in results:
            status = "PASS" if result.get("passed") else "FAIL"
            sections.append(f"[{status}] Input: {result.get('input', '')}\n{result.get(key, '')}")
            if key == "actual" and result.get("reason"):
                sections.append(f"Reason: {result.get('reason')}")
        return "\n\n".join(sections)

    @staticmethod
    def _format_output_diff(results: list[dict]) -> str:
        chunks = []
        for result in results:
            if result.get("passed"):
                continue
            diff = difflib.unified_diff(
                str(result.get("expected", "")).splitlines(),
                str(result.get("actual", "")).splitlines(),
                fromfile=f"expected input {result.get('input', '')}",
                tofile=f"student input {result.get('input', '')}",
                lineterm="",
            )
            chunks.extend(diff)
            if result.get("reason"):
                chunks.append(f"# Reason: {result.get('reason')}")
            chunks.append("")
        return "\n".join(chunks)

    @staticmethod
    def _unified_diff(before: str, after: str) -> str:
        return "\n".join(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile="before.c",
                tofile="after.c",
                lineterm="",
            )
        ) or "(no code changes)"

    def show_code_diff(self, before: str, after: str):
        self._set_styled_diff(self.code_diff_textbox, self._unified_diff(before, after))

    @staticmethod
    def _set_styled_diff(textbox, diff_text: str):
        textbox.configure(state="normal")
        textbox.delete("1.0", tk.END)
        for line in (diff_text or "").splitlines() or [""]:
            tag = ReviewLabWindow._diff_tag_for_line(line)
            start = textbox.index(tk.END)
            textbox.insert(tk.END, line + "\n")
            if tag:
                textbox.tag_add(tag, start, textbox.index(f"{start} lineend"))
        textbox.configure(state="disabled")

    @staticmethod
    def _diff_tag_for_line(line: str) -> str:
        if line.startswith(("---", "+++")):
            return "diff_header"
        if line.startswith("@@"):
            return "diff_hunk"
        if line.startswith("+"):
            return "diff_add"
        if line.startswith("-"):
            return "diff_remove"
        if line.startswith("#"):
            return "diff_note"
        return ""

    def apply_suggested_fix(self):
        try:
            provider = self.review_window.make_provider()
        except Exception as exc:
            messagebox.showerror("LLM Setup Error", str(exc))
            return
        self.status_var.set("Asking LLM to apply the reviewer suggestion...")
        self._set_phase_status(llm_status="running", compile_status="idle", run_status="idle")
        threading.Thread(target=self._fix_worker, args=(provider,), daemon=True).start()

    def _fix_worker(self, provider):
        before_code = self.current_code()
        try:
            prompt = json.dumps(self._fix_prompt_payload(before_code), indent=2, ensure_ascii=False, default=str)
            response = complete_json_with_schema(provider, prompt, None, REVIEW_FIX_RESPONSE_SCHEMA)
            fixed_code = str(response.get("fixed_code", "")).strip()
            if not fixed_code:
                raise ValueError("LLM did not return fixed_code.")
            self.after(0, lambda: self._apply_fix_response(before_code, fixed_code, response))
        except Exception as exc:
            self.after(0, lambda captured=exc: self._show_fix_error(captured))

    def _fix_prompt_payload(self, current_code: str) -> dict:
        review_response = (self.case.saved_review or {}).get("response") if self.case.saved_review else {}
        remaining_failures = [result for result in self.last_run_results if not result.get("passed")]
        return {
            "task": "apply_review_fix",
            "question": self.case.question,
            "scope": (
                f"Fix only behavior for {self.case.question}. The file may contain multiple homework questions; "
                "preserve unrelated question behavior unless shared code directly affects this question."
            ),
            "instructions": (
                "Return the full corrected C file. Make the smallest edit set that passes all known inputs for this question. "
                "Do not perform style cleanup, refactors, rewrites, or unrelated fixes. Preserve names, formatting, prompts, and "
                "other question behavior unless a change is required for this question to pass. Add clear comments near changed code "
                "using the phrase REVIEWER FIX, explaining what changed and which failed behavior it addresses. "
                "Do not delete unrelated student code. The UI shows a before/after diff, so do not comment out large old blocks."
            ),
            "current_code": current_code,
            "original_reviewed_code": self.original_code,
            "reviewer_output": review_response,
            "deterministic_failed_cases": [failure.__dict__ for failure in self.case.failed_cases],
            "remaining_failures_after_last_run": remaining_failures,
            "grading_policy": self.case.grading_policy,
        }

    def _apply_fix_response(self, before_code: str, fixed_code: str, response: dict):
        self.last_fix_response = response
        self.code_textbox.delete("1.0", tk.END)
        self.code_textbox.insert("1.0", fixed_code)
        self.refresh_code_view()
        self.show_code_diff(before_code, fixed_code)
        self._set_text(self.fix_notes_textbox, self._format_fix_notes(response))
        self.status_var.set("LLM fix inserted into the lab. Running all grading inputs...")
        self._set_phase_status(llm_status="done", compile_status="running", run_status="waiting")
        self.run_all_inputs()

    def _show_fix_error(self, exc: Exception):
        self.status_var.set(f"LLM fix failed: {exc}")
        self._set_phase_status(llm_status="failed")
        self._set_text(self.fix_notes_textbox, f"LLM fix failed:\n{exc}")

    @staticmethod
    def _format_fix_notes(response: dict) -> str:
        lines = [
            "Explanation:",
            str(response.get("explanation", "")),
            "",
            "Changes made:",
        ]
        lines.extend(f"- {change}" for change in response.get("changes_made", []) or [])
        lines.extend(["", "Suggested tests:"])
        lines.extend(f"- {test}" for test in response.get("tests_to_run", []) or [])
        if response.get("risk_note"):
            lines.extend(["", "Risk note:", str(response.get("risk_note", ""))])
        return "\n".join(lines)

    @staticmethod
    def _set_text(textbox, text: str, readonly=True):
        textbox.configure(state="normal")
        textbox.delete("1.0", tk.END)
        textbox.insert("1.0", text or "")
        if readonly:
            textbox.configure(state="disabled")


class CheckerManagerWindow(ctk.CTkToplevel):
    def __init__(self, parent: App, initial_question=None, review_feedback=None):
        super().__init__(parent)
        self._ui_queue = queue.Queue()
        self._closing = False
        self._background_running = False
        self._worker_snapshot = {}
        self.pending_review_feedback = dict(review_feedback or {})
        super().after(50, self._drain_ui_queue)
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
        self.latest_checker_test_hash = {}
        self.assignment_path_var = tk.StringVar(value="")
        self._initial_question = initial_question
        self.provider_var = tk.StringVar(value="Gemini")
        self.gemini_model_var = tk.StringVar(value=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))
        self.gemini_model_values = App.default_model_options(self.gemini_model_var.get())
        self.audit_size_var = tk.StringVar(value="15")
        self.question_var = tk.StringVar(value=parent.gui_questions[0] if parent.gui_questions else "Q1")

        top = self.checker_setup_frame = ctk.CTkFrame(self, corner_radius=8)
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

        buttons = self.checker_actions_frame = ctk.CTkFrame(self, corner_radius=8)
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
        self.auto_current_button = ctk.CTkButton(
            buttons,
            text="One-click Calibrate Current Question",
            command=self.auto_setup_current_question,
        )
        self.auto_current_button.grid(row=2, column=0, columnspan=2, padx=8, pady=(0, 8), sticky="ew")
        self.auto_all_button = ctk.CTkButton(
            buttons,
            text="One-click Calibrate All Questions",
            command=self.auto_setup_all_questions,
        )
        self.auto_all_button.grid(row=2, column=2, columnspan=2, padx=8, pady=(0, 8), sticky="ew")
        self.rollback_checker_button = ctk.CTkButton(
            buttons,
            text="Rollback Version",
            command=self.rollback_current_checker,
        )
        self.rollback_checker_button.grid(row=2, column=4, padx=8, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(
            buttons,
            text=(
                "Recommended flow: Suggest, review/edit JSON, Test Draft, Save Checker, run grading, then Run Audit. "
                "One-click calibration does Suggest -> deterministic mutation tests -> Save -> Grade -> up to 3 "
                "stratified Audit/Improve rounds with cumulative no-regression gates; it may regrade every student "
                "and make up to 45 audit LLM calls plus suggestions per question at the default sample size. "
                "The assignment file is optional LLM context, not an audit folder."
            ),
            text_color="gray",
            anchor="w",
            justify="left",
            wraplength=950,
        ).grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 8), sticky="ew")

        activity_frame = self.checker_activity_frame = ctk.CTkFrame(self, corner_radius=8)
        activity_frame.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="ew")
        activity_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(activity_frame, text="LLM activity:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.llm_activity_label = ctk.CTkLabel(activity_frame, text="Idle", anchor="w")
        self.llm_activity_label.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        self.llm_activity_progress = ctk.CTkProgressBar(activity_frame, mode="indeterminate", height=8)
        self.llm_activity_progress.grid(row=1, column=0, columnspan=2, padx=8, pady=(0, 8), sticky="ew")
        self.llm_activity_progress.set(0)
        self.llm_activity_progress.grid_remove()
        self.calibration_progress_label = ctk.CTkLabel(
            activity_frame,
            text="Calibration: idle",
            anchor="w",
            justify="left",
            text_color="gray",
        )
        self.calibration_progress_label.grid(row=2, column=0, columnspan=2, padx=8, pady=(0, 8), sticky="ew")
        self.llm_activity_running = False
        self.llm_activity_started_at = None
        self.llm_activity_step = "Idle"

        self.checker_state_frame = ctk.CTkFrame(self, corner_radius=8)
        self.checker_state_frame.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.checker_state_frame.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self, corner_radius=8, command=self.on_checker_tab_changed)
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
        ctk.CTkLabel(
            self.test_table_frame,
            text="No draft tests have run yet. Click Test Draft, or use one-click calibration.",
            text_color="gray",
            anchor="w",
        ).grid(row=0, column=0, padx=8, pady=8, sticky="w")

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
        if self._initial_question or self.pending_review_feedback:
            self.after(0, lambda: self.apply_external_focus(self._initial_question, self.pending_review_feedback))

    def apply_external_focus(self, question=None, review_feedback=None):
        if review_feedback:
            self.pending_review_feedback.update(dict(review_feedback))
        if question and question in (self.parent.gui_questions or []):
            self.question_var.set(question)
            self.load_question_config()
        focused = question or self.question_var.get()
        findings = list(self.pending_review_feedback.get(focused, []))
        if findings:
            self.show_json_result(
                {
                    "review_feedback": findings,
                    "hint": (
                        f"{len(findings)} post-scoring review(s) blame the {focused} checker. "
                        "Click One-click Calibrate (Current Question) to refine with this feedback, then regrade."
                    ),
                }
            )
            self.set_status(
                f"{focused}: {len(findings)} review finding(s) blame the checker. "
                "Run One-click Calibrate (Current Question)."
            )
            if messagebox.askyesno(
                "Start Calibration?",
                (
                    f"Apply {len(findings)} checker-defect review finding(s) to {focused} now?\n\n"
                    "This runs one-click calibrate for the current question."
                ),
            ):
                self.auto_setup_current_question()

    def show_on_top(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

    def close_window(self):
        self._closing = True
        self.parent.checker_manager_window = None
        self.destroy()

    def on_checker_tab_changed(self):
        compact = self.tabview.get() == "Test Results"
        for frame in [
            self.checker_setup_frame,
            self.checker_actions_frame,
            self.checker_activity_frame,
            self.checker_state_frame,
        ]:
            if compact:
                frame.grid_remove()
            else:
                frame.grid()

    def after(self, ms, func=None, *args):
        if (
            func is not None
            and ms == 0
            and hasattr(self, "_ui_queue")
            and threading.current_thread() is not threading.main_thread()
        ):
            self._ui_queue.put(lambda: func(*args))
            return None
        return super().after(ms, func, *args)

    def _drain_ui_queue(self):
        if self._closing or not self.winfo_exists():
            return
        try:
            while True:
                try:
                    callback = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                callback()
        except Exception as exc:
            log(f"Checker Manager UI callback failed: {exc}", "error")
        finally:
            if not self._closing and self.winfo_exists():
                super().after(50, self._drain_ui_queue)

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
        self.parent.update_setup_readiness_banner()

    def compact_checker_status_for_question(self, question):
        question_config = self.checker_config.get("questions", {}).get(question) or self.checker_config.get("questions", {}).get(question.upper())
        if not question_config:
            return f"{question}: needs checker", COLORS["danger"]
        metadata = question_config.get("metadata", {}) if isinstance(question_config, dict) else {}
        audit_status = metadata.get("audit_status", "not_run")
        test_status = metadata.get("test_status", "not_run")
        if (
            metadata.get("calibration_status") == "passed"
            and audit_metadata_is_current(question_config, question)
        ):
            return f"{question}: verified both ways", COLORS["secondary"]
        if audit_status == "passed":
            return f"{question}: audit stale/incomplete", COLORS["warning"]
        if audit_status == "partial":
            return f"{question}: audit partial", COLORS["warning"]
        if audit_status == "uncertain":
            return f"{question}: audit uncertain", COLORS["warning"]
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
        positive_status = metadata.get("positive_gate_status", "not_run")
        negative_status = metadata.get("negative_gate_status", "not_run")
        low = metadata.get("strict_too_low", {}) if isinstance(metadata.get("strict_too_low"), dict) else {}
        high = metadata.get("strict_too_high", {}) if isinstance(metadata.get("strict_too_high"), dict) else {}
        confidence_current = audit_metadata_is_current(question_config, question)
        low_status = str(low.get("status", "in progress")).replace("_", " ").title()
        high_status = str(high.get("status", "in progress")).replace("_", " ").title()
        if metadata.get("strict_status") == "verified" and not confidence_current:
            low_status = high_status = "Stale"
        low_line = (
            f"Too-low: {low_status} — "
            f"deductions reviewed {low.get('reviewed', 0)}/{low.get('required', 0)}"
        )
        bound = high.get("upper_bound")
        bound_text = "not available" if bound is None else f"{100 * float(bound):.1f}%"
        high_line = (
            f"Too-high: {high_status} — "
            f"full-score sample {high.get('reviewed', 0)}/{high.get('required', 0)}, "
            f"95% upper bound {bound_text}"
        )
        if (
            metadata.get("calibration_status") == "passed"
            and confidence_current
        ):
            return (
                f"{question}: Verified ({checker_name})\n{low_line}\n{high_line}",
                COLORS["secondary"],
            )
        blockers = list(metadata.get("strict_blockers", []) or [])
        blocker_text = f"\nNext: {blockers[0]}" if blockers else ""
        if audit_status == "passed":
            return (
                f"{question}: In progress ({checker_name}; accept={positive_status}, reject={negative_status})"
                f"\n{low_line}\n{high_line}{blocker_text}",
                COLORS["warning"],
            )
        if audit_status == "partial":
            return f"{question}: audit partial; some LLM reviews errored but none flagged ({checker_name})", COLORS["warning"]
        if audit_status == "uncertain":
            return f"{question}: audit uncertain; checker was not changed from incomplete evidence ({checker_name})", COLORS["warning"]
        if audit_status in {"flagged", "error"}:
            return f"{question}: audit {audit_status}; review checker before trusting scores ({checker_name})", COLORS["danger"]
        if test_status == "passed":
            return f"{question}: checker saved and draft tests passed; run grading/audit next ({checker_name})", COLORS["warning"]
        return (
            f"{question}: In progress ({checker_name})\n{low_line}\n{high_line}"
            f"{blocker_text or chr(10) + 'Next: Run Test Draft, then One-click Calibrate.'}",
            COLORS["warning"],
        )

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
        saved_config = append_checker_version(
            existing_config,
            question_config,
            0,
            "promoted",
            f"Saved after deterministic checker tests: {test_status}.",
        )
        saved_config.setdefault("metadata", {}).update(
            {
                **existing_metadata,
                **saved_config.get("metadata", {}),
                "saved": True,
                "test_status": test_status,
                "audit_status": "not_run",
                "calibration_status": "not_run",
                "positive_gate_status": "not_run",
                "negative_gate_status": "not_run",
                "strict_status": "stale",
                "strict_blockers": ["Checker changed; regrade and rerun strict verification."],
            }
        )
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
        contract_errors = checker_config_errors(question_config)
        if contract_errors:
            messagebox.showerror("Invalid Checker Contract", "\n".join(contract_errors))
            self.set_status("Checker contract needs correction before it can be saved.")
            return
        structural_errors = structural_requirements_errors(question_config)
        if structural_errors:
            messagebox.showerror("Structural Requirement Needs Input", "\n".join(structural_errors))
            self.set_status("Structural requirement needs a deduction before saving.")
            return
        question = self.question_var.get()
        current_hash = checker_config_hash(question_config)
        test_status = (
            self.latest_checker_test_status.get(question, "not_run")
            if self.latest_checker_test_hash.get(question) == current_hash
            else "not_run"
        )
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

    def rollback_current_checker(self):
        self.run_background(
            "Rolling back checker and regrading...",
            self._rollback_current_checker_worker,
            "Restoring previous checker version",
        )

    def run_background(self, status, worker, activity_message=None):
        if self._background_running:
            self.set_status("Another Checker Manager action is already running.")
            return
        self._background_running = True
        self._worker_snapshot = {
            "question": self.question_var.get(),
            "provider": self.provider_var.get(),
            "model": self.gemini_model_var.get(),
            "assignment_path": self.assignment_path_var.get().strip(),
            "audit_size": self.audit_size_var.get().strip(),
            "config_text": self.config_textbox.get("1.0", tk.END).strip(),
            "slim_output": self.parent.slim_output_var.get(),
        }
        self.set_checker_actions_enabled(False)
        self.set_status(status)
        if activity_message:
            self.start_llm_activity(activity_message)

        def runner():
            try:
                worker()
            finally:
                self.after(0, lambda: self.finish_background_action(activity_message))

        threading.Thread(target=runner, daemon=True).start()

    def finish_background_action(self, activity_message=None):
        if activity_message:
            self.stop_llm_activity()
        self._background_running = False
        self._worker_snapshot = {}
        self.set_checker_actions_enabled(True)
        self.update_gemini_key_status()

    def set_checker_actions_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for button in [
            self.suggest_checker_button,
            self.test_checker_button,
            self.save_checker_button,
            self.run_audit_button,
            self.reload_checker_button,
            self.auto_current_button,
            self.auto_all_button,
            self.rollback_checker_button,
        ]:
            button.configure(state=state)

    def worker_value(self, key, getter):
        return self._worker_snapshot[key] if key in self._worker_snapshot else getter()

    def slim_output_enabled(self):
        return self.worker_value("slim_output", self.parent.slim_output_var.get)

    def start_llm_activity(self, message):
        self.llm_activity_running = True
        self.llm_activity_started_at = time.monotonic()
        self.llm_activity_step = message
        self.llm_activity_progress.grid()
        self.llm_activity_progress.start()
        self.update_llm_activity_label()

    def set_llm_activity_step(self, message):
        self.llm_activity_step = message
        self.update_llm_activity_label()

    def set_calibration_progress(self, message, color=None):
        options = {"text": f"Calibration: {message}"}
        if color:
            options["text_color"] = color
        self.calibration_progress_label.configure(**options)

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
        self.llm_activity_progress.grid_remove()
        self.llm_activity_label.configure(text=f"Done in {elapsed}s")

    def _suggest_with_llm_worker(self):
        try:
            question = self.worker_value("question", self.question_var.get)
            self.after(0, lambda: self.set_llm_activity_step("Compiling reference solution and collecting examples"))
            original_code, inputs, expected_outputs = self.collect_question_context(question)
            self.after(0, lambda: self.set_llm_activity_step("Parsing assignment PDF/DOCX text and images"))
            assignment_path = self.worker_value("assignment_path", lambda: self.assignment_path_var.get().strip())
            assignment_context = parse_assignment_context(assignment_path or None)
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
            config_text = self.worker_value("config_text", lambda: self.config_textbox.get("1.0", tk.END).strip())
            question_config = json.loads(config_text)
            question = self.worker_value("question", self.question_var.get)
            _, _inputs, expected_outputs = self.collect_question_context(question)
            rows = run_checker_tests(question_config, expected_outputs)
            tests_ok, warnings = self.evaluate_checker_test_rows(rows)
            self.latest_checker_test_status[question] = "passed" if tests_ok else "failed"
            self.latest_checker_test_hash[question] = checker_config_hash(question_config)
            self.after(0, lambda: self.show_test_rows(rows))
            status = "passed" if tests_ok else "needs review"
            self.after(0, lambda: self.set_status(f"Checker test {status}: {len(rows)} rows"))
        except Exception as exc:
            self.after(
                0,
                lambda captured_exc=exc: (
                    self.show_test_error(str(captured_exc)),
                    self.show_error("Checker Test Failed", captured_exc),
                ),
            )

    def _run_audit_worker(self):
        try:
            provider = self.make_provider()
            self.after(0, lambda: self.set_llm_activity_step("Parsing assignment context for audit"))
            assignment_path = self.worker_value("assignment_path", lambda: self.assignment_path_var.get().strip())
            assignment_context = parse_assignment_context(assignment_path or None)
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
            assignment_path = self.worker_value("assignment_path", lambda: self.assignment_path_var.get().strip())
            assignment_context = parse_assignment_context(assignment_path or None)
            question = self.worker_value("question", self.question_var.get)
            result = self.auto_configure_question(question, provider, assignment_context, show_prompt=True)
            calibration = self.run_calibration_rounds([result], provider, assignment_context)
            audit_summary = calibration.get("overall", {"status": "skipped", "reviewed": 0})
            payload = {
                "question_results": [self.serializable_auto_result(result)],
                "calibration": calibration,
                "audit": audit_summary,
            }
            self.after(0, lambda captured_result=result: self.apply_auto_config_result(captured_result))
            self.after(0, lambda captured_payload=payload: self.show_json_result(captured_payload))
            self.after(0, lambda: self.set_status(self.auto_setup_status_message([result], audit_summary)))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Auto Setup Failed", captured_exc))

    def _auto_setup_all_worker(self):
        try:
            provider = self.make_provider()
            assignment_path = self.worker_value("assignment_path", lambda: self.assignment_path_var.get().strip())
            assignment_context = parse_assignment_context(assignment_path or None)
            results = []
            for question in self.parent.gui_questions:
                self.after(0, lambda current_question=question: self.set_llm_activity_step(f"Auto setup for {current_question}"))
                try:
                    result = self.auto_configure_question(question, provider, assignment_context, show_prompt=not results)
                except Exception as exc:
                    result = self.failed_auto_config_result(question, exc)
                results.append(result)
            calibration = self.run_calibration_rounds(results, provider, assignment_context)
            audit_summary = calibration.get("overall", {"status": "skipped", "reviewed": 0})
            payload = {
                "question_results": [self.serializable_auto_result(result) for result in results],
                "calibration": calibration,
                "audit": audit_summary,
            }
            first_displayable = next((result for result in results if result["question_config"] or result["test_rows"]), None)
            if first_displayable:
                self.after(0, lambda captured_result=first_displayable: self.apply_auto_config_result(captured_result))
            self.after(0, lambda captured_payload=payload: self.show_json_result(captured_payload))
            self.after(0, lambda: self.set_status(self.auto_setup_status_message(results, audit_summary)))
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Auto Setup All Failed", captured_exc))

    def _rollback_current_checker_worker(self):
        try:
            question = self.worker_value("question", self.question_var.get)
            current = self.checker_config.get("questions", {}).get(question, {})
            metadata = current.get("metadata", {}) if isinstance(current, dict) else {}
            versions = [
                version
                for version in metadata.get("versions", [])
                if version.get("status") == "promoted" and isinstance(version.get("config"), dict)
            ]
            active_hash = metadata.get("active_version")
            active_version = next((version for version in reversed(versions) if version.get("hash") == active_hash), None)
            parent_hash = active_version.get("parent_hash") if active_version else None
            prior = next((version for version in reversed(versions) if version.get("hash") == parent_hash), None)
            if prior is None:
                raise RuntimeError("No previous promoted checker version is available.")
            restored = dict(prior["config"])
            restored["metadata"] = dict(metadata)
            restored["metadata"].update(
                active_version=prior.get("hash", ""),
                audit_status="not_run",
                calibration_status="rolled_back",
                calibration_rollback=True,
            )
            self.checker_config["questions"][question] = restored
            save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)
            self.after(0, lambda: self.set_calibration_progress(f"{question}: rolled back; regrading all students"))
            self.force_grade_outputs()
            self.after(
                0,
                lambda: (
                    self.load_question_config(),
                    self.refresh_checker_status_strip(),
                    self.set_status(f"Rolled back {question} and regenerated grades."),
                ),
            )
        except Exception as exc:
            self.after(0, lambda captured_exc=exc: self.show_error("Checker Rollback Failed", captured_exc))

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
        for draft_round in range(1, 4):
            if suggestion.status != "supported" or not suggestion.checker:
                break
            question_config = {"checker": suggestion.checker, "config": suggestion.config}
            if suggestion.structural_requirements:
                question_config["structural_requirements"] = suggestion.structural_requirements
            self.after(
                0,
                lambda current_round=draft_round: self.set_llm_activity_step(
                    f"{question}: deterministic bidirectional tests, draft {current_round}/3"
                ),
            )
            configuration_errors = checker_config_errors(question_config)
            structural_errors = structural_requirements_errors(question_config)
            current_warnings = list(configuration_errors) + list(structural_errors)
            if not configuration_errors:
                rows = run_checker_tests(question_config, expected_outputs)
                tests_ok, test_warnings = self.evaluate_checker_test_rows(rows)
                current_warnings.extend(test_warnings)
            warnings = current_warnings
            if tests_ok and not structural_errors:
                self.mark_checker_saved(question, question_config, test_status="passed")
                saved = True
                break
            if draft_round == 3:
                break
            deterministic_feedback = [
                AuditResult(
                    "deterministic_probe",
                    question,
                    "flagged",
                    "flagged",
                    "high",
                    warning,
                    checker_behavior=(
                        "false_reject" if "Expected accept" in warning else "false_accept"
                    ),
                    evidence="Deterministic bidirectional checker test.",
                )
                for warning in current_warnings[:12]
            ]
            self.after(
                0,
                lambda current_round=draft_round: self.set_llm_activity_step(
                    f"{question}: refining failed draft {current_round}/3"
                ),
            )
            suggestion = refine_checker(
                question,
                original_code,
                inputs[:8],
                expected_outputs[:8],
                question_config,
                deterministic_feedback,
                provider,
                focused_context.text,
                focused_context.images,
            )
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
        tests_ok = bool(rows) and all(row.get("test_passed", row.get("passed", False)) for row in rows)
        warnings = [
            f"{row.get('variant', 'test')}: {row.get('reason', 'checker test failed')}"
            for row in rows
            if not row.get("test_passed", row.get("passed", False))
        ]
        return tests_ok, warnings

    def run_calibration_rounds(self, setup_results, provider, assignment_context):
        summaries = []
        for setup_result in setup_results:
            if not setup_result.get("saved"):
                summaries.append(
                    {
                        "question": setup_result.get("question", ""),
                        "status": "skipped",
                        "reason": "Initial checker was not saved because deterministic tests failed.",
                        "rounds": [],
                    }
                )
                continue
            summaries.append(
                self.calibrate_question(
                    setup_result["question"],
                    setup_result,
                    provider,
                    assignment_context,
                )
            )
        statuses = [summary.get("status") for summary in summaries]
        if any(status == "flagged" for status in statuses):
            overall_status = "flagged"
        elif any(status == "error" for status in statuses):
            overall_status = "error"
        elif summaries and all(status == "passed" for status in statuses):
            overall_status = "passed"
        else:
            overall_status = "partial"
        overall = {
            "status": overall_status,
            "reviewed": sum(summary.get("reviewed", 0) for summary in summaries),
        }
        return {"overall": overall, "questions": summaries}

    def calibrate_question(self, question, setup_result, provider, assignment_context):
        self.after(0, lambda: self.set_calibration_progress(f"{question}: preparing full reference corpus"))
        original_code, inputs, expected_outputs = self.collect_question_context(question, max_inputs=None)
        active_config = editable_checker_config(self.checker_config["questions"][question])
        active_stack = []
        cumulative_rows = list(setup_result.get("test_rows", []))
        protected_passed_ids: set[str] = set()
        sampled_ids: set[str] = set()
        needs_post_promotion_audit = False
        round_summaries = []
        total_reviewed = 0
        last_status = "flagged"
        review_feedback = list(self.pending_review_feedback.get(question, []))
        latest_results = []
        latest_cases = []
        strict_seed = sum(ord(character) for character in question) * 1000

        for round_number in range(1, MAX_CALIBRATION_ROUNDS + 1):
            self.after(
                0,
                lambda current_round=round_number: self.set_calibration_progress(
                    f"{question}: round {current_round}/{MAX_CALIBRATION_ROUNDS} — grading all students"
                ),
            )
            self.force_grade_outputs()
            seed = strict_seed + round_number
            cases = select_strict_audit_cases(
                [question],
                seed=seed,
                exclude_full_score_ids=sampled_ids,
            )
            if not cases:
                last_status = "flagged" if needs_post_promotion_audit else ("passed" if round_summaries else "skipped")
                round_summaries.append(
                    {
                        "round": round_number,
                        "status": last_status,
                        "reason": (
                            "No holdout cases remain to audit the newly promoted checker."
                            if needs_post_promotion_audit
                            else "No new audit cases remain."
                        ),
                    }
                )
                break

            sampled_ids.update(case.student_id for case in cases)
            self.after(0, lambda selected=cases: self.start_audit_display(selected))
            self.after(
                0,
                lambda current_round=round_number, count=len(cases): self.set_calibration_progress(
                    f"{question}: round {current_round}/{MAX_CALIBRATION_ROUNDS} — auditing 0/{count}"
                ),
            )
            results = audit_cases_with_llm(
                cases,
                self.checker_config.get("questions", {}),
                provider,
                assignment_context,
                max_workers=4,
                progress_callback=lambda result, done, total, current_round=round_number: self.after(
                    0,
                    lambda: (
                        self.add_audit_result(result, done, total),
                        self.set_calibration_progress(
                            f"{question}: round {current_round}/{MAX_CALIBRATION_ROUNDS} — auditing {done}/{total}"
                        ),
                    ),
                ),
            )
            latest_results = results
            latest_cases = cases
            total_reviewed += len(results)
            needs_post_promotion_audit = False
            self.record_audit_results(results, self.audit_overall_status(results))
            passed_ids = {result.student_id for result in results if result.status == "passed"}
            protected_passed_ids.update(passed_ids)
            flagged = [result for result in results if result.status == "flagged"]
            uncertain = [result for result in results if result.status == "uncertain"]
            errors = [result for result in results if result.status == "error"]
            corroborated_feedback = [
                item for item in review_feedback if corroborated_review_feedback_item(item)
            ]
            force_review_refine = bool(corroborated_feedback) and round_number == 1
            round_summary = {
                "round": round_number,
                "sampled": len(results),
                "passed": len(passed_ids),
                "flagged": len(flagged),
                "uncertain": len(uncertain),
                "errors": len(errors),
                "sample_hashes": anonymized_student_hashes({result.student_id for result in results}),
                "review_feedback_used": len(review_feedback) if force_review_refine else 0,
            }
            round_summaries.append(round_summary)

            if not flagged and not force_review_refine:
                if errors and len(errors) == len(results):
                    last_status = "error"
                elif uncertain or errors:
                    last_status = "partial"
                else:
                    last_status = "passed"
                round_summary["status"] = last_status
                if errors:
                    round_summary["reason"] = (
                        f"No checker defect was established; {len(errors)} audit call(s) errored and were not treated as passes."
                    )
                elif uncertain:
                    round_summary["reason"] = "No defects were flagged; uncertain evidence was not used to mutate the checker."
                else:
                    round_summary["reason"] = "No checker defects were flagged."
                break

            if round_number == MAX_CALIBRATION_ROUNDS:
                last_status = "flagged"
                round_summary.update(
                    status="flagged",
                    reason="Checker defects remain after the final audit holdout; no unverified candidate was promoted.",
                )
                break

            self.after(
                0,
                lambda current_round=round_number: self.set_calibration_progress(
                    f"{question}: round {current_round}/{MAX_CALIBRATION_ROUNDS} — proposing a guarded improvement"
                ),
            )
            focused_context = assignment_context_for_question(assignment_context, question)
            proposal = refine_checker(
                question,
                original_code,
                inputs[:8],
                expected_outputs[:8],
                active_config,
                results,
                provider,
                focused_context.text,
                focused_context.images,
                review_feedback=corroborated_feedback if force_review_refine else None,
            )
            if proposal.status != "supported" or not proposal.checker:
                round_summary.update(status="rejected", reason="LLM did not produce a supported candidate.")
                last_status = "flagged"
                break
            candidate = {"checker": proposal.checker, "config": proposal.config}
            if proposal.structural_requirements:
                candidate["structural_requirements"] = proposal.structural_requirements
            config_errors = checker_config_errors(candidate)
            if config_errors:
                round_summary.update(status="rejected", reason="; ".join(config_errors))
                last_status = "flagged"
                self._record_rejected_candidate(question, active_config, candidate, round_number, round_summary["reason"])
                break

            candidate_rows = run_checker_tests(candidate, expected_outputs, max_cases=len(expected_outputs))
            candidate_tests_ok, candidate_warnings = self.evaluate_checker_test_rows(candidate_rows)
            feedback_rows = review_feedback_test_rows(candidate, corroborated_feedback)
            feedback_ok, feedback_failures = validate_candidate_against_rows(candidate, feedback_rows)
            cumulative_ok, cumulative_failures = validate_candidate_against_rows(candidate, cumulative_rows)
            preserves_passed, changed_ids = candidate_preserves_audited_cases(
                question,
                protected_passed_ids,
                active_config,
                candidate,
                expected_outputs,
                allowed_changed_ids={
                    str(item.get("student_id", ""))
                    for item in corroborated_feedback
                    if item.get("student_id")
                },
            )
            if not candidate_tests_ok or not feedback_ok or not cumulative_ok or not preserves_passed:
                reasons = candidate_warnings + feedback_failures + cumulative_failures
                if changed_ids:
                    reasons.append(f"changed {len(changed_ids)} previously passed audited student(s)")
                reason = "; ".join(reasons[:8]) or "candidate failed no-regression gates"
                round_summary.update(status="rejected", reason=reason)
                last_status = "flagged"
                self._record_rejected_candidate(question, active_config, candidate, round_number, reason)
                break

            active_stack.append(active_config)
            promoted = append_checker_version(
                self.checker_config["questions"].get(question, {}),
                candidate,
                round_number,
                "promoted",
                f"Passed {len(candidate_rows)} mutation tests and preserved {len(protected_passed_ids)} audited students.",
            )
            promoted.setdefault("metadata", {}).update(
                saved=True,
                test_status="passed",
                audit_status="not_run",
                calibration_round=round_number,
                strict_status="stale",
                strict_blockers=["Checker promotion invalidated prior population evidence."],
            )
            self.checker_config["questions"][question] = promoted
            save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)
            active_config = editable_checker_config(promoted)
            cumulative_rows.extend(candidate_rows)
            cumulative_rows.extend(
                {
                    **row,
                    "test_passed": True,
                }
                for row in feedback_rows
            )
            needs_post_promotion_audit = True
            if force_review_refine:
                self.pending_review_feedback.pop(question, None)
                review_feedback = []
            round_summary.update(
                status="promoted",
                reason="Candidate passed deterministic, cumulative, and audited-student no-regression gates.",
                mutation_tests=len(candidate_rows),
                protected_audits=len(protected_passed_ids),
            )
            self.after(
                0,
                lambda current_round=round_number: self.set_calibration_progress(
                    f"{question}: round {current_round}/{MAX_CALIBRATION_ROUNDS} — promoted; regrading before next audit",
                    COLORS["secondary"],
                ),
            )
        else:
            last_status = "flagged"

        if last_status in {"flagged", "error", "partial"} and active_stack:
            rollback = active_stack[-1]
            rollback_version = append_checker_version(
                self.checker_config["questions"].get(question, {}),
                rollback,
                len(round_summaries),
                "promoted",
                "Automatic rollback after a later calibration round remained flagged.",
            )
            rollback_version.setdefault("metadata", {}).update(
                saved=True,
                test_status="passed",
                audit_status="flagged",
                calibration_rollback=True,
                strict_status="stale",
                strict_blockers=["Rollback and regrade invalidated prior population evidence."],
            )
            self.checker_config["questions"][question] = rollback_version
            save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)
            self.force_grade_outputs()

        metadata = self.checker_config["questions"][question].setdefault("metadata", {})
        positive_rows = [row for row in cumulative_rows if bool(row.get("expected_pass", True))]
        negative_rows = [row for row in cumulative_rows if not bool(row.get("expected_pass", True))]
        metadata["positive_gate_status"] = (
            "passed"
            if positive_rows and all(row.get("test_passed", False) for row in positive_rows)
            else "failed"
        )
        metadata["negative_gate_status"] = (
            "passed"
            if negative_rows and all(row.get("test_passed", False) for row in negative_rows)
            else "failed"
        )
        checker_hash = editable_checker_hash(self.checker_config["questions"][question])
        strict_result = evaluate_strict_population_confidence(
            audit_population_records(load_audit_population([question])),
            [
                SemanticAuditEvidence(
                    student_id=result.student_id,
                    status=result.status,
                    checker_behavior=result.checker_behavior,
                    checker_hash=checker_hash,
                    evidence_fingerprint=stable_fingerprint(
                        result.status,
                        result.checker_behavior,
                        result.reason,
                        result.evidence,
                    ),
                    verification_passes=result.verification_passes,
                    disagreement=(
                        result.status == "uncertain"
                        and "disagreed" in str(result.reason).lower()
                    ),
                )
                for result in latest_results
            ],
            checker_hash=checker_hash,
            deterministic_negative_gate_passed=metadata["negative_gate_status"] == "passed",
            seed=strict_seed,
            fresh=not needs_post_promotion_audit,
            sampled_full_score_ids={
                case.student_id for case in latest_cases if float(case.score) >= 99.999
            },
        )
        metadata.update(
            strict_confidence_metadata(
                strict_result,
                checker_hash=checker_hash,
                population_fingerprint=grade_population_evidence_fingerprint(question),
                sampled_id_hashes=anonymized_student_hashes(set(strict_result.sampled_ids)),
            )
        )
        if last_status == "passed" and (
            metadata["positive_gate_status"] != "passed"
            or metadata["negative_gate_status"] != "passed"
            or strict_result.status != "verified"
        ):
            last_status = "flagged"
            round_summaries.append(
                {
                    "round": len(round_summaries) + 1,
                    "status": "flagged",
                    "reason": "Strict too-low or too-high confidence coverage was incomplete, stale, uncertain, or failed.",
                }
            )
        metadata["calibration_status"] = last_status
        if last_status == "passed":
            metadata.pop("calibration_rollback", None)
        metadata["calibration_rounds"] = round_summaries
        metadata["calibration_reviewed"] = total_reviewed
        save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)
        color = COLORS["secondary"] if last_status == "passed" else COLORS["warning"]
        self.after(
            0,
            lambda: (
                self.set_calibration_progress(
                    f"{question}: {last_status} after {len(round_summaries)} round(s), {total_reviewed} audits",
                    color,
                ),
                self.refresh_checker_status_strip(),
            ),
        )
        return {
            "question": question,
            "status": last_status,
            "reviewed": total_reviewed,
            "rounds": round_summaries,
        }

    def _record_rejected_candidate(self, question, active_config, candidate, round_number, reason):
        rejected = append_checker_version(
            self.checker_config["questions"].get(question, {}),
            candidate,
            round_number,
            "rejected",
            reason,
        )
        active_with_metadata = dict(active_config)
        active_with_metadata["metadata"] = rejected.get("metadata", {})
        self.checker_config["questions"][question] = active_with_metadata
        save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)

    def force_grade_outputs(self):
        for question_config in self.checker_config.get("questions", {}).values():
            if isinstance(question_config, dict):
                metadata = question_config.setdefault("metadata", {})
                metadata["strict_status"] = "stale"
                metadata["strict_blockers"] = ["Regrading invalidated prior population evidence."]
        save_checker_config(self.checker_config, DEFAULT_CHECKER_CONFIG_PATH)
        run_tests(
            self.parent.gui_questions,
            progress_callback=lambda *_args: None,
            scoring_mode=self.parent.gui_test_scoring_mode,
            deduction_per_error=self.parent.gui_test_error_deduction,
            llm_compile_repair_enabled=self.parent.gui_llm_compile_repair_enabled,
            llm_compile_repair_provider=self.parent.make_compile_repair_provider(),
            llm_compile_repair_penalty=self.parent.gui_llm_compile_repair_penalty,
            llm_compile_repair_max_attempts=self.parent.gui_llm_compile_repair_max_attempts,
            vs_path_override=self.parent.gui_vs_path,
        )
        create_excels(
            self.parent.gui_questions,
            self.parent.gui_weights,
            self.parent.gui_penalty,
            slim=self.slim_output_enabled(),
            per_error_penalty=self.parent.gui_per_error_penalty,
        )
        self.after(0, self.parent.update_excel_button_state)

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
            elif any(result.status == "uncertain" for result in question_results):
                audit_status = "uncertain"
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
                audit_rubric_version=AUDIT_RUBRIC_VERSION,
                audit_checker_hash=editable_checker_hash(
                    self.checker_config.get("questions", {}).get(question, {})
                ),
                audit_evidence_fingerprint=stable_fingerprint(
                    [
                        {
                            "student": result.student_id,
                            "status": result.status,
                            "behavior": result.checker_behavior,
                            "reason": result.reason,
                            "evidence": result.evidence,
                        }
                        for result in question_results
                    ]
                ),
                audit_evidence_mtime=latest_audit_evidence_mtime(question),
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
            progress_callback=lambda *_args: None,
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
            slim=self.slim_output_enabled(),
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

    def collect_question_context(self, question, max_inputs=8):
        try:
            original_path = os.path.join(question, "original_sol.c")
            with open(original_path, "r", encoding="utf-8", errors="ignore") as original_file:
                original_code = original_file.read()
            inputs = read_inputs_from_file(question)
            if max_inputs is not None:
                inputs = inputs[:max_inputs]
            setup_visual_studio_environment(self.parent.gui_vs_path)
            # Checker Manager runs in a GUI worker thread. Supplying a callback
            # keeps get_ground_truth from creating a terminal tqdm bar, which can
            # raise OSError(EINVAL) when no valid Windows console handle exists.
            expected_outputs = get_ground_truth(question, inputs, progress_callback=lambda *_args: None)
            if not expected_outputs and inputs:
                raise RuntimeError(
                    "the reference solution did not compile or produce outputs; "
                    "check the configured Visual Studio vcvars path"
                )
            return original_code, inputs, expected_outputs
        except Exception as exc:
            raise RuntimeError(f"{question}: failed to collect reference outputs: {exc}") from exc

    def make_provider(self):
        provider_name = (
            self._worker_snapshot["provider"]
            if "provider" in self._worker_snapshot
            else self.provider_var.get()
        )
        model_name = (
            self._worker_snapshot["model"]
            if "model" in self._worker_snapshot
            else self.gemini_model_var.get()
        )
        if provider_name == "Gemini":
            if not self.has_gemini_api_key():
                raise ValueError(self.gemini_key_missing_message())
            return GeminiProvider(model=str(model_name).strip() or None)
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
            value = (
                self._worker_snapshot["audit_size"]
                if "audit_size" in self._worker_snapshot
                else self.audit_size_var.get().strip()
            )
            return max(1, min(50, int(value)))
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
        self.on_checker_tab_changed()

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
        self.on_checker_tab_changed()

    def show_test_error(self, message):
        self.clear_test_table()
        ctk.CTkLabel(
            self.test_table_frame,
            text=f"Test Draft could not run:\n{message}",
            text_color=COLORS["danger"],
            anchor="w",
            justify="left",
            wraplength=900,
        ).grid(row=0, column=0, columnspan=5, padx=8, pady=8, sticky="ew")
        self.tabview.set("Test Results")
        self.on_checker_tab_changed()

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
        passed = bool(row.get("test_passed", row.get("passed")))
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
        self.on_checker_tab_changed()

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
        if any(result.status == "uncertain" for result in results):
            return "yellow: one or more reviews were uncertain"
        return "green: all sampled reviews passed"


if __name__ == "__main__":
    app = App()
    app.mainloop()
