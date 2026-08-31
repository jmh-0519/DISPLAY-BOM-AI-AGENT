---
name: bom-design-change
description: Display BOM의 MATERIAL/ASSY 설계변경 분석, 후보 추천, 복수 Action, 두 승인과 안전한 적용 절차를 통제한다.
---

# BOM Design Change Skill

## Goal

Single Agent가 MCP Tool 결과를 근거로 설계변경 End-to-End Workflow를 안전하게 수행한다.

## Workflow

### Design Change Active Workflow — Analysis Session → Request → Apply → Word Report

Design Change의 활성 업무 경로는 **분석 단계와 실제 설계변경 Request/Workflow를 분리**한다.

1. `analyze_design_change_candidates`로 **Analysis Session**을 시작한다. 이 단계에서는 `change_requests`/`change_actions`를 생성하지 않는다.
2. Analysis Session 안에서 대상·Reason·후보·Rule/Attribute·공급사·원가·재고를 분석하고 사용자 후속질문에 설명한다.
3. 사용자가 후보를 화면에서 임시 선택한다. Dropdown 선택은 Memory/UI 상태일 뿐 DB의 Design Change Request나 후보 승인 이력을 만들지 않는다.
4. CONDITIONAL이면 `revalidate_design_change_analysis`로 요청수량 등 보완 가능한 정보를 반영해 재검증한다. 재검증도 Request를 생성하지 않는다.
5. 선택 후보가 COMMON 영향 대상이면 `preview_design_change_analysis_impact`로 영향 모델과 Before/After Spec을 읽기 전용으로 확인한다. 이 단계도 Request를 생성하지 않는다.
6. 사용자가 분석 결과·후보·필요한 영향범위를 확인한 뒤 **"설계변경 진행"을 명시적으로 승인한 경우에만** `create_design_change_request_from_analysis`를 호출한다. 이 시점이 실제 Design Change Request 생성 경계이다.
7. Request 생성 후 `create_design_change_preview`로 실제 변경 Preview를 만든다.
8. 사용자가 Preview를 확인한 뒤 `record_final_apply_approval`로 Production Apply 최종 승인을 기록한다.
9. `apply_approved_change_request`가 모든 Action을 하나의 Transaction으로 적용하며 실패 시 전체 Rollback한다.
10. Apply 성공 후 `export_design_change_completion_report`로 **설계변경 완료 Word 보고서**를 생성하고 Design Change 업무를 종료한다.

### Analysis Memory / Restart

- Analysis Session은 `analysis_id`, 대상, Reason, 후보, Evidence, 재검증 이력, 임시 선택, 영향분석을 Memory로 유지한다.
- `왜?`, `비교해줘`, `수량을 바꿔서 다시 봐줘` 같은 요청은 동일 Analysis Memory를 사용한다.
- 사용자가 `다시 처음부터`, `새로 분석`, `다시 조회`라고 하면 현재 **Analysis Memory만 새 Analysis Session으로 교체**한다.
- 아직 Request가 생성되지 않았으므로 Analysis 재시작 시 Request 삭제, 취소, SUPERSEDED 처리를 하지 않는다.
- 새 Analysis는 최초 분석 입력(`analysis_base_request`)을 기준으로 시작하며, 이전 재검증에서 입력한 임시 수량 등은 자동 승계하지 않는다.

### Design Change 품평회 정책

현재 Design Change 활성 Workflow에서는 **Review BOM / AI 품평 단계를 수행하지 않는다.**

```text
Analysis Session
→ 사용자 설계변경 진행 승인
→ Design Change Request 생성
→ 변경 Preview
→ 최종 Apply 승인
→ Atomic Apply
→ Word 완료 보고서
→ 종료
```

Review BOM / AI 품평 Runtime 경로는 현재 Core에서 사용하지 않는다. 과거 Schema/Data 정리는 별도 DB Cleanup에서 수행한다.

## Query and Download Tools

- `get_bom`, `search_material`, `search_product`
- `list_design_change_history`
- `export_bom_excel`, `export_design_change_completion_report`

