# 현재 개발 단계

기준일: 2026-08-12

## STEP22

- BOM 조회결과 Excel 다운로드 MCP `export_bom_excel`
- 설계변경·AI 품평 Word 다운로드 MCP `export_design_change_report`
- 다운로드 MCP는 모두 읽기 전용이며 Production BOM을 변경하지 않음
- AI 품평 내부 JSON 제거 및 종합평가·세부 체크리스트 UI 제공
- 중복 `설계변경` 메뉴 제거, Workflow 공용 분석 UI 유지

## 완료

- Python/VS Code 기반 프로젝트 구조
- Azure OpenAI 설정 및 Tool Calling Client
- 단일 Agent + LangGraph 대화 Memory
- 프로젝트 Skill 로딩
- Display BOM MCP Server
- 제품/자재/BOM 조회
- 자연어 조회 정규화
- 설계변경 REPLACE 분석과 PASS/CONDITIONAL/FAIL 판정
- 변경 예정 BOM Preview와 Revision
- 변경 요청 및 BOM Snapshot 저장
- Review BOM 생성과 Revision 관리
- Rule/Compatibility 기반 AI 품평 자동검증
- 품평 체크 결과와 근거 저장
- 설계변경/품평/적용 전 보고서 데이터 생성
- 표준 Word 설계변경·AI 품평 보고서 생성 및 다운로드
- 설계변경 메뉴와 AI Workflow의 분석 결과 UI 공용화
- 사용자 명시 승인 후 Review BOM의 양산 E-BOM 반영
- E-BOM Effective Date 이력과 적용 후 무결성 검증
- PASS/CONDITIONAL/FAIL Gate 및 최종 적용 전 쓰기 차단

## 이번 재설계에서 제거/대체

- 부서 담당자별 품평 의견을 Agent에 입력하는 `evaluate_bom_review` Tool 제거
- `Preview 승인 → Controlled Apply → 사후 품평` 흐름 제거
- Agent 내부 다사용자 품평회 화면 구상 제거
- 최종 적용 전 단계에서 Production E-BOM을 변경하던 의미 제거
- `__pycache__`, `.env`, 데이터 백업 ZIP을 배포 패키지에서 제외

## 현재 범위 제한

- 샘플 CSV 기반이며 실제 Windchill/PLM/ERP 연동은 미구현
- REPLACE 중심이며 복합 변경 트랜잭션 UI는 후속 범위
- 비정형 고객 승인/공급사 협의 등은 데이터가 없으면 자동 승인하지 않음
- 보고서는 현재 DOCX를 지원하며 PDF 변환은 후속 범위
- 사용자 인증, 권한, 전자결재, 감사 로그는 운영 전 추가 필요

## 다음 권장 단계

1. 신규 Workflow 전용 자동 테스트 보강 및 전체 회귀 테스트 정리
2. Word 보고서 회사 양식·로고 적용 및 PDF 변환 지원
3. 사용자 확인 필요 항목의 해소/재검증 UI
4. 복수 자재 및 Assembly 변경 지원
5. 실제 BOM 시스템 연동 Adapter와 트랜잭션/권한 설계
# STEP23 1차 MVP 마무리

Agent 채팅의 파일 다운로드를 Streamlit 실제 다운로드 버튼으로 연결하고, 설계변경·품평회 통합 이력 조회 화면과 MCP Tool을 추가했다. CSV 저장소는 `WorkflowHistoryRepository`로 격리해 차기 SQLite 전환 시 UI와 Agent 계약을 유지할 수 있도록 했다.
