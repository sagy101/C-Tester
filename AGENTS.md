# Agent Guidance

- Use `gemini-flash-latest` as the default Gemini model for this project unless the user or environment explicitly requests another available model.
- Keep real Gemini/API integration tests opt-in. They should require explicit environment flags and skip during normal deterministic test runs.
