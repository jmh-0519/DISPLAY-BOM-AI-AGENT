# STEP40-C1 Regression Test Alignment

STEP40-C 정책 변경에 맞춰 이전 테스트 2건을 갱신합니다.

- PLANT 누락 시 LLM tool_choice가 아니라 Agent가 target-scoped `list_plants` Tool Call을 직접 생성하는 구조를 검증합니다.
- 생산계획/수요 데이터 개념 제거 후 Candidate 요약이 `재고 데이터`를 사용하도록 검증합니다.

Runtime 소스는 변경하지 않습니다.
