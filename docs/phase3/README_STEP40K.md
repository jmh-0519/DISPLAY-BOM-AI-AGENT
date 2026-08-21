# STEP40-K — History Selection State & Master Query Navigation UX

## 변경 목적

1. 설계변경 이력의 Request ID 클릭 시 URL query parameter 때문에 앱이 Agent 채팅으로 재로딩되는 문제 제거
2. Master 조회 메뉴를 BOM / 모델 / 자재가 메인 메뉴에서 바로 보이도록 단순화
3. 모델/자재 검색 결과의 코드 클릭으로 상세조회하며 중복 상세정보 제거

## 설계변경 이력

- Request ID는 URL 링크가 아니라 Streamlit 내부 버튼으로 동작
- 클릭 시 동일 화면 하단에 상세 표시
- 다른 메뉴로 이동하면 선택 Request 상태 제거
- 다시 이력 메뉴로 돌아왔을 때 과거 Request가 자동으로 열리지 않음
- Request ID는 파란색 Bold 링크형 버튼으로 표시
- 기존 검색조건 및 15건 Paging 유지

## Master 조회 메뉴

Sidebar의 별도 `조회 유형` 영역을 제거하고 메인 업무 메뉴에서 직접 선택합니다.

- `Master 조회 · BOM`
- `Master 조회 · 모델`
- `Master 조회 · 자재`

## 모델 / 자재 조회

- 검색 결과의 모델코드/자재코드를 파란색 Bold 버튼으로 표시
- 코드를 클릭하면 같은 화면 하단에 상세조회
- `상세조회 모델`, `상세조회 자재` Dropdown 제거
- 상세정보는 `기본정보 + 상세 속성`으로 단순화
- Master/Specification/Attribute 간 중복 key는 1회만 표시

## DB / Runtime

- DB schema 및 데이터 변경 없음
- MCP/Service/Repository 변경 없음

## 검증

```text
STEP40-I/J/K 관련 계약 및 역방향 BOM 테스트: 12 passed
Python compile: PASS
```

전체 `scripts.run_tests`는 패키징 환경에 `openai`, `langchain_core`, `mcp`, `streamlit`이 없어 collection 단계에서 실행할 수 없으므로 사용자 `.venv`에서 확인합니다.

```powershell
python -m scripts.run_tests -q
```
