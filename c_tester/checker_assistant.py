"""LLM-assisted checker suggestion and audit helpers."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import html
import json
import logging
import os
import re
import urllib.error
import urllib.request
import zipfile
from typing import Any, Protocol

import pandas as pd

from .semantic_grading import available_checker_templates, compare_output_with_config


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
MAX_ASSIGNMENT_IMAGES = 8
CHECKER_SUGGESTION_EVAL_CASES = {
    "common_supported": [
        {
            "task_shape": "one numeric answer such as factorial, sum, max, count, gcd, or lcm",
            "expected_checker": "last_integer",
            "success_criteria": "Ignore prompts and labels, compare the final numeric answer.",
        },
        {
            "task_shape": "ordered integer sequence such as Fibonacci, primes, sorted array, or printed array values",
            "expected_checker": "integer_list",
            "success_criteria": "Compare the extracted integer sequence, preserving order when the assignment requires order.",
        },
        {
            "task_shape": "divisor-list task, including zero-input wording about no divisors",
            "expected_checker": "divisors",
            "success_criteria": "Validate the divisor set from the numeric input instead of trusting prompt numbers.",
        },
        {
            "task_shape": "reverse integer digits",
            "expected_checker": "reverse_integer",
            "success_criteria": "Compare the reversed integer answer at the configured answer position.",
        },
        {
            "task_shape": "textual yes/no or category answer where punctuation/case are not meaningful",
            "expected_checker": "normalized_text",
            "success_criteria": "Normalize harmless case and punctuation only.",
        },
    ],
    "edge_or_unsupported": [
        {
            "task_shape": "exact menu, drawing, or required sentence where formatting is part of the answer",
            "expected_checker": "exact",
            "success_criteria": "Use exact only when semantic normalization would hide a real mistake.",
        },
        {
            "task_shape": "floating point answer requiring tolerance",
            "expected_checker": "no_supported_checker",
            "success_criteria": "No current checker supports numeric tolerance, so require manual configuration.",
        },
        {
            "task_shape": "multi-column table or compound answer with mixed text and numbers",
            "expected_checker": "no_supported_checker",
            "success_criteria": "Do not force last_integer or integer_list when important structure would be lost.",
        },
        {
            "task_shape": "assignment text and images include multiple questions",
            "expected_checker": "selected_question_only",
            "success_criteria": "Use only the selected question number and ignore neighboring question context.",
        },
    ],
}
CHECKER_AUDIT_EVAL_CASES = {
    "looks_correct_when": [
        "Perfect score, grade text, output, checker result, and Excel fields agree.",
        "Wrong-input count, comments, and assigned score match the configured checker failures.",
        "Compile repair succeeded and the final score reflects the configured repair penalty and repair note.",
        "Structural recursion/loop checks were enforced when configured, and the score/comments reflect any structural penalty.",
        "Submission penalties in final fields match naming, RAR, missing-file, or nested-folder notes.",
    ],
    "flagged_when": [
        "Assigned score conflicts with wrong-input count or checker pass/fail evidence.",
        "Excel comments, timeout fields, compile-error flags, or wrong-input fields contradict the grade text.",
        "Final weighted grade does not match question scores, weights, or submission penalties when those fields are present.",
        "Structural check status, structural penalty, grade text, or final comments contradict each other.",
        "Checker configuration is unsupported or appears mismatched to the assignment intent and would hide mistakes.",
    ],
    "uncertain_when": [
        "Reference context is insufficient to know whether text formatting is semantically important.",
        "Student output, grade text, or expected/reference output is missing or truncated.",
        "The case depends on assignment-specific intent not visible in the selected-question context.",
    ],
}
AUDIT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["looks_correct", "flagged", "uncertain"]},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "risk", "reason"],
    "additionalProperties": False,
}
SUGGEST_CHECKER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["supported", "no_supported_checker"]},
        "checker": {"type": "string", "nullable": True},
        "config": {"type": "object"},
        "structural_requirements": {
            "type": "object",
            "properties": {
                "requires_recursion": {"type": "boolean", "nullable": True},
                "entry_functions": {"type": "array", "items": {"type": "string"}, "nullable": True},
                "allow_recursive_helpers": {"type": "boolean", "nullable": True},
                "forbid_loops": {"type": "boolean", "nullable": True},
                "deduction": {"type": "number", "nullable": True},
                "deduction_required": {"type": "boolean", "nullable": True},
                "reason": {"type": "string", "nullable": True},
            },
            "nullable": True,
        },
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["status", "checker", "config", "confidence", "reason"],
    "additionalProperties": False,
}


def get_google_api_key() -> str | None:
    key = os.getenv("GOOGLE_API_KEY")
    if key:
        return key
    if os.name != "nt":
        return None

    try:
        import winreg
    except ImportError:
        return None

    locations = (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    )
    for root, subkey in locations:
        try:
            with winreg.OpenKey(root, subkey) as env_key:
                key, _ = winreg.QueryValueEx(env_key, "GOOGLE_API_KEY")
                if key:
                    os.environ["GOOGLE_API_KEY"] = key
                    return key
        except OSError:
            continue
    return None


@dataclass(frozen=True)
class SuggestionResult:
    status: str
    question: str
    checker: str | None
    config: dict
    confidence: float
    reason: str
    structural_requirements: dict | None = None


@dataclass(frozen=True)
class AuditCase:
    student_id: str
    question: str
    score: float
    grade_text: str
    output_text: str
    excel_fields: dict[str, Any]
    final_fields: dict[str, Any]


@dataclass(frozen=True)
class AuditResult:
    student_id: str
    question: str
    status: str
    verdict: str
    risk: str
    reason: str


@dataclass(frozen=True)
class AssignmentImage:
    label: str
    mime_type: str
    data: bytes
    text: str = ""


@dataclass(frozen=True)
class AssignmentContext:
    text: str = ""
    images: tuple[AssignmentImage, ...] = ()
    source_path: str = ""


class LLMProvider(Protocol):
    def complete_json(
        self,
        prompt: str,
        images: list[AssignmentImage] | tuple[AssignmentImage, ...] | None = None,
        response_schema: dict | None = None,
    ) -> dict:
        """Return a JSON object from an LLM prompt."""


class GeminiProvider:
    """Small Gemini REST client using GOOGLE_API_KEY by default."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or get_google_api_key()
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set")

    def complete_json(
        self,
        prompt: str,
        images: list[AssignmentImage] | tuple[AssignmentImage, ...] | None = None,
        response_schema: dict | None = None,
    ) -> dict:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:"
            f"generateContent?key={self.api_key}"
        )
        parts = [{"text": prompt}]
        for image in images or []:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": image.mime_type,
                        "data": base64.b64encode(image.data).decode("ascii"),
                    }
                }
            )
        generation_config = {"responseMimeType": "application/json"}
        if response_schema:
            generation_config["responseSchema"] = gemini_response_schema(response_schema)
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": generation_config,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini request failed: {exc}; {error_body[:1000]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini request failed: {exc}") from exc

        text = body["candidates"][0]["content"]["parts"][0]["text"]
        return parse_json_object(text)


