# STEP24 Final BOM Query Normalization Fix

- BOM 조회 의도와 단일 BOM 코드가 함께 있으면 표준 질의로 정규화합니다.
- `제품 BOM BOM 조회 대상 코드: LTA400HR01-001`처럼 화면 문구를 다시 입력해도
  `LTA400HR01-001의 BOM을 보여줘`와 동일한 Agent/Tool 경로를 사용합니다.
- 여러 코드 비교, 일반 BOM 설명, 설계변경 요청은 기존 Agent 판단을 유지합니다.
- Tool 결과는 기존 공통 BOM 렌더러로 표시합니다.