조회와 다운로드 Tool은 읽기 전용이며 Production BOM을 변경하지 않는다. 파일을 요청한 경우 내부 경로나 base64를 답변에 표시하지 않고 UI의 실제 다운로드 버튼을 사용한다.

## Safety Rules

- 제품·자재·Request/Action/Approval ID를 추측하거나 생성하지 않는다.
- Tool의 PASS, CONDITIONAL, FAIL을 임의로 바꾸지 않는다.
- 후보 점수·원가·재고·납기·공급사를 Tool 결과 없이 생성하지 않는다.
- 후보 승인과 최종 Apply 승인을 한 번의 사용자 동의로 합치지 않는다.
- 다른 요청의 Action·후보·승인 ID를 현재 요청에 사용하지 않는다.
- REPLACE/ADD Action을 누락한 채 1차 승인을 진행하지 않는다.
- PENDING 또는 FAIL Action이 하나라도 있으면 Preview·최종 승인·Apply를 진행하지 않는다.
- CONDITIONAL 예외승인은 사유를 필수로 기록하고 FAIL에는 사용하지 않는다.
- Preview 이후 후보·공급사·수량·Action이 달라지면 새 Preview와 최종 승인을 받는다.
- MATERIAL/ASSY 유형, BOM 계층, 중복 활성 관계와 순환 관계 검증 실패를 완화하지 않는다.
- 공용 ASSY 내부 변경은 영향 모델 전체를 확인하고, 모델의 ASSY 연결 교체와 구분한다.
- Analysis 단계와 실제 Design Change Request 생성 경계를 섞지 않는다. Request는 사용자 설계변경 진행 승인 이후에만 생성한다.
- 사용자 승인 없이 BOM을 변경했다고 표현하거나 적용 Tool을 호출하지 않는다.
- Design Change Core Workflow에서는 Review BOM/AI 품평을 요구하지 않으며, Preview와 최종 승인 Revision 일치 여부를 검증한다.
- SQLite Apply 직전에 승인된 Preview, 교체 Item 수, 현재 BOM Revision과 Action 무결성을 다시 검증한다.
- Production 변경은 `apply_approved_change_request`의 SQLite 단일 Transaction에서만 수행한다.
- Tool 실행 실패와 업무 검증 FAIL을 구분한다.
- 설계변경·분석 이력 조회는 상태를 변경하지 않는다.

## Architecture

- Single Agent 구조를 유지한다.
- Skill은 업무 절차와 금지조건을 제공한다.
- Planning/Workflow State는 Analysis ID, Analysis Memory, 실제 Request ID와 승인 상태를 단계별로 구분해 유지한다.
- 업무 판정과 데이터 변경은 Service를 거친 MCP Tool 결과를 따른다.
- 화면과 Agent는 같은 MCP Capability와 이력 Repository를 사용한다.

## STEP31 Analysis Explainability and Follow-up Q&A

설계변경 후보 분석이 완료된 뒤 사용자의 후속질문은 새로운 설계변경 요청으로 초기화하지 않는다.
현재 Thread의 Analysis Context와 저장된 Candidate Evaluation Evidence를 사용한다.

### Follow-up Planning

- `왜 전부 FAIL이야?`, `후보가 왜 없어?` → `get_design_change_analysis`
- 특정 후보의 FAIL/CONDITIONAL 사유 → `get_candidate_evaluation_detail`
- 후보 간 차이, 가장 비슷한 후보, 가장 저렴한 후보, 납기/재고 우선 후보 → `compare_design_change_candidates`
- Explain Tool을 한 번 호출한 뒤에는 같은 턴에서 후보평가를 다시 실행하지 않는다.

### Explanation Rules

