# Display BOM AI Agent v4.0.0 Release Freeze

## Release Scope

`v4.0.0`은 다음 기능이 하나의 Single Agent Runtime으로 통합된 Release입니다.

- Hybrid routing: Fast / Macro / Agent
- RAG Knowledge Evidence
- Read-only Text-to-SQL
- Read-only / Workflow Composition
- Active BOM / Workflow Context separation
- BOM Edge Ontology + exact Parent / LOCATION provenance
- Scope Conflict guard
- REPLACE / ADD / DELETE / QUANTITY_CHANGE Analysis
- Analysis Session / Request lifecycle separation
- HITL approval + Preview + Atomic Apply
- Deterministic Agent Evaluation / Safety / Performance gate

## Release Lineage

주요 기준 commit:

```text
v3.1.1 Clean Core baseline : ab650c8
PLAN-04 Runtime Composition: 34536d0
PLAN-05 Generalization     : f48bef6
FINAL-01 Context/Ontology  : 89dce7a
FINAL-02 Eval/Stability    : 9f5a210
FINAL-03 Release Freeze    : v4.0.0 tag target
```

`v4.0.0` tag는 FINAL-03 문서 / repository hygiene / release gate를 통과한 Release commit에 생성합니다.

## FINAL-02 Quality Evidence

FINAL-03의 품질 기준은 FINAL-02에서 생성한 동일 observation run의 결과를 사용합니다.

```text
Run ID                    evaluation-13d2ccbbbbdf
Agent Cases / Turns       56 / 69
Intent Accuracy           100.00%
Route Accuracy            100.00%
Tool Selection Accuracy   100.00%
Tool Argument Accuracy    100.00%
Planner Accuracy          100.00% (6/6)
Context Gate              13/13
Architecture Validators   6/6
Safety Assertions         167/167
Safety Violations         0
Average Latency            808.02ms
P95 Latency               3314.59ms
<=5s Turn Rate            95.65% (diagnostic)
LLM-free Turn Rate        85.51% (diagnostic)
RAG Retrieval Gate        PASS
Text-to-SQL Gate          PASS
Full Regression           737/737 PASS
UI Acceptance             PASS
```

### RAG Retrieval

```text
Cases                      56
Hit Rate@1                 94.64%
Hit Rate@3                 100.00%
Hit Rate@5                 100.00%
Mean Recall@5              100.00%
MRR                        0.9702
Metadata Filter Accuracy   100.00%
P95 Retrieval Latency      176.83ms
```

### Text-to-SQL

```text
Cases                      23
Passed                     23/23
Overall Accuracy           100.00%
Status Accuracy            100.00%
Execution Success          100.00%
Semantic Result Match      100.00%
UNSUPPORTED Accuracy       100.00%
P95 Generation Latency     1720.17ms
```

## Safety Boundary

FINAL-02 / FINAL-03는 다음 권한을 새로 부여하지 않습니다.

```text
Request creation authority outside approved workflow : NO
Approval authority in analysis/evaluation layer      : NO
Production BOM write authority                       : NO
```

Production E-BOM 변경은 기존 승인 Workflow와 Atomic Apply 경계만 사용합니다.

## Final Release Commands

FINAL-03 package 적용 후:

```powershell
python -m scripts.validate_final_03_release_freeze
python -m scripts.run_tests --suite quick -q
python -m scripts.finalize_final_03_release --run-tests --require-tests
```

Release Gate가 PASS한 후에만 source/docs를 명시적으로 stage하고 commit합니다.

그 다음:

```powershell
git tag -a v4.0.0 -m "Display BOM AI Agent v4.0.0"
git push origin HEAD
git push origin v4.0.0
```

최종 확인:

```powershell
git rev-parse HEAD
git rev-list -n 1 v4.0.0
git ls-remote --heads origin <release-branch>
git ls-remote --tags origin v4.0.0
```

Local HEAD, remote branch, local tag, remote tag가 모두 동일 commit이어야 Freeze가 완료됩니다.

## Repository Hygiene

Release commit에서 제외:

- `.env` / Secret
- `.perf/`
- `artifacts/`
- `data/rag/`
- Runtime DB / DB backup
- patch / migration backup workspace
- Python cache / pytest temp
- local evaluator latest output

## Legacy Compatibility

기존 `evaluation/release_gate.py`와 `scripts/finalize_agent_evaluation.py`의 `v3.1.1` 표기는 과거 50-case/58-turn baseline 재현을 위한 legacy contract이므로 제거하지 않습니다. 현재 Release 판단은 FINAL-02 + FINAL-03 gate를 사용합니다.
