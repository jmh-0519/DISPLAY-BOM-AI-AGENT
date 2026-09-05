# Display BOM AI Agent v4.0.0 Release

## 1. Release Status

`v4.0.0`은 Display BOM AI Agent 프로젝트의 최종 개발 완료 버전입니다.

이번 Release는 v3.0의 설계변경 End-to-End Core에 다음을 추가하여 업무형 AI Agent의 근거성, 분석 범위, Context 이해와 품질 검증 체계를 완성했습니다.

- RAG Knowledge Evidence
- Read-only Text-to-SQL
- Analytics / Knowledge Composition
- Evidence-driven Design Change Composition
- Ontology / Context Scope Understanding
- Agent Accuracy / Safety / Performance Evaluation
- Integrated Release Gate
- Repository / Documentation Cleanup

## 2. Final Quality Evidence

```text
Agent Cases / Turns       56 / 69
Intent Accuracy           100.00%
Route Accuracy            100.00%
Tool Selection Accuracy   100.00%
Tool Argument Accuracy    100.00%
Planner Accuracy          100.00% (6/6)
Context Gate              13/13
Safety                    167/167 PASS
Average Latency           808.02 ms
P95 Latency               3314.59 ms
<=5s Rate                 95.65% (diagnostic)
LLM-free Rate             85.51% (diagnostic)
RAG Retrieval             PASS
Text-to-SQL               PASS
Full Regression           743/743 PASS
UI Acceptance             PASS
```

Accuracy는 정의된 Ground Truth Dataset에 대한 conformance입니다.

## 3. RAG Evidence

```text
Cases                     56
Hit Rate@1                94.64%
Hit Rate@3                100.00%
Hit Rate@5                100.00%
Mean Recall@5             100.00%
MRR                       0.9702
Metadata Filter Accuracy  100.00%
P95 Retrieval Latency     176.83 ms
Gate                      PASS
```

## 4. Text-to-SQL Evidence

```text
Cases                     23
SQL Cases                 15
UNSUPPORTED Cases         8
Overall Accuracy          100.00%
Status Accuracy           100.00%
Execution Success         100.00%
Semantic Result Match     100.00%
UNSUPPORTED Accuracy      100.00%
P95 Generation Latency    1720.17 ms
Gate                      PASS
```

## 5. Authority Boundary

```text
Request creation authority outside approved workflow : NO
Approval authority in analysis/evaluation layer      : NO
Production BOM write authority                       : NO
```

- LLM / RAG / Text-to-SQL / Context Resolver는 Production BOM write 권한이 없습니다.
- Analysis는 Design Change Request가 아닙니다.
- 사용자 승인 이후에만 Request가 생성됩니다.
- Preview와 최종 승인 후에만 Production E-BOM Apply가 가능합니다.
- FAIL Action은 Apply할 수 없습니다.
- Apply는 Atomic Transaction이며 실패 시 Rollback합니다.

## 6. Major Release History

최종 Repository에서는 주요 Release tag만 유지합니다.

- `v1.0.0` — 기본 BOM AI Agent PoC
- `v2.0.0` — SQLite 기반 BOM Domain / 데이터 구조 확장
- `v3.0.0` — 설계변경 End-to-End Workflow
- `v4.0.0` — RAG / Text-to-SQL / Context-Ontology / Evaluation / Final Release

세부 개발 과정은 Git commit history로 확인하며 중간 작업용 tag는 최종 Release 목록에서 제거합니다.

## 7. Final Release Commands

```powershell
python -m scripts.validate_evaluation_foundation
python -m scripts.finalize_evaluation --run-tests --require-tests
python -m scripts.validate_release_freeze
python -m scripts.finalize_release --run-tests --require-tests
```

Release commit 이후 `v4.0.0` tag와 remote branch/tag가 동일 commit을 가리키는지 확인합니다.
