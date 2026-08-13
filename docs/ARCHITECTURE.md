# 아키텍처

## 구성

- Single Azure BOM Agent: 사용자 의도 해석, 실행 계획, Workflow Memory
- BOM 업무 Skill: 실행 순서와 안전 규칙
- Display BOM MCP Server: 조회 및 설계변경 Capability 제공
- Service Layer: BOM 조회, 변경 분석, Review BOM, Rule 검증, 보고서, 최종 적용
- CSV Sample Data: 학습 프로젝트용 E-BOM과 기준정보/이력
- Streamlit: Agent 채팅, BOM 조회, AI 설계변경 Workflow 화면

## MCP Capability

| 영역 | Tool |
|---|---|
| 조회 | `get_bom`, `list_products`, `search_product`, `list_materials`, `search_material` |
| 분석 | `analyze_design_change`, `create_ai_change_request` |
| Review BOM | `create_review_bom` |
| AI 품평 | `run_ai_bom_review` |
| 보고서 | `generate_design_change_report` |
| 최종 반영 | `apply_reviewed_bom` |

## 쓰기 경계

`apply_reviewed_bom`만 `bom.csv`를 변경한다. 다른 Tool은 Workflow/Review/Report 데이터를 만들지만 Production E-BOM에는 쓰지 않는다.

기존 `evaluate_bom_review`의 부서 담당자별 확인 입력 방식은 제거했다. 기존 `ReviewService`의 Rule Engine과 Revision/검증 이력 기능은 AI 자동 품평의 실행 엔진으로 재사용한다.