1. `검색 후보 0건`과 `검색 후보는 있으나 PASS/CONDITIONAL 0건`을 반드시 구분한다.
2. FAIL 사유는 실제 Rule Condition 또는 Attribute Before/Candidate 값을 근거로 설명한다.
3. CONDITIONAL은 어떤 데이터가 없거나 어떤 추가 확인이 필요한지 설명한다.
4. 재고 평가는 설계변경 Action의 BOM `QUANTITY`를 기준으로 한다. REPLACE는 현재 BOM 수량, ADD/QUANTITY_CHANGE는 변경 후 BOM 수량을 사용하며 생산계획이나 별도 요청 필요수량을 곱하지 않는다.
5. 기술/Spec FAIL은 공급사 PASS로 뒤집히지 않는다.
6. 후보 비교 1위가 FAIL이면 "가장 가까운 후보"일 뿐 승인 가능한 후보라고 표현하지 않는다.
7. 저장된 Evidence가 없으면 추측하지 않고 근거 데이터가 부족하다고 설명한다.
8. 후속질문 답변에서 후보 분석 표나 Workflow를 새로 생성하지 않는다.
9. Explain/Compare Tool은 읽기 전용이며 후보 상태·승인 상태·Production BOM을 변경하지 않는다.

## STEP32 Evidence and Impact Explanation Rules

1. Rule 평가 설명은 `rule_id`, `revision`, 실제값, 연산자, 기준값, 조건별 점수와 판정 사유를 근거로 한다.
2. Attribute 평가 설명은 기존 품목 값과 후보 품목 값을 Before → Candidate 형식으로 설명한다.
3. `CONDITIONAL`은 단순히 "데이터 부족"이라고만 말하지 않고 `missing_requirements`의 필드와 해결 방법을 제시한다.
4. 재고 설명은 BOM `QUANTITY`, 가용재고, 부족수량과 Location별 근거를 사용한다. 생산계획 또는 별도 요청수량을 설계변경 재고판정 기준으로 사용하지 않는다.
5. 입고예정 재고는 Effective Date 이전 입고분만 가용재고에 포함되었는지 구분한다.
6. 공급사 설명은 평가 당시 저장된 Score, Component Score와 Weight를 우선 사용하며 현재 Master를 임의로 재계산하지 않는다.
7. 후보 비교는 동일 평가항목의 Before/Candidate 차이를 보여주며, 비교 1위가 FAIL이면 승인 가능 후보로 표현하지 않는다.
8. 공용 ASSY 내부 BOM 변경은 영향받는 모델마다 Old/New Item과 변경 Spec을 연결하여 설명한다.
9. 공용 영향 모델이 여러 개인 경우 일부 모델만 생략하여 영향이 없는 것처럼 표현하지 않는다.
10. Explain/Compare/Impact 결과에 없는 수치나 Spec을 LLM이 보완하여 만들어내지 않는다.

## STEP33 Multi-Reason and Dynamic Candidate Rules

1. REPLACE 후보 추천 요청에서는 사용자가 신규 자재 ID를 미리 알고 있다고 가정하지 않는다.
2. 제품과 변경 대상 기존 품목이 식별되면 `new_item_code` 없이 `analyze_design_change_candidates`로 Analysis Session에서 후보를 동적으로 탐색한다. 이때 실제 Request는 생성하지 않는다.
3. 자연어에 여러 설계변경 사유가 포함되면 하나만 다시 선택하도록 요구하지 않는다.
4. Action에는 업무 대표 사유인 Primary Reason 1개와 추가 사유인 Secondary Reasons를 함께 저장한다.
5. Primary Reason은 명시적 사용자 선택이 있으면 그것을 사용하고, 없으면 자연어/Metadata에서 먼저 식별된 유효 사유를 사용한다.
6. 후보 평가는 Primary Reason뿐 아니라 저장된 모든 적용 가능한 Reason Rule을 함께 적용한다.
7. 복수 Reason이 COST/LEAD_TIME/QUALITY/SUPPLIER_STOP 등 공급사 평가 가중치에 영향을 주면 하나의 사유만 덮어쓰지 않고 관련 Weight Profile을 결합한다.
8. 사용자가 후속 턴에 `변경 가능한 자재 알려줘`처럼 대상 코드를 반복하지 않아도 최근 대화의 제품/기존 품목 Context를 유지하여 후보 분석을 계속한다.
9. 복수 Reason을 감지했다는 이유만으로 후보 탐색을 건너뛰거나 신규 자재 지정을 강제하지 않는다.
10. Explain 결과에는 Primary Reason과 Secondary Reasons, 각 Rule의 change_reason을 구분해 제공한다.


