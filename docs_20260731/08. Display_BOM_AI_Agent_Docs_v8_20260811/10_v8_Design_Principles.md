# v8 Design Principles

1. **Single Agent** — Multi-Agent로 불필요하게 확장하지 않는다.
2. **Agent = Decision** — 판단, Tool 선택, 결과 해석을 담당한다.
3. **Skill = Procedure** — 검증된 업무 절차와 제약을 제공한다.
4. **MCP = Interface** — 외부 Capability를 표준 방식으로 연결한다.
5. **Service = Business Logic** — Rule과 데이터 처리의 소유자다.
6. **Memory = Context/State** — 대화 문맥과 업무 진행상태를 이어간다.
7. **Controlled Planning** — 자유 계획보다 Domain Workflow 안에서 상황별 계획을 수행한다.
8. **Read/Analyze/Write Separation** — 조회/분석과 실제 변경을 분리한다.
9. **Human Approval Before Apply** — Production BOM 변경은 승인 이후에만 수행한다.
10. **Reuse Existing Assets** — 검증된 Service/Test/UI를 재사용한다.
11. **Contract/Test First** — 기능의 입력/출력과 기대 동작을 테스트로 고정한다.
12. **Domain Normalization Outside LLM** — 반복적이고 결정적인 용어 정규화는 코드/사전으로 관리한다.
13. **No Premature Complexity** — 현재 필요하지 않은 Multi-Agent, MCP-RAG, Vector DB는 도입하지 않는다.
14. **UI Does Not Own Business Logic** — Streamlit은 표현과 Interaction에 집중한다.
15. **E2E Before Expansion** — 새 계층은 실제 사용자 시나리오로 검증한 뒤 다음 단계로 넘어간다.
