# Robust Grading Plan

## Goal

Make grading tolerant of harmless output-format differences while keeping the checks conservative enough to avoid false credit. Generated student files, grade text files, build artifacts, zips, and Excel outputs stay local and are not committed.

## Implementation

1. Add per-question semantic checkers instead of one global fuzzy comparison.
   - `Q1`: parse the answer as a divisor list and compare it to the mathematically expected divisors for the input.
   - `Q2`: parse the answer as the reversed number and compare it to the mathematically expected reverse for the input.
2. Keep exact matching as a valid fast path.
3. Treat ambiguous or unparsable output as incorrect.
4. Preserve compile errors, runtime errors, timeouts, wrong-input lists, timeout-input lists, and Excel column names.
5. Add audit information to grade text files so changed scores can be reviewed:
   - expected output
   - actual output
   - semantic reason
   - parsed expected value
   - parsed actual value

## Verification

1. Add focused unit tests for semantic checkers:
   - exact reference output
   - output with prompts and labels
   - punctuation and casing changes
   - wrong numeric answer
   - partial divisor lists
   - reordered divisors
   - prompt-only output
   - timeout/runtime/error strings
2. Regenerate local grading artifacts from `hw1_2026.zip`.
3. Validate generated Excel files:
   - per-question row counts match generated grade files, excluding examples
   - `Grade` values match the corresponding grade text files
   - compilation-error flags match grade text files
   - wrong-input and timeout-input columns match grade text summaries
   - final weighted grades match configured weights and penalties
   - comments contain failed cases, timeout cases, and penalty notes when applicable
4. Generate or inspect an audit summary of changed cases, especially:
   - old zero to new high score
   - still-low scores
   - compile errors
   - preprocessing penalties
   - edge inputs such as `0`, one-digit values, palindromes, and trailing-zero reversals
5. Use a separate cheap sub-agent to independently verify all generated scores and Excel fields per student from the local artifacts before commit.

## Commit Scope

Commit only source and plan changes. Do not commit `hw1_2026.zip`, `Q*/C/*`, `Q*/grade/*`, `Q*/output/*`, `*.xlsx`, `*.exe`, `*.obj`, or other generated artifacts.
