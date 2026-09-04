# Display BOM AI Agent Evaluation

`evaluation/`은 Agent Ground Truth, Runtime Observation, domain-specific quality gate를 관리합니다.

## Dataset Policy

두 dataset을 구분합니다.

- `evaluation/datasets/agent_eval_v1.jsonl`: 기존 50 Cases / 58 Turns regression baseline
- `evaluation/datasets/agent_eval_v2.jsonl`: `v4.0.0` Release 기준 56 Cases / 69 Turns

v2는 기존 baseline을 보존하면서 Knowledge, Text-to-SQL, Read-only Composition, Workflow Composition, Scope Conflict 경로를 추가합니다.

Ground Truth는 Intent, Hybrid Execution Path, Interaction, Action, Primary Tool, Required Entity, Candidate Status/Ranking Policy, Safety Assertion을 포함합니다.

## Dynamic Fixture / Observation

`EvaluationFixtureResolver`가 현재 검증 DB의 활성 BOM을 분석해 평가 Fixture를 동적으로 선택합니다. 특정 MODEL / MATERIAL / Scenario ID를 Runtime 분기에 하드코딩하지 않습니다.

Agent Evaluation은 Runtime `data/display_bom.db`를 직접 변경하지 않고 Disposable Evaluation DB를 사용합니다.

Runtime Observation은 Intent, Gateway Route, Execution Path, Tool Name/Arguments, Workflow State, Active BOM Context, Error, End-to-End Latency, LLM Call/Token, Timing Evidence를 수집합니다.

기본 산출물은 `.perf/evaluation/` 아래에 생성되며 Git 대상이 아닙니다.

## FINAL-02 Quality Gate

현재 Agent 품질 Gate의 실제 Runtime 기준은 `agent_eval_v2.jsonl`입니다.

```powershell
python -m scripts.validate_final_02_evaluation_foundation

python -m scripts.run_rag_retrieval_evaluation `
  --rebuild-index `
  --strict `
  --output .perf/evaluation/rag_report.json

python -m scripts.run_text_to_sql_generation_evaluation `
  --strict `
  --output .perf/evaluation/text_to_sql_report.json

python -m scripts.collect_agent_evaluation_observations `
  --dataset evaluation/datasets/agent_eval_v2.jsonl `
  --all

python -m scripts.evaluate_agent_accuracy `
  --dataset evaluation/datasets/agent_eval_v2.jsonl `
  --require-complete

python -m scripts.evaluate_agent_performance `
  --dataset evaluation/datasets/agent_eval_v2.jsonl `
  --require-complete

python -m scripts.evaluate_agent_safety `
  --dataset evaluation/datasets/agent_eval_v2.jsonl `
  --require-complete

python -m scripts.finalize_final_02_evaluation --run-tests --require-tests
```

Gate 기준:

- Foundation PASS
- Intent / Route / Tool Selection / Tool Argument Accuracy = 100%
- Safety = 100%, failed assertion = 0
- P95 latency <= 5,000ms
- RAG Retrieval Gate PASS
- Text-to-SQL Generation Gate PASS
- Full Regression PASS
- Accuracy / Performance / Safety가 같은 observation run에서 생성

`<=5s turn rate`와 `LLM-free rate`는 diagnostic metric입니다.

## v4.0.0 Verified Result

```text
Agent Cases / Turns       56 / 69
Intent Accuracy           100.00%
Route Accuracy            100.00%
Tool Selection Accuracy   100.00%
Tool Argument Accuracy    100.00%
Planner Accuracy          100.00% (6/6)
Context Gate              13/13
Safety                    167/167
P95 Latency               3314.59ms
RAG Gate                  PASS
Text-to-SQL Gate          PASS
Full Regression           737/737 PASS
```

Accuracy 100%는 정의된 Ground Truth Dataset에 대한 conformance이지 범용 실세계 정확도를 의미하지 않습니다.

## FINAL-03 Release Freeze

FINAL-03는 FINAL-02 결과를 품질 근거로 재사용하되 문서 / repository hygiene / deterministic release contract와 마지막 Full Regression을 다시 검증합니다.

```powershell
python -m scripts.validate_final_03_release_freeze
python -m scripts.finalize_final_03_release --run-tests --require-tests
```

기본 산출물:

- `.perf/evaluation/final03_freeze_validation.json`
- `.perf/evaluation/final03_release_report.json`
- `.perf/evaluation/final03_release_report.md`

## Legacy Evaluation Gate

`evaluation/release_gate.py`와 `scripts/finalize_agent_evaluation.py`는 기존 50-case/58-turn baseline의 역사적 release gate를 재현하기 위해 보존합니다. 현재 `v4.0.0` Release 판정에는 `final02_gate.py`와 FINAL-03 release gate를 사용합니다.
