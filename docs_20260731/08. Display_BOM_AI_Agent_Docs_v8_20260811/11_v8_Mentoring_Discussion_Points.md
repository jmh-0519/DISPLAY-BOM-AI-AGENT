# v8 Mentoring Discussion Points

## 멘토에게 확인하고 싶은 핵심 사항
1. 현재 **Single Agent + Skill + MCP + Service** 책임 분리가 적절한가?
2. 조회 단계에서 사용한 Multi-step Tool Calling 구조를 Design Change Workflow까지 확장하는 방향이 적절한가?
3. Planning을 자유 생성형이 아니라 **Domain Skill/Workflow 기반 Controlled Planning**으로 가져가는 것이 적절한가?
4. 다음 단계로 Conversation Memory를 먼저 구현하고, 이후 구조화된 Workflow State를 분리하는 순서가 적절한가?
5. Tool Observation을 Conversation Context에 어느 수준까지 보존하는 것이 좋은가?
6. MCP Tool 수가 현재 수준일 때 MCP-RAG/Tool Retrieval을 도입하지 않는 판단이 적절한가?
7. Query Normalization을 LLM Prompt가 아니라 코드 + Alias CSV로 관리하는 방식이 적절한가?
8. Design Change의 Analyze → Preview → Approval → Apply → Review 구조에서 추가로 필요한 안전장치가 있는가?
9. 현 단계에서 Memory 구현 후 바로 Design Change MCP 통합으로 가는 것이 좋은지, Evaluation Framework를 먼저 보강할지?
