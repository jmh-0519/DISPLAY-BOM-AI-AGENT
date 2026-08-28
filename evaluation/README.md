# Display BOM AI Agent Evaluation

`evaluation/`은 v3.1.0 Agent Evaluation의 Ground Truth와 Runtime Observation을 관리합니다.

## AE-01 — Evaluation Dataset

- 50개 평가 Case / 58개 Turn
- Runtime 코드에 특정 MODEL / MATERIAL / Scenario ID 하드코딩 금지
- Query는 `{{MODEL_A}}`, `{{PLANT_A}}` 등의 Fixture Template 사용
- Ground Truth:
  - Intent
  - Hybrid Execution Path
  - Interaction
  - Action
  - Primary Tool
  - Required Entity
  - Candidate Status/Ranking Policy
  - Safety Assertion

```powershell
python -m scripts.validate_agent_evaluation_dataset
```

## AE-02 — Dynamic Fixture / Runtime Observation

### Dynamic Fixture

`EvaluationFixtureResolver`가 현재 검증 DB의 활성 BOM을 분석하여 실제 평가값을 선택합니다.

- MODEL_A / MODEL_B
- PLANT_A / PLANT_B
- MATERIAL_A / B / C
- Material Name / Family
- ASSY Parent / Target Name
- 존재하지 않는 Invalid Entity

평가 Dataset은 샘플코드가 바뀌어도 동일한 평가 의미를 유지합니다.

```powershell
python -m scripts.resolve_agent_evaluation_fixtures
```

### Evaluation DB Sandbox

Agent Evaluation은 Runtime `data/display_bom.db`를 직접 사용하지 않습니다.

```text
Runtime DB
   ↓ copy
Disposable Evaluation DB
   ↓
Agent Evaluation
   ↓
삭제
```

Analysis Session도 DB 이력을 생성할 수 있으므로 모든 자동 평가 실행은 DB Copy에서 수행합니다.

### Runtime Observation

AE-02 Collector는 PASS/FAIL을 판단하지 않고 실제 실행 Evidence만 수집합니다.

수집 항목:

- 실제 Intent
- Gateway Route
- `FAST_PATH / DETERMINISTIC_MACRO / AGENT_PATH`
- Tool Name / Arguments / Call ID
- Workflow State Before / After
- Request ID / Analysis ID
- Active BOM Context Before / After
- Plant Option
- Error
- End-to-End Latency
- LLM Call Count
- Prompt / Completion / Total Token
- Prompt Budget
- Graph Node Timing
- MCP Tool Timing

Runtime Observation은 `.perf/evaluation/` 아래 JSONL로 저장하며 Git 대상이 아닙니다.

예제 Smoke:

```powershell
python -m scripts.collect_agent_evaluation_observations `
  --case-id CHAT-001 `
  --case-id BOM_READ-001 `
  --case-id REPLACE-001
```

`REPLACE-001`은 Analysis Session을 실행하지만 Evaluation DB Sandbox를 사용하므로 실제 Runtime DB는 변경하지 않습니다.

## 역할 분리

```text
pytest
  → 코드 계약 / 회귀

Evaluation Ground Truth
  → 무엇이 정답인가

Runtime Observation
  → 실제로 무엇이 실행됐는가

Evaluator (AE-03+)
  → Ground Truth vs Observation 비교
```

AE-02에서는 아직 Accuracy 점수를 만들지 않습니다. 정식 점수 산출은 후속 Evaluator 단계에서 수행합니다.

## AE-03 Accuracy Evaluator

AE-03 compares the AE-01 Ground Truth with AE-02 runtime observations.

Metrics:

- Intent Accuracy
- Route Accuracy
- Tool Selection Accuracy
- Tool Argument Accuracy

Tool argument scoring is business-contract aware. It checks resolved MODEL/PLANT/item/action and quantity where the selected MCP capability requires them. Dynamic fixture names may resolve to concrete item codes at runtime and are accepted as equivalent evidence.

Full baseline:

```powershell
python -m scripts.collect_agent_evaluation_observations --all
python -m scripts.evaluate_agent_accuracy --require-complete
```

The report is written under `.perf/evaluation/` and remains a local evaluation artifact rather than a Git source file.

## AE-08 Safety / Workflow / Hallucination Evaluation

AE-08 extends runtime observations with deterministic safety evidence:

- protected SQLite table fingerprints before/after each turn;
- raw MCP Tool result payloads for candidate status/ranking and invalid-entity checks;
- workflow state before/after for context mutation and approval-gate checks.

The evaluator checks only the `safety_assertions` declared by AE-01. It does not
use an LLM judge and does not invent missing evidence. Old AE-02 observations
without AE-08 evidence must be re-collected before running the safety release
gate.
