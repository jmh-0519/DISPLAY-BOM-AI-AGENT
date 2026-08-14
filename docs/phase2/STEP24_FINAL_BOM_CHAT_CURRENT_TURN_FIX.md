# STEP24 최종 BOM 채팅 현재 턴 추출 및 ASSY 행 강조

- Checkpoint 메시지 병합 시 이전 메시지 개수로 자르지 않습니다.
- 마지막 사용자 요청 이후의 현재 턴에서 `get_bom` Tool 결과를 추출합니다.
- BOM Tool 결과가 있으면 LLM 임의 표/트리/설명을 숨깁니다.
- 공통 7개 컬럼 BOM 표만 한 번 표시합니다.
- Child가 ASSEMBLY인 관계는 행 전체를 파란색 굵은 글씨로 표시합니다.
