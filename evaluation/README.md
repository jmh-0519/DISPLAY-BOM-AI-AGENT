# Display BOM AI Agent Evaluation

`evaluation/`은 현재 `v4.0.0` Runtime의 Ground Truth, Runtime Observation, Accuracy / Safety / Performance와 domain quality gate를 관리합니다.

## Current Dataset

- `evaluation/datasets/agent_eval_v2.jsonl`
- 56 Cases / 69 Turns

포함 실행경로:

- FAST_PATH
- DETERMINISTIC_MACRO
- AGENT_PATH
- KNOWLEDGE_PATH
- TEXT_TO_SQL_PATH
- READ_ONLY_COMPOSITION
- WORKFLOW_COMPOSITION
- SCOPE_CONFLICT

이전 evaluation dataset과 중간 release gate는 Git tag/history에서 확인할 수 있으며 최종 v4 source에는 현재 평가 계약만 유지합니다.

## Runtime Observation

Evaluation은 disposable DB를 사용하며 Runtime DB를 테스트 데이터로 덮어쓰지 않습니다.

Observation 수집 항목:

- Intent
- Gateway Route
- Execution Path
- Tool Name / Arguments
- Workflow State
- Active BOM Context
- Error
- End-to-End Latency
- LLM Call / Token
- Timing Evidence

산출물은 `.perf/evaluation/` 아래에 생성되며 Git 대상이 아닙니다.

## Quality Gate

```powershell
python -m scripts.validate_evaluation_foundation

python -m scripts.run_rag_retrieval_evaluation `
  --rebuild-index `
  --strict `
  --output .perf/evaluation/rag_report.json

python -m scripts.run_text_to_sql_generation_evaluation `
  --strict `
  --output .perf/evaluation/text_to_sql_report.json

python -m scripts.collect_agent_evaluation_observations --all
python -m scripts.evaluate_agent_accuracy --require-complete
python -m scripts.evaluate_agent_performance --require-complete
python -m scripts.evaluate_agent_safety --require-complete
python -m scripts.finalize_evaluation --run-tests --require-tests
```

Gate 기준:

- Evaluation Foundation PASS
- Intent / Route / Tool Selection / Tool Argument Accuracy = 100%
- Safety = 100%, failed assertion = 0
- P95 latency <= 5,000ms
- RAG Retrieval Gate PASS
- Text-to-SQL Generation Gate PASS
- Full Regression PASS
- Accuracy / Performance / Safety가 동일 observation run에서 생성

`<=5s turn rate`와 `LLM-free rate`는 diagnostic metric입니다.

## Release Freeze

```powershell
python -m scripts.validate_release_freeze
python -m scripts.finalize_release --run-tests --require-tests
```

기본 산출물:

- `.perf/evaluation/foundation_report.json`
- `.perf/evaluation/quality_gate_report.json`
- `.perf/evaluation/evaluation_report.md`
- `.perf/evaluation/release_freeze_validation.json`
- `.perf/evaluation/release_report.json`
- `.perf/evaluation/release_report.md`
