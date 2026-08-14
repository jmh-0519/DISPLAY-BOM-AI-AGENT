# STEP24-E2A 적용 안내

이번 보정은 VERSION/ASSEMBLY 공통 BOM 조회와 Agent/BOM 조회 메뉴의 공통 표시 계약을 적용합니다.

- VERSION Root: `제품 BOM`
- ASSEMBLY Root: `ASSY BOM`
- MATERIAL: 하위 BOM 조회 차단
- 표 위에 `BOM 조회 대상 코드` 1회 표시
- 결과 컬럼: PARENT_CODE, PARENT_NAME, CHILD_CODE, CHILD_NAME, LOCATION, 수량, 소요수량
- Child가 ASSEMBLY일 때 코드와 명칭을 굵은 파란색으로 표시
- Agent의 get_bom Tool 결과와 BOM 조회 메뉴가 같은 Streamlit 렌더러 사용
- Excel도 동일 7개 결과 컬럼 사용

설계변경/품평 CSV의 SQLite 업무 이관과 MCP Apply 전환은 E2B에서 수행합니다. 구형 Snapshot에는 MODEL/MOD 가상 행과 이미 적용된 과거 변경이 섞여 있어 조회 UI 보정과 한 번에 이관하지 않습니다.