def gemini_response_schema(schema: Any) -> Any:
    """Return the subset of JSON schema accepted by Gemini responseSchema."""
    unsupported_keys = {"additionalProperties", "$schema"}
    if isinstance(schema, dict):
        return {
            key: gemini_response_schema(value)
            for key, value in schema.items()
            if key not in unsupported_keys
        }
    if isinstance(schema, list):
        return [gemini_response_schema(item) for item in schema]
    return schema


def list_gemini_models(api_key: str | None = None) -> list[str]:
    key = api_key or get_google_api_key()
    if not key:
        raise ValueError("GOOGLE_API_KEY is not set")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini model list request failed: {exc}") from exc
    model_names = []
    for model in body.get("models", []):
        methods = model.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        name = str(model.get("name", "")).removeprefix("models/")
        if name:
            model_names.append(name)
    return sorted(model_names)


def complete_json_with_schema(
    provider: LLMProvider,
    prompt: str,
    images: list[AssignmentImage] | tuple[AssignmentImage, ...] | None = None,
    response_schema: dict | None = None,
) -> dict:
    if response_schema is None:
        return provider.complete_json(prompt, images)
    try:
        return provider.complete_json(prompt, images, response_schema=response_schema)
    except TypeError as exc:
        if "response_schema" not in str(exc):
            raise
        return provider.complete_json(prompt, images)


