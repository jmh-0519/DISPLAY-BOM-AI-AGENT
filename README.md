# Display BOM AI Agent

Azure OpenAI, LangGraph, MCP, Streamlit으로 구성한 단일 BOM AI Agent 학습 프로젝트입니다.

STEP25부터 모든 Runtime 데이터는 `data/display_bom.db` SQLite 하나에서
조회·저장하며 CSV 저장소와 저장소 선택 모드는 제공하지 않습니다.

핵심 목표는 기존 BOM 시스템 전체를 재구현하는 것이 아니라, 설계변경 분석과 Rule 기반 품평 체크리스트를 AI Agent가 자동화하고 사용자가 보고서를 확인한 뒤 양산 E-BOM 반영을 최종 승인하도록 만드는 것입니다.

## 실행

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Azure OpenAI 설정은 `.env.example`을 복사해 `.env`에 입력합니다. `.env`는 배포물과 Git에 포함하지 않습니다.

## 핵심 Workflow

```text
설계변경 분석/검증
→ 변경 요청 및 변경 예정 BOM
→ Review BOM 생성
→ AI 품평 체크리스트 자동검증
→ 적용 전 Word 보고서 생성/다운로드
→ 사용자 최종 승인
→ 양산 E-BOM 반영
```

BOM 조회 Excel과 설계변경 완료 Word 문서는 각각 `export_bom_excel`,
`export_design_change_report` 다운로드 MCP Tool을 통해 생성됩니다.

상세 내용은 `docs/PROJECT_STATUS.md`, `docs/TARGET_WORKFLOW.md`, `docs/ARCHITECTURE.md`를 참고하십시오.
# STEP25 - SQLite 단일 Runtime

- Agent 채팅 Word/Excel 실제 다운로드 버튼
- 설계변경 이력 목록·상세 조회
- 품평회 이력 목록·상세 체크리스트 조회
- SQLite 기준정보·BOM·Workflow Repository
- SQLite Transaction 기반 승인 Apply와 Rollback
- 조회·다운로드 MCP Capability

Agent와 Streamlit은 업무 Service를 직접 우회하지 않고 Display BOM MCP Tool을 사용합니다.
