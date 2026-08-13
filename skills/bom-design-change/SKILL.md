---
name: bom-design-change
description: Display BOM 자재 교체의 분석, Review BOM, AI 품평, 보고서, 승인 및 적용 절차를 통제한다.
---

# BOM Design Change Skill

## Goal

Single Agent가 MCP Tool 결과를 근거로 설계변경 End-to-End Workflow를 안전하게 수행한다.

## Workflow

1. 제품 ID, 기존 자재 ID, 신규 자재 ID를 식별한다.
2. `analyze_design_change` 또는 `create_ai_change_request`로 적합성을 검증한다.
3. FAIL이면 이후 단계로 진행하지 않는다.
4. 등록된 변경 ID로 `create_review_bom`을 호출한다.
5. `run_ai_bom_review`로 Rule·Compatibility 체크리스트를 검증한다.
6. CONDITIONAL은 사용자 확인 전 적용하지 않고 FAIL은 차단한다.
7. PASS 품평 건은 `export_design_change_report`로 Word 보고서를 생성할 수 있다.
8. 보고서를 확인한 사용자의 명시적 요청이 있을 때만 `apply_reviewed_bom`을 호출한다.

## Query and Download Tools

- `get_bom`, `search_material`, `search_product`
- `list_design_changes`, `get_design_change`
- `list_bom_reviews`, `get_bom_review`
- `export_bom_excel`, `export_design_change_report`

조회와 다운로드 Tool은 읽기 전용이며 Production BOM을 변경하지 않는다. 파일을 요청한 경우 내부 경로나 base64를 답변에 표시하지 않고 UI의 실제 다운로드 버튼을 사용한다.

## Safety Rules

- 제품·자재·변경 ID·품평회 ID를 추측하거나 생성하지 않는다.
- Tool의 PASS, CONDITIONAL, FAIL을 임의로 바꾸지 않는다.
- 분석, Review BOM, 품평, 보고서, 명시적 승인 순서를 건너뛰지 않는다.
- 사용자 승인 없이 BOM을 변경했다고 표현하거나 적용 Tool을 호출하지 않는다.
- 적용 대상 Review BOM과 승인된 Revision이 일치해야 한다.
- Tool 실행 실패와 업무 검증 FAIL을 구분한다.
- 설계변경·품평 이력 조회는 상태를 변경하지 않는다.

## Architecture

- Single Agent 구조를 유지한다.
- Skill은 업무 절차와 금지조건을 제공한다.
- Planning/Workflow State는 허용된 다음 단계와 변경 ID·Review ID를 유지한다.
- 업무 판정과 데이터 변경은 Service를 거친 MCP Tool 결과를 따른다.
- 화면과 Agent는 같은 MCP Capability와 이력 Repository를 사용한다.