class FakeLLMProvider:
    """Deterministic provider for tests and offline demos."""

    def complete_json(
        self,
        prompt: str,
        _images: list[AssignmentImage] | tuple[AssignmentImage, ...] | None = None,
        response_schema: dict | None = None,
    ) -> dict:
        del response_schema
        lower_prompt = prompt.lower()
        if '"task": "compile_fix"' in lower_prompt:
            try:
                payload = json.loads(prompt)
                original_code = str(payload.get("original_code", ""))
                current_error = str(payload.get("current_compile_error", ""))
            except json.JSONDecodeError:
                original_code = prompt
                current_error = prompt
            if "too_bad" in original_code.lower() or "ambiguous" in current_error.lower():
                return {
                    "status": "too_bad",
                    "too_bad": True,
                    "fixed_code": "",
                    "compile_issue": "The compile failure is tied to unclear missing logic.",
                    "fix_reason": "code cannot be made to compile without guessing the student's intended logic.",
                    "changes_made": "",
                    "risk_note": "Compile-only repair is unsafe.",
                }
            fixed_code = original_code.replace("/* FAKE_FIX_SEMICOLON */", ";")
            fixed_code = fixed_code.replace("return 0\n}", "return 0;\n}")
            fixed_code = fixed_code.replace("return 0\r\n}", "return 0;\n}")
            return {
                "status": "fixed_candidate",
                "too_bad": False,
                "fixed_code": fixed_code,
                "compile_issue": "A compile-only syntax fix is needed.",
                "fix_reason": "added missing syntax required for compilation.",
                "changes_made": "added missing semicolon",
                "risk_note": "",
            }
        if '"task": "audit_score"' in lower_prompt:
            return {
                "verdict": "looks_correct",
                "risk": "low",
                "reason": "Deterministic fake provider accepts the supplied audit package.",
            }
        if '"task": "review_score_deduction"' in lower_prompt or '"task": "apply_review_fix"' in lower_prompt:
            return self._fake_review_response(prompt, lower_prompt)
        if "divisor" in lower_prompt:
            return {
                "status": "supported",
                "checker": "divisors",
                "config": {"allow_prompt_numbers": True, "zero_requires_no_divisors_message": True},
                "confidence": 0.9,
                "reason": "The expected outputs describe divisors.",
                "structural_requirements": {},
            }
        if "reverse" in lower_prompt:
            return {
                "status": "supported",
                "checker": "reverse_integer",
                "config": {"answer_position": "last_integer"},
                "confidence": 0.9,
                "reason": "The expected outputs describe reversing an integer.",
                "structural_requirements": {},
            }
        return {
            "status": "no_supported_checker",
            "checker": None,
            "config": {},
            "confidence": 0.0,
            "reason": "No deterministic fake match found.",
            "structural_requirements": {},
        }

    def _fake_review_response(self, prompt: str, lower_prompt: str) -> dict:
        if '"task": "apply_review_fix"' in lower_prompt:
            return self._fake_apply_review_fix_response(prompt)
        return self._fake_score_review_response(prompt)

    @staticmethod
    def _fake_apply_review_fix_response(prompt: str) -> dict:
        try:
            payload = json.loads(prompt)
            current_code = str(payload.get("current_code", ""))
        except json.JSONDecodeError:
            current_code = prompt
        return {
            "fixed_code": "/* REVIEWER FIX: fake provider left code unchanged for offline preview. */\n" + current_code,
            "explanation": "Fake/offline mode demonstrates the fix workflow without changing program logic.",
            "changes_made": ["Added a visible reviewer-fix comment only."],
            "tests_to_run": ["Run all grading inputs and inspect any remaining mismatches."],
            "risk_note": "Fake/offline mode does not produce real code fixes.",
        }

    @staticmethod
    def _fake_score_review_response(prompt: str) -> dict:
        try:
            payload = json.loads(prompt)
            failed_cases = payload.get("failed_cases", [])
        except json.JSONDecodeError:
            failed_cases = []
        failed_inputs = [str(case.get("input_value", "")) for case in failed_cases if isinstance(case, dict)]
        examples = [
            {
                "input": str(case.get("input_value", "")),
                "expected_output": str(case.get("expected_output", "")),
                "actual_output": str(case.get("actual_output", "")),
                "why_it_failed": str(case.get("reason", "")) or "The actual output did not match the expected output.",
            }
            for case in failed_cases[:3]
            if isinstance(case, dict)
        ]
        return {
            "summary": "The fake reviewer grouped the supplied failures as one deterministic grading issue.",
            "deduction_is_plausible": True,
            "root_causes": [
                {
                    "issue": "The output differs from the expected format or value for the listed inputs.",
                    "failed_inputs": failed_inputs,
                    "deduction_impact": f"{len(failed_inputs)} failed input(s) contributed to the shown deduction.",
                    "examples": examples,
                }
            ],
            "inline_comments": [
                {
                    "line": 1,
                    "comment": "Start by checking the branch or formatting responsible for the first failed case.",
                }
            ],
            "fix_to_full_score": "Make the output match the expected behavior for every failed input.",
            "risk_note": "",
        }