## STEP33-B Multi-Reason UI and Conditional Gate Rules

1. 변경 대상 품목 요약은 내부 스크롤 없이 전체 Context가 한 번에 보여야 한다.
2. 후보 비교표는 `종합 적합성 → 종합 판단 요약 → 평가 사유 → 기술 평가` 순서로 핵심 판단을 먼저 보여준다.
3. `종합 판단 요약`은 저장된 기술/공급/재고 Evidence와 missing data를 근거로 간단하게 작성하며 LLM이 임의 수치를 생성하지 않는다.
4. 복수 Reason은 후보별 `평가 사유`에 Primary/Secondary 전체를 함께 표시한다.
5. 사용자 입력 Reason과 DB 상태가 다를 수 있으므로 EOL 등은 사용자 입력과 Master Evidence를 구분하여 표시한다.
6. CONDITIONAL 후보 선택은 Workflow 시작이 아니다. 부족 데이터 보완/재검증 또는 예외승인 Gate를 통과해야 한다.
7. 예외승인을 통과한 CONDITIONAL 후보가 COMMON 영향 대상이면 공용 영향 확인을 추가로 완료한 뒤 1차 후보 승인을 기록한다.
8. FAIL 후보에는 예외승인을 허용하지 않는다.

## STEP33-C Candidate Selection Confirmation Rules

1. 후보 Dropdown 선택은 Streamlit Session State의 임시 선택이며 DB에 `selected_candidate_id`를 기록하지 않는다.
2. 후보를 고르면 별도 조회 버튼 없이 선택 후보 재확인 영역을 즉시 표시한다.
3. 실제 DB 저장은 사용자가 `이 후보로 선택 확정` 또는 `예외승인 후 이 후보로 선택 확정`을 눌렀을 때만 수행한다.
4. 모든 REPLACE/ADD Action에 정확히 하나의 후보가 선택되어야 하며, 일부 Action에 선택 가능한 후보가 없으면 서버 호출 전에 UI에서 차단한다.
5. 동일 대상/Parent/Location/Action을 복수 Reason 때문에 중복 Action으로 생성하지 않는다. 하나의 Action에 Primary + Secondary Reasons를 연결한다.
6. CONDITIONAL 후보는 선택 확정 전에 추가 속성 또는 사용자 요청수량을 입력하여 재검증할 수 있다.
7. 공급사/원가 Master가 없는 경우 임시 수치로 사실을 만들지 않는다. 기준정보를 보완하거나 예외승인 사유를 기록한다.
8. 재검증 후 PASS가 되면 일반 확정 버튼을 사용한다. 계속 CONDITIONAL이면 사유 없는 확정을 금지한다.
9. CONDITIONAL 후보 선택과 예외승인은 하나의 확정 동작으로 처리하여 후보만 저장되고 예외승인이 누락되는 중간상태를 만들지 않는다.
10. UI 업무 오류는 사용자 친화적 메시지로 표시하고 Python Traceback을 사용자 화면에 노출하지 않는다.


## STEP34 Analysis Session / Request Separation Rules

1. 후보 탐색, 평가, Explain, 추가정보 반영, 재검증, 후보 임시선택, 공용 영향 확인은 모두 Analysis Session에 속한다.
2. 위 Analysis 단계에서는 `change_requests`와 `change_actions`를 생성하지 않는다.
3. 사용자가 분석안을 확인한 뒤 명시적으로 설계변경 진행을 승인한 시점에만 `create_design_change_request_from_analysis`로 Request를 생성한다.
4. Analysis 중 `다시 처음부터` 요청은 Analysis Memory만 초기화/재생성하며 Design Change 이력에는 아무 Request도 남기지 않는다.
5. Analysis 재검증 전 결과와 재검증 후 결과를 모두 Memory에 유지하여 Before/After를 설명한다.
6. Request 생성 이후에는 Workflow Memory로 전환하고 Preview → 최종 Apply 승인 → Atomic Apply 순서를 강제한다.
7. 현재 Design Change 활성 경로에서는 별도 Review BOM/AI 품평을 수행하지 않는다.
8. Apply 성공 후 Word 완료 보고서를 생성하면 Workflow를 종료한다.
9. Review/품평 Runtime 경로는 사용하지 않는다. 과거 Schema/Data는 DB Cleanup 범위에서 별도로 정리한다.
10. 분석 이력과 실제 설계변경 Request 이력을 동일 개념으로 취급하지 않는다.


