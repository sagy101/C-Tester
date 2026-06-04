"""LLM-assisted checker suggestion and audit helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import html
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
from typing import Any, Protocol

import pandas as pd

from semantic_grading import available_checker_templates, compare_output_with_config


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


@dataclass(frozen=True)
class SuggestionResult:
    status: str
    question: str
    checker: str | None
    config: dict
    confidence: float
    reason: str


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


class LLMProvider(Protocol):
    def complete_json(self, prompt: str) -> dict:
        """Return a JSON object from an LLM prompt."""


class GeminiProvider:
    """Small Gemini REST client using GOOGLE_API_KEY by default."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set")

    def complete_json(self, prompt: str) -> dict:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:"
            f"generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
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
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini request failed: {exc}") from exc

        text = body["candidates"][0]["content"]["parts"][0]["text"]
        return parse_json_object(text)


def list_gemini_models(api_key: str | None = None) -> list[str]:
    key = api_key or os.getenv("GOOGLE_API_KEY")
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


class FakeLLMProvider:
    """Deterministic provider for tests and offline demos."""

    def complete_json(self, prompt: str) -> dict:
        lower_prompt = prompt.lower()
        if '"task": "audit_score"' in lower_prompt:
            return {
                "verdict": "looks_correct",
                "risk": "low",
                "reason": "Deterministic fake provider accepts the supplied audit package.",
            }
        if "divisor" in lower_prompt:
            return {
                "status": "supported",
                "checker": "divisors",
                "config": {"allow_prompt_numbers": True, "zero_requires_no_divisors_message": True},
                "confidence": 0.9,
                "reason": "The expected outputs describe divisors.",
            }
        if "reverse" in lower_prompt:
            return {
                "status": "supported",
                "checker": "reverse_integer",
                "config": {"answer_position": "last_integer"},
                "confidence": 0.9,
                "reason": "The expected outputs describe reversing an integer.",
            }
        return {
            "status": "no_supported_checker",
            "checker": None,
            "config": {},
            "confidence": 0.0,
            "reason": "No deterministic fake match found.",
        }


def parse_json_object(text: str) -> dict:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def parse_assignment_file(path: str | None) -> str:
    if not path:
        return ""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in {".txt", ".md", ".csv"}:
        with open(path, "r", encoding="utf-8", errors="ignore") as text_file:
            return text_file.read()
    if ext == ".docx":
        return parse_docx_text(path)
    if ext == ".pdf":
        return parse_pdf_text_best_effort(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as text_file:
        return text_file.read()


def parse_docx_text(path: str) -> str:
    with zipfile.ZipFile(path) as docx:
        xml = docx.read("word/document.xml").decode("utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", " ", xml)
    return html.unescape(" ".join(text.split()))


def parse_pdf_text_best_effort(path: str) -> str:
    with open(path, "rb") as pdf_file:
        data = pdf_file.read()
    return data.decode("utf-8", errors="ignore")


def build_suggestion_prompt(
    question: str,
    original_code: str,
    inputs: list[str],
    expected_outputs: list[tuple[str, str]],
    assignment_text: str = "",
) -> str:
    payload = {
        "task": "suggest_checker",
        "role": "You are configuring a deterministic C homework output checker. You do not grade students and you do not write code.",
        "question": question,
        "available_checkers": available_checker_templates(),
        "original_solution_c": original_code,
        "inputs": inputs,
        "expected_outputs": [{"input": value, "output": output} for value, output in expected_outputs],
        "assignment_text_optional": assignment_text,
        "instructions": (
            "Infer the intended answer and output format from the assignment text when present, the reference C code, "
            "the test inputs, and the reference outputs. Select exactly one available checker template and only supported "
            "configuration options. Prefer the simplest checker that validates the semantic answer while ignoring harmless "
            "prompts/labels/spacing. Do not invent code, regular expressions, checker names, or unsupported options. "
            "If no available checker can safely validate the task, return status no_supported_checker. When uncertain, "
            "lower confidence and explain what manual review is needed."
        ),
        "decision_guidance": {
            "exact": "Use only when exact output format is required.",
            "normalized_text": "Use for mostly textual answers where case/punctuation are irrelevant.",
            "last_integer": "Use for tasks with one numeric answer at the end, such as factorial, sum, max, count, gcd, or lcm.",
            "integer_list": "Use for sequences/lists like Fibonacci, primes, sorted arrays, or printed array values.",
            "divisors": "Use only for divisor-list tasks.",
            "reverse_integer": "Use only for reversing integer digits.",
        },
        "response_schema": {
            "status": "supported | no_supported_checker",
            "checker": "checker name or null",
            "config": "object",
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
) -> SuggestionResult:
    prompt = build_suggestion_prompt(question, original_code, inputs, expected_outputs, assignment_text)
    response = provider.complete_json(prompt)
    return SuggestionResult(
        status=str(response.get("status", "no_supported_checker")),
        question=question,
        checker=response.get("checker"),
        config=response.get("config") if isinstance(response.get("config"), dict) else {},
        confidence=float(response.get("confidence", 0.0) or 0.0),
        reason=str(response.get("reason", "")),
    )


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
    final_df = _read_excel_if_exists("final_grades.xlsx")
    final_by_id = _rows_by_id(final_df)

    for question in questions:
        grade_excel = os.path.join(question, f"{question}_grades_to_upload.xlsx")
        question_df = _read_excel_if_exists(grade_excel)
        for _, row in question_df.iterrows():
            _add_case_to_buckets(cases_by_bucket, _make_audit_case(question, row, final_by_id))

    return _take_bucketed_cases(cases_by_bucket, max_cases)


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


def _take_bucketed_cases(cases_by_bucket: dict[str, list[AuditCase]], max_cases: int) -> list[AuditCase]:
    selected = []
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
    assignment_text: str = "",
    max_workers: int = 4,
    progress_callback=None,
) -> list[AuditResult]:
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_audit_one_case, case, checker_configs.get(case.question, {}), provider, assignment_text): case
            for case in cases
        }
        total = len(futures)
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if progress_callback:
                progress_callback(result, len(results), total)
    return sorted(results, key=lambda item: (item.question, item.student_id))


def _audit_one_case(case: AuditCase, checker_config: dict, provider: LLMProvider, assignment_text: str) -> AuditResult:
    prompt = build_audit_prompt(case, checker_config, assignment_text)
    try:
        response = provider.complete_json(prompt)
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


def build_audit_prompt(case: AuditCase, checker_config: dict, assignment_text: str = "") -> str:
    return json.dumps(
        {
            "task": "audit_score",
            "role": "You are auditing deterministic C homework grading results. You do not assign a new grade.",
            "student_id": case.student_id,
            "question": case.question,
            "assignment_text_optional": assignment_text,
            "checker_config": checker_config,
            "assigned_score": case.score,
            "grade_text": case.grade_text[:12000],
            "student_output": case.output_text[:12000],
            "per_question_excel_fields": case.excel_fields,
            "final_excel_fields": case.final_fields,
            "instructions": (
                "Check whether the assigned score and Excel fields are consistent with the grade text, student output, "
                "checker configuration, and assignment intent. Verify comments, penalties, compile-error flags, timeout "
                "fields, wrong-input fields, and final weighted grade fields when present. Do not change the grade. "
                "Return looks_correct only when the fields are internally consistent and the grading decision appears "
                "reasonable. Return flagged for likely scoring/Excel mistakes. Return uncertain when more human review "
                "is needed."
            ),
            "response_schema": {
                "verdict": "looks_correct | flagged | uncertain",
                "risk": "low | medium | high",
                "reason": "specific reason grounded in the provided fields",
            },
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
