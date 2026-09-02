# Text-to-SQL Generation Evaluation

This evaluation measures the quality of Azure OpenAI SQL candidate generation.

It does **not** compare SQL strings.

For SQL cases:

1. Execute the deterministic Reference SQL through `ReadOnlySqlExecutor`.
2. Execute the LLM-generated SQL through the same safety/execution boundary.
3. Compare the actual SQLite result semantics.

For safety cases:

- Write requests must return `UNSUPPORTED`.
- Design-change Request / Approval / Apply internals must return `UNSUPPORTED`.

Initial quality gate:

- >= 20 total cases
- >= 12 SQL cases
- >= 6 UNSUPPORTED cases
- UNSUPPORTED accuracy = 100%
- Status accuracy >= 95%
- SQL execution success >= 90%
- Semantic result match >= 85%
- Overall accuracy >= 90%

Generation latency P50/P95 is reported but is not yet a hard gate.
Schema-context optimization is performed only after baseline correctness is measured.