## STEP35 Persistent Revalidation and Conversational PLANT Rules

1. 최초 후보 분석 Snapshot은 재검증 결과로 덮어쓰지 않는다. `analysis_initial_candidates`와 최초 Context를 유지한다.
2. 재검증 결과는 `revalidation_history`에 순서대로 누적하며 최초 분석 화면 하단에 Before/After로 표시한다.
3. 한 후보를 재검증한 뒤에도 최초 후보 Pool을 유지하여 사용자가 다른 후보로 바꾸거나 요청수량을 다시 입력해 반복 재검증할 수 있게 한다.
4. 재검증은 Analysis Session의 상태만 갱신하며 Design Change Request를 생성하지 않는다.
5. Agent 채팅의 PLANT는 Sidebar 기본값으로 고정하지 않는다.
6. BOM 조회 또는 설계변경에 PLANT가 필요하지만 사용자 요청과 활성 Analysis/Workflow에 plant_code가 없으면 먼저 `list_plants`를 조회한다.
7. `list_plants` 결과의 코드와 이름을 사용자에게 선택지로 제시하고, 사용자가 PLANT를 선택하기 전에는 BOM 조회·후보 분석·Request 생성 Tool을 실행하지 않는다.
8. PLANT를 임의로 기본 선택하거나 추측하지 않는다. 사용자가 다음 턴에 선택한 PLANT를 직전 요청 Context와 결합해 업무를 계속한다.
9. 현재 Design Change에서는 품평회 단계를 사용하지 않으며 Streamlit 주요 메뉴에서도 품평회 이력을 노출하지 않는다.

## STEP37 Product-wide Cost Opportunity Scan Rules

1. 사용자가 특정 단일 품목이 아니라 `대상 모델`, `제품 전체`, `BOM 전체`, `BOM에 구성된 자재들` 범위에서 원가 절감 대체 후보를 찾는 경우 하나의 임의 품목을 Design Change target으로 선택하지 않는다.
2. 위 요청은 `scan_product_cost_reduction_candidates`로 제품 BOM 전체를 읽기 전용 탐색한다. 이 Tool은 Design Change Request를 생성하지 않고 기존 Analysis Session도 덮어쓰지 않는다.
3. BOM 탐색 대상은 실제 `version_code + plant_code + as_of_date`의 활성 BOM 관계에서 동적으로 결정한다. 테스트 제품 코드나 특정 자재 코드를 Runtime 분기조건으로 사용하지 않는다.
4. 사용자가 `CF 말고`, 특정 코드 `제외`처럼 범위를 제외하면 해당 품목/공정만 Scan에서 제외한다. 나머지 BOM 구성품은 계속 탐색한다.
5. 기술 평가가 FAIL인 후보는 원가가 낮아 보여도 변경 가능 후보로 표현하지 않는다.
6. `cost_reduction_status=CONFIRMED`는 현재품과 후보 모두에 비교 가능한 단가 Evidence가 있고 후보 단가가 실제로 낮을 때만 사용한다.
7. `cost_reduction_status=UNAVAILABLE`은 기술적으로 PASS/CONDITIONAL일 수 있으나 단가 근거가 부족하므로 원가 절감이 확인됐다고 표현하지 않는다.
8. `NO_SAVINGS`는 기술적으로 대체 가능하더라도 확인된 단가 기준 원가 절감 후보가 아님을 명확히 한다.
9. 제품 전체 Scan 결과에서 사용자가 특정 현재품/후보 조합을 선택한 뒤에만 해당 품목을 대상으로 정식 `analyze_design_change_candidates` Analysis Session을 시작한다.
10. 제품 전체 Opportunity Scan은 탐색/Planning 단계이며, 사용자 승인 전 `change_requests`/`change_actions`를 생성하지 않는다.
