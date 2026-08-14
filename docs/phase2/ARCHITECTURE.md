# 아키텍처

## 구성

- Single Azure BOM Agent: 사용자 의도 해석, 실행 계획, Workflow Memory
- BOM 업무 Skill: 실행 순서와 안전 규칙
- Display BOM MCP Server: 조회 및 설계변경 Capability 제공
- Service Layer: BOM 조회, 변경 분석, Review BOM, Rule 검증, 보고서, 최종 적용
- SQLite Repository: E-BOM, 기준정보, 설계변경, Review, 품평, 적용 이력
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

`apply_reviewed_bom`만 SQLite `bom_master`의 Production 관계를 변경한다.
다른 Tool은 Workflow/Review/Report 테이블만 변경하며 승인 전 Production E-BOM에는 쓰지 않는다.

모든 Capability는 MCP Server → Domain Service → SQLite Repository 경로를 사용한다.
CSV fallback과 저장소 모드 분기는 존재하지 않는다.
