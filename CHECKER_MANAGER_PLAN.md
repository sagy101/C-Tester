# Checker Manager And LLM Audit Plan

## Goals

Add a GUI workflow for selecting, saving, testing, and auditing semantic checkers without making grading depend on arbitrary LLM-written code. The default grader remains deterministic and reproducible.

## Core Concepts

1. Checker templates are deterministic, pre-existing implementations.
2. A custom checker is a saved template plus configuration, not arbitrary Python by default.
3. The LLM receives the available templates and configuration schemas, then selects/configures one or returns `no_supported_checker`.
4. The assignment PDF/Word text is optional. If provided, it is parsed and included in the LLM context.
5. Student outputs are not sent during checker suggestion because they only exist after grading.
6. After grading, sampled student results can be audited by LLM calls in parallel.

## Checker Manager Screen

Open from a new main-screen button: `Checker Manager`.

The screen contains:
- question selector/table
- current checker mode and JSON config
- optional assignment file path
- `Suggest with LLM`
- `Test Checker`
- `Save Checker`
- `Run Audit`
- status/results table

## Checker Suggestion Flow

For one selected question, gather:
- available checker templates and config schemas
- current checker config, if any
- `original_sol.c`
- `input.txt`
- expected outputs generated from `original_sol.c`
- optional parsed assignment text

Send this to the LLM provider. The LLM returns structured JSON:

```json
{
  "status": "supported",
  "question": "Q1",
  "checker": "integer_list",
  "config": {"order_matters": true, "allow_prompt_numbers": true},
  "confidence": 0.9,
  "reason": "The task asks for divisors in ascending order."
}
```

or:

```json
{
  "status": "no_supported_checker",
  "reason": "The answer requires custom stateful validation that no template supports."
}
```

The proposal is displayed and is only applied after the user clicks `Save Checker`.

## Checker Tests

`Test Checker` runs deterministic checks for the selected question:
- exact expected output
- generated prompt/noise variants
- clearly wrong outputs
- edge inputs from `input.txt`

Each row shows expected output, synthetic/student-like output, parsed expected, parsed actual, pass/fail, and reason.

## LLM Audit Flow

`Run Audit` runs after grading and samples 10-15 students distributed by:
- 100 scores
- high scores
- medium scores
- low non-zero scores
- zeros
- penalties
- compile errors
- timeout cases

For each sampled student/question, send:
- optional assignment text
- checker template/config
- selected input cases
- intended output
- student output
- parsed expected/actual
- assigned score
- grade text fields
- per-question Excel fields
- final Excel fields and penalty/comment fields

Run audit calls in parallel with a small concurrency limit. The GUI shows each student row as `waiting`, `running`, `passed`, `flagged`, or `error`.

The overall result is:
- green when all sampled reviews pass
- yellow when there are uncertain/error reviews
- red when one or more reviews are flagged

The LLM audit is advisory. Deterministic checkers remain the source of grades.

## Verification Stage

Create a temporary dummy homework outside committed files:
- two question folders
- original solutions
- input files
- around 20 dummy student outputs/grade rows representing 100, high, medium, low, zero, penalty, compile-error, and timeout cases

Verify:
- Checker Manager can save/load checker configs.
- LLM suggestion can select/configure existing templates using a fake deterministic LLM provider.
- `Test Checker` returns expected pass/fail rows.
- audit sampling includes multiple score buckets.
- fake LLM audit reviews run in parallel and produce row statuses plus an overall result.
- generated Excel fields remain consistent with grade text and final calculations.

Do not commit dummy homework, dummy students, generated grade files, generated Excel files, zips, or build artifacts.
