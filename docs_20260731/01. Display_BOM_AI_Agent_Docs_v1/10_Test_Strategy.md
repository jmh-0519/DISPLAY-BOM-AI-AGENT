# 테스트 전략

## 1. 테스트 목표

LLM의 비결정성을 제외한 핵심 기능은 반복 가능하게 검증하고, Agent가 올바른 Tool과 근거를 사용하는지 시나리오 단위로 확인한다.

## 2. 테스트 계층

### Unit Test

- `BomService.get_product()`
- `BomService.search_material()`
- `BomService.get_bom()`
- Tool 입력 검증
- Registry 등록 및 조회
- Executor 예외 처리

### Integration Test

- Tool → Service → CSV
- Agent → Executor → Tool
- Streamlit 외부의 전체 질의 처리 함수

### Agent Scenario Test

- 정상 제품 BOM 조회
- 자재 키워드 검색
- 존재하지 않는 제품
- 모호한 질문
- 인사와 사용법 질문
- 지원하지 않는 쓰기 요청

### Security Test

- SQL Injection 형태 입력
- 파일 경로 입력
- 비정상적으로 긴 입력
- API Key 로그 노출 여부
- 허용되지 않은 Tool 이름

## 3. 완료 기준 예시

- 모든 Unit Test 통과
- 핵심 시나리오 Tool 선택 정확도 목표 충족
- Tool 결과와 최종 답변의 ID 및 수량 일치
- 실패 시 사용자에게 수정 가능한 메시지 제공

## 4. 테스트 케이스 템플릿

| ID | 구분 | 입력 | 예상 Tool | 예상 결과 | 상태 |
|---|---|---|---|---|---|
| TC-001 | 정상 | PRD-LED-43-A BOM 조회 | get_bom | BOM 목록 반환 | 미실행 |
