# Display BOM AI Agent Evaluation

`evaluation/`은 Clean Core Agent Evaluation의 Ground Truth와 Runtime Evidence를 관리합니다.

## Evaluation Dataset

- 50개 평가 Case / 58개 Turn
- Runtime 코드에 특정 MODEL / MATERIAL / Scenario ID를 하드코딩하지 않음
- Query는 `{{MODEL_A}}`, `{{PLANT_A}}` 등의 Fixture Template 사용
- Ground Truth는 Intent, Hybrid Execution Path, Interaction, Action, Primary Tool, Required Entity, Candidate Status/Ranking Policy, Safety Assertion을 포함

```powershell
python -m scripts.validate_agent_evaluation_dataset
```

## Dynamic Fixture and Runtime Observation

`EvaluationFixtureResolver`가 현재 검증 DB의 활성 BOM을 분석해 실제 평가값을 선택합니다. 평가 Dataset은 샘플 코드가 바뀌어도 동일한 평가 의미를 유지합니다.

```powershell
python -m scripts.resolve_agent_evaluation_fixtures
```

Agent Evaluation은 Runtime `data/display_bom.db`를 직접 변경하지 않습니다. Runtime DB를 Disposable Evaluation DB로 복사해 실행하고 종료 후 삭제합니다.

Runtime Observation Collector는 PASS/FAIL을 판단하지 않고 실제 실행 Evidence만 수집합니다. 주요 수집 항목은 Intent, Gateway Route, Execution Path, Tool Name/Arguments, Workflow State, Request/Analysis ID, Active BOM Context, Error, End-to-End Latency, LLM Call/Token, Prompt Budget, Graph/MCP Timing입니다.

```powershell
python -m scripts.collect_agent_evaluation_observations --all
```

기본 산출물은 `.perf/evaluation/agent_observations.jsonl`과 `.perf/evaluation/agent_profile.jsonl`이며 Git 대상이 아닙니다.

## Accuracy Evaluation

Ground Truth와 Runtime Observation을 비교해 Intent, Route, Tool Selection, Tool Argument Accuracy를 계산합니다. Tool argument 평가는 선택된 MCP capability의 업무 계약을 기준으로 MODEL/PLANT/item/action/quantity를 검증합니다.

```powershell
python -m scripts.evaluate_agent_accuracy --require-complete
```

기본 산출물: `.perf/evaluation/accuracy_report.json`

## Failure Triage

Accuracy 실패를 진단용으로 분류하며 Ground Truth나 Accuracy 점수를 변경하지 않습니다.

```powershell
python -m scripts.triage_agent_accuracy
```

기본 산출물: `.perf/evaluation/accuracy_failure_triage.json`

## Performance Evaluation

Runtime Observation/Profile에서 latency, LLM/token efficiency, Hybrid execution-path 지표를 집계합니다.

```powershell
python -m scripts.evaluate_agent_performance
```

기본 산출물: `.perf/evaluation/performance_report.json`

## Safety / Workflow / Hallucination Evaluation

Safety 평가는 deterministic runtime evidence를 사용하며 LLM judge를 사용하지 않습니다. 보호 SQLite table fingerprint, raw MCP result, workflow state before/after를 근거로 Ground Truth의 `safety_assertions`만 평가합니다. Evidence가 없으면 통과로 간주하지 않고 재수집을 요구합니다.

```powershell
python -m scripts.evaluate_agent_safety --require-complete
```

기본 산출물: `.perf/evaluation/safety_report.json`

## Release Gate

Accuracy / Performance / Safety가 동일한 observation run에서 생성되었는지 확인하고 Accuracy, Safety, P95 latency와 선택적으로 Full Regression을 함께 검증합니다.

```powershell
python -m scripts.finalize_agent_evaluation --run-tests
```

기본 산출물은 `.perf/evaluation/release_gate_report.json`과 `.perf/evaluation/evaluation_report.md`입니다. Accuracy 100%는 현재 Ground Truth dataset에 대한 conformance이며 일반적인 실세계 정확도 100%를 의미하지 않습니다.