def parse_json_object(text: str) -> dict:
    text = strip_json_fence(text.strip())
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        candidate = extract_first_json_object_text(text)
        if not candidate:
            raise exc
        parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_first_json_object_text(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string or char == '"':
            in_string, escaped, consumed = advance_json_string_state(char, in_string, escaped)
            if consumed:
                continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def advance_json_string_state(char: str, in_string: bool, escaped: bool) -> tuple[bool, bool, bool]:
    if not in_string:
        return True, False, True
    if escaped:
        return True, False, True
    if char == "\\":
        return True, True, True
    if char == '"':
        return False, False, True
    return True, False, True


def parse_assignment_file(path: str | None) -> str:
    return parse_assignment_context(path).text


def parse_assignment_context(path: str | None) -> AssignmentContext:
    if not path:
        return AssignmentContext()
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in {".txt", ".md", ".csv"}:
        with open(path, "r", encoding="utf-8", errors="ignore") as text_file:
            return AssignmentContext(text=text_file.read(), source_path=path)
    if ext == ".docx":
        return parse_docx_context(path)
    if ext == ".pdf":
        return parse_pdf_context(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as text_file:
        return AssignmentContext(text=text_file.read(), source_path=path)


def parse_docx_text(path: str) -> str:
    return parse_docx_context(path).text


def parse_docx_context(path: str) -> AssignmentContext:
    text = parse_docx_text_with_package(path)
    images = extract_docx_images(path)
    return AssignmentContext(text=text, images=tuple(images), source_path=path)


def parse_docx_text_with_package(path: str) -> str:
    try:
        from docx import Document
    except ImportError:
        return parse_docx_text_from_xml(path)

    document = Document(path)
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)
    return "\n".join(parts)


def parse_docx_text_from_xml(path: str) -> str:
    with zipfile.ZipFile(path) as docx:
        xml = docx.read("word/document.xml").decode("utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", " ", xml)
    return html.unescape(" ".join(text.split()))


def extract_docx_images(path: str) -> list[AssignmentImage]:
    images = []
    with zipfile.ZipFile(path) as docx:
        for name in docx.namelist():
            if not name.startswith("word/media/"):
                continue
            mime_type = image_mime_type(name)
            if not mime_type:
                continue
            images.append(
                AssignmentImage(
                    label=f"DOCX embedded image {len(images) + 1}: {os.path.basename(name)}",
                    mime_type=mime_type,
                    data=docx.read(name),
                )
            )
            if len(images) >= MAX_ASSIGNMENT_IMAGES:
                break
    return images


def parse_pdf_text_best_effort(path: str) -> str:
    return parse_pdf_context(path).text


def parse_pdf_context(path: str) -> AssignmentContext:
    try:
        return parse_pdf_context_with_pymupdf(path)
    except ImportError:
        text = parse_pdf_text_with_pypdf(path)
        return AssignmentContext(text=text, source_path=path)


def parse_pdf_context_with_pymupdf(path: str) -> AssignmentContext:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError("PDF image extraction requires PyMuPDF. Run: python -m pip install pymupdf") from exc

    document = fitz.open(path)
    text_parts = []
    images = []
    for page_index, page in enumerate(document, start=1):
        page_text = page.get_text("text").strip()
        if page_text:
            text_parts.append(page_text)
        if len(images) < MAX_ASSIGNMENT_IMAGES:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
            images.append(
                AssignmentImage(
                    label=f"PDF page {page_index}",
                    mime_type="image/png",
                    data=pixmap.tobytes("png"),
                    text=page_text,
                )
            )
    text = "\n".join(text_parts).strip()
    if not text:
        text = parse_pdf_text_with_pypdf(path)
    return AssignmentContext(text=text, images=tuple(images), source_path=path)


def parse_pdf_text_with_pypdf(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF assignment parsing requires pypdf. Run: python -m pip install pypdf") from exc

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(path, strict=False)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(page_text.strip() for page_text in pages if page_text.strip())
    if not text:
        raise ValueError("Could not extract text from PDF assignment file.")
    return text


def image_mime_type(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext)


def assignment_context_for_question(context: AssignmentContext | str, question: str) -> AssignmentContext:
    if isinstance(context, str):
        context = AssignmentContext(text=context)
    question_text = extract_question_assignment_text(context.text, question)
    images = tuple(image for image in context.images if assignment_image_matches_question(image, question))
    if context.images and not images:
        images = context.images[:MAX_ASSIGNMENT_IMAGES]
    return AssignmentContext(
        text=question_text,
        images=images[:MAX_ASSIGNMENT_IMAGES],
        source_path=context.source_path,
    )


def extract_question_assignment_text(text: str, question: str) -> str:
    if not text:
        return ""
    question_number = question_number_from_name(question)
    if question_number is None:
        return text[:12000]

    matches = list(question_heading_matches(text))
    preamble = text[: matches[0][1]].strip() if matches else ""
    for index, match in enumerate(matches):
        if match[0] != question_number:
            continue
        start = match[1]
        end = matches[index + 1][1] if index + 1 < len(matches) else len(text)
        question_text = text[start:end].strip()
        if preamble:
            return f"Global assignment instructions:\n{preamble}\n\nSelected question:\n{question_text}"[:12000]
        return question_text[:12000]
    return text[:12000]


def assignment_image_matches_question(image: AssignmentImage, question: str) -> bool:
    question_number = question_number_from_name(question)
    if question_number is None or not image.text:
        return not image.text
    return any(match[0] == question_number for match in question_heading_matches(image.text))


def question_number_from_name(question: str) -> int | None:
    match = re.search(r"\d+", question or "")
    return int(match.group(0)) if match else None


def question_heading_matches(text: str):
    pattern = re.compile(r"(?:^|\n)\s*(?:question\s*(\d+)\b|q\s*(\d+)\b|שאלה\s*(\d+))", re.IGNORECASE)
    for match in pattern.finditer(text):
        number_text = match.group(1) or match.group(2) or match.group(3)
        if number_text:
            yield int(number_text), match.start()


def build_suggestion_prompt(
    question: str,
    original_code: str,
    inputs: list[str],
    expected_outputs: list[tuple[str, str]],
    assignment_text: str = "",
    assignment_images: list[AssignmentImage] | tuple[AssignmentImage, ...] | None = None,
) -> str:
    question_number = question_number_from_name(question)
    payload = {
        "task": "suggest_checker",
        "role": "You are configuring a deterministic C homework output checker. You do not grade students and you do not write code.",
        "question": question,
        "target_question_number": question_number,
        "available_checkers": available_checker_templates(),
        "eval_cases": CHECKER_SUGGESTION_EVAL_CASES,
        "original_solution_c": original_code,
        "inputs": inputs,
        "expected_outputs": [{"input": value, "output": output} for value, output in expected_outputs],
        "assignment_text_for_selected_question_optional": assignment_text,
        "assignment_images_for_selected_question_optional": [image.label for image in assignment_images or []],
        "instructions": (
            f"Focus only on the selected question {question} (question number {question_number}). If the assignment text "
            "or images contain multiple questions, ignore the other question sections. Infer the intended answer and output "
            "format from the selected-question assignment context when present, the reference C code, the test inputs, and "
            "the reference outputs. Select exactly one available checker template and only supported "
            "configuration options. Prefer the simplest checker that validates the semantic answer while ignoring harmless "
            "prompts/labels/spacing. Do not invent code, regular expressions, checker names, or unsupported options. "
            "Each input string is the full stdin sent to the program, not necessarily the mathematical argument. "
            "Some assignments use routing/menu fields before the actual question argument. "
            "For those multi-integer/menu inputs, do not choose checkers that derive the answer directly from the raw stdin "
            "unless that checker can be configured with input_integer_index to point at the actual task argument. "
            "If no input-derived checker safely matches the task, compare the reference output answer, usually with "
            "last_integer for one numeric Result value. "
            "If no available checker can safely validate the task, return status no_supported_checker. When uncertain, "
            "lower confidence and explain what manual review is needed. If the selected question requires recursion, "
            "forbids loops, or gives an explicit structural penalty, include structural_requirements. Derive deduction "
            "only from explicit assignment text such as 'non-recursive gets 0'. If the assignment requires recursion "
            "but does not state the deduction, set deduction to null and deduction_required to true so the grader can "
            "fill the mandatory value manually."
        ),
        "decision_guidance": {
            "exact": "Use only when exact output format is required.",
            "normalized_text": "Use for mostly textual answers where case/punctuation are irrelevant.",
            "last_integer": (
                "Use for tasks with one numeric answer at the end, such as factorial, sum, max, count, gcd, lcm, "
                "binary-as-digits, digit reductions, or a series value. Prefer this for menu/routing-style stdin "
                "when the final answer is printed as Result = <number>."
            ),
            "integer_list": "Use for sequences/lists like Fibonacci, primes, sorted arrays, or printed array values.",
            "divisors": (
                "Use only for divisor-list tasks when the raw stdin value is the number whose divisors are expected. "
                "If stdin includes routing/menu fields, set input_integer_index to the argument integer. "
                "Do not use it for unrelated numeric transformations."
            ),
            "reverse_integer": (
                "Use only for reversing integer digits when the raw stdin value is the number being reversed. "
                "If stdin includes routing/menu fields, set input_integer_index to the argument integer. "
                "Do not use it for digit-sum/digit-reduction tasks."
            ),
            "no_supported_checker": "Use for unsupported needs such as floating-point tolerance, multi-column structure, or mixed semantic fields.",
        },
        "response_schema": {
            "status": "supported | no_supported_checker",
            "checker": "checker name or null",
            "config": "object",
            "structural_requirements": {
                "requires_recursion": "boolean, true only when assignment requires recursion",
                "entry_functions": "array of function names to inspect, e.g. ['q_2']",
                "allow_recursive_helpers": "boolean, true when helper recursion is acceptable",
                "forbid_loops": "boolean, true when loops are disallowed",
                "deduction": "number of points to deduct, or null when mandatory manual input is needed",
                "deduction_required": "boolean, true when deduction could not be derived from assignment text",
                "reason": "short explanation grounded in the assignment text",
            },
            "confidence": "0.0-1.0",
            "reason": "short explanation of why this checker is safe and what output it validates",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def suggest_checker(
    question: str,
    original_code: str,
    inputs: list[str],
    expected_outputs: list[tuple[str, str]],
    provider: LLMProvider,
    assignment_text: str = "",
    assignment_images: list[AssignmentImage] | tuple[AssignmentImage, ...] | None = None,
) -> SuggestionResult:
    prompt = build_suggestion_prompt(question, original_code, inputs, expected_outputs, assignment_text, assignment_images)
    response = complete_json_with_schema(provider, prompt, assignment_images, SUGGEST_CHECKER_RESPONSE_SCHEMA)
    structural_requirements = merge_structural_requirements(
        question,
        response.get("structural_requirements") if isinstance(response.get("structural_requirements"), dict) else {},
        assignment_text,
    )
    return SuggestionResult(
        status=str(response.get("status", "no_supported_checker")),
        question=question,
        checker=response.get("checker"),
        config=response.get("config") if isinstance(response.get("config"), dict) else {},
        confidence=float(response.get("confidence", 0.0) or 0.0),
        reason=str(response.get("reason", "")),
        structural_requirements=structural_requirements,
    )


def merge_structural_requirements(question: str, existing: dict | None, assignment_text: str = "") -> dict:
    merged = dict(existing or {})
    inferred = infer_structural_requirements(question, assignment_text)
    if not inferred:
        normalize_structural_requirement_flags(merged)
        return merged

    if not (merged.get("requires_recursion") or merged.get("forbid_loops")):
        normalize_structural_requirement_flags(inferred)
        return inferred

    for key, value in inferred.items():
        if merged.get(key) in (None, "", [], {}):
            merged[key] = value
    normalize_structural_requirement_flags(merged)
    return merged


def normalize_structural_requirement_flags(requirements: dict):
    deduction = requirements.get("deduction", requirements.get("penalty"))
    try:
        float(deduction)
    except (TypeError, ValueError):
        return
    requirements["deduction_required"] = False


def infer_structural_requirements(question: str, assignment_text: str = "") -> dict:
    normalized = " ".join(str(assignment_text or "").lower().split())
    has_recursion_requirement = any(
        phrase in normalized
        for phrase in [
            "recursion",
            "recursive",
            "non-recursive",
            "רקורס",
        ]
    )
    if not has_recursion_requirement:
        return {}

    zero_deduction = any(
        phrase in normalized
        for phrase in [
            "will receive credit",
            "will not receive credit",
            "receive 0",
            "gets 0",
            "get 0",
            "יקבל 0",
            "0 !",
            "0!",
        ]
    )
    question_number = question_number_from_name(question)
    requirements = {
        "requires_recursion": True,
        "entry_functions": [f"q_{question_number}"] if question_number is not None else [],
        "allow_recursive_helpers": True,
        "forbid_loops": "loop" in normalized or "for/while" in normalized or "while" in normalized or "for" in normalized,
        "deduction_required": not zero_deduction,
        "reason": "Assignment text requires recursive implementation.",
    }
    if zero_deduction:
        requirements["deduction"] = 100
        requirements["deduction_required"] = False
        requirements["reason"] = "Assignment states non-recursive solutions receive 0."
    else:
        requirements["deduction"] = None
    return requirements


def run_checker_tests(checker_config: dict, inputs_and_expected: list[tuple[str, str]], max_cases: int = 8) -> list[dict]:
    rows = []
    for input_value, expected_output in inputs_and_expected[:max_cases]:
        variants = [
            ("exact", expected_output),
            ("prompted", f"Input: {input_value}\nOutput: {expected_output}"),
            ("wrong", "0"),
        ]
        for variant_name, actual_output in variants:
            comparison = compare_output_with_config(checker_config, input_value, expected_output, actual_output)
            rows.append(
                {
                    "input": input_value,
                    "variant": variant_name,
                    "expected_output": expected_output,
                    "actual_output": actual_output,
                    "passed": comparison.passed,
                    "reason": comparison.reason,
                    "expected_canonical": comparison.expected_canonical,
                    "actual_canonical": comparison.actual_canonical,
                }
            )
    return rows


def select_audit_cases(questions: list[str], max_cases: int = 15) -> list[AuditCase]:
    cases_by_bucket = _empty_audit_buckets()
    cases_by_question = {question: _empty_audit_buckets() for question in questions}
    final_df = _read_excel_if_exists("final_grades.xlsx")
    final_by_id = _rows_by_id(final_df)

    for question in questions:
        grade_excel = os.path.join(question, f"{question}_grades_to_upload.xlsx")
        question_df = _read_excel_if_exists(grade_excel)
        for _, row in question_df.iterrows():
            case = _make_audit_case(question, row, final_by_id)
            _add_case_to_buckets(cases_by_bucket, case)
            _add_case_to_buckets(cases_by_question[question], case)

    selected = []
    if max_cases >= len(questions):
        for question in questions:
            question_pick = _take_bucketed_cases(cases_by_question[question], 1)
            if question_pick and len(selected) < max_cases:
                selected.append(question_pick[0])

    return _take_bucketed_cases(cases_by_bucket, max_cases, selected)


def _empty_audit_buckets() -> dict[str, list[AuditCase]]:
    return {
        "perfect": [],
        "high": [],
        "medium": [],
        "low": [],
        "zero": [],
        "penalty": [],
        "compile_timeout": [],
    }


def _make_audit_case(question: str, row: pd.Series, final_by_id: dict[str, dict]) -> AuditCase:
    student_id = str(row.get("ID_number", ""))
    score = float(row.get("Grade", 0) or 0)
    return AuditCase(
        student_id=student_id,
        question=question,
        score=score,
        grade_text=_read_optional_text(os.path.join(question, "grade", f"{student_id}.txt")),
        output_text=_read_optional_text(os.path.join(question, "output", f"{student_id}.txt")),
        excel_fields=row.to_dict(),
        final_fields=final_by_id.get(student_id, {}),
    )


def _add_case_to_buckets(cases_by_bucket: dict[str, list[AuditCase]], case: AuditCase):
    for bucket in _case_buckets(case):
        cases_by_bucket[bucket].append(case)


def _take_bucketed_cases(
    cases_by_bucket: dict[str, list[AuditCase]],
    max_cases: int,
    selected: list[AuditCase] | None = None,
) -> list[AuditCase]:
    selected = list(selected or [])
    while len(selected) < max_cases and any(cases_by_bucket.values()):
        for bucket in cases_by_bucket:
            if cases_by_bucket[bucket] and len(selected) < max_cases:
                candidate = cases_by_bucket[bucket].pop(0)
                if candidate not in selected:
                    selected.append(candidate)
    return selected


def audit_cases_with_llm(
    cases: list[AuditCase],
    checker_configs: dict[str, dict],
    provider: LLMProvider,
    assignment_context: AssignmentContext | str = "",
    max_workers: int = 4,
    progress_callback=None,
) -> list[AuditResult]:
    results = []
    if isinstance(assignment_context, str):
        assignment_context = AssignmentContext(text=assignment_context)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_audit_one_case, case, checker_configs.get(case.question, {}), provider, assignment_context): case
            for case in cases
        }
        total = len(futures)
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if progress_callback:
                progress_callback(result, len(results), total)
    return sorted(results, key=lambda item: (item.question, item.student_id))


def _audit_one_case(case: AuditCase, checker_config: dict, provider: LLMProvider, assignment_context: AssignmentContext) -> AuditResult:
    focused_context = assignment_context_for_question(assignment_context, case.question)
    prompt = build_audit_prompt(case, checker_config, focused_context.text, focused_context.images)
    try:
        response = _complete_audit_json_with_retry(provider, prompt, focused_context.images)
        verdict = str(response.get("verdict", "uncertain"))
        risk = str(response.get("risk", "medium"))
        reason = str(response.get("reason", ""))
        status = "passed" if verdict == "looks_correct" else "flagged"
    except Exception as exc:
        verdict = "error"
        risk = "high"
        reason = str(exc)
        status = "error"
    return AuditResult(case.student_id, case.question, status, verdict, risk, reason)


def _complete_audit_json_with_retry(
    provider: LLMProvider,
    prompt: str,
    images: list[AssignmentImage] | tuple[AssignmentImage, ...] | None = None,
) -> dict:
    try:
        return complete_json_with_schema(provider, prompt, images, AUDIT_RESPONSE_SCHEMA)
    except Exception as first_error:
        retry_prompt = (
            f"{prompt}\n\n"
            "The previous response could not be parsed as JSON. Return one valid JSON object only, with no markdown, "
            "no comments, and no trailing text. Required keys: verdict, risk, reason."
        )
        try:
            return complete_json_with_schema(provider, retry_prompt, images, AUDIT_RESPONSE_SCHEMA)
        except Exception as second_error:
            raise RuntimeError(f"{first_error}; retry failed: {second_error}") from second_error


def build_audit_prompt(
    case: AuditCase,
    checker_config: dict,
    assignment_text: str = "",
    assignment_images: list[AssignmentImage] | tuple[AssignmentImage, ...] | None = None,
) -> str:
    return json.dumps(
        {
            "task": "audit_score",
            "role": "You are auditing deterministic C homework grading results. You do not assign a new grade.",
            "student_id": case.student_id,
            "question": case.question,
            "target_question_number": question_number_from_name(case.question),
            "assignment_text_for_selected_question_optional": assignment_text,
            "assignment_images_for_selected_question_optional": [image.label for image in assignment_images or []],
            "eval_cases": CHECKER_AUDIT_EVAL_CASES,
            "checker_config": checker_config,
            "assigned_score": case.score,
            "grade_text": case.grade_text[:12000],
            "student_output": case.output_text[:12000],
            "per_question_excel_fields": case.excel_fields,
            "final_excel_fields": case.final_fields,
            "instructions": (
                f"Focus only on {case.question}. If assignment text or images contain multiple questions, ignore other "
                "question sections. Check whether the assigned score and Excel fields are consistent with the grade text, "
                "student output, checker configuration, and selected-question assignment intent. Verify comments, penalties, compile-error flags, timeout "
                "fields, wrong-input fields, structural recursion/loop check fields, structural penalties, and final weighted grade fields "
                "when present. Do not change the grade. "
                "Return looks_correct only when the fields are internally consistent and the grading decision appears "
                "reasonable. Return flagged for likely scoring/Excel mistakes. Return uncertain when more human review "
                "is needed."
            ),
            "response_schema": {
                "verdict": "looks_correct | flagged | uncertain",
                "risk": "low | medium | high",
                "reason": "one short plain-text sentence under 350 characters; no newlines",
            },
            "strict_json_rules": (
                "Return exactly one JSON object with exactly the keys verdict, risk, and reason. "
                "The reason value must be one JSON string: escape quotes and do not include markdown, lists, nested objects, or line breaks."
            ),
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _read_excel_if_exists(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_excel(path, dtype={"ID_number": str}).fillna("")


def _rows_by_id(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "ID_number" not in df.columns:
        return {}
    return {str(row["ID_number"]): row.to_dict() for _, row in df.iterrows()}


def _read_optional_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="ignore") as text_file:
        return text_file.read()


def _case_buckets(case: AuditCase) -> list[str]:
    buckets = []
    if case.score >= 100:
        buckets.append("perfect")
    elif case.score >= 80:
        buckets.append("high")
    elif case.score >= 50:
        buckets.append("medium")
    elif case.score > 0:
        buckets.append("low")
    else:
        buckets.append("zero")
    if case.final_fields.get("Penalty Applied"):
        buckets.append("penalty")
    if case.excel_fields.get("Compilation_Error") or case.excel_fields.get("Timeouts"):
        buckets.append("compile_timeout")
    return buckets
