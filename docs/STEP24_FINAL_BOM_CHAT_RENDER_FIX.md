# STEP24 최종 BOM 채팅 표시 보정

`get_bom` Tool 결과가 존재하는 Agent 응답은 LLM이 생성한 Markdown 표를 표시하지 않습니다.
채팅과 BOM 조회 메뉴가 동일한 공통 BOM Renderer만 한 번 호출합니다.

- 제품 BOM / ASSY BOM 제목
- BOM 조회 대상 코드
- PARENT_CODE, PARENT_NAME, CHILD_CODE, CHILD_NAME, LOCATION, 수량, 소요수량
- Assembly Child의 코드/명칭만 굵은 파란색
- 대화 이력 재표시 시에도 중복 방지
