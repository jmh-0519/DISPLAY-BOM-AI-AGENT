# v8 Memory Design - Next Core Phase

## 1. Memory 필요성이 확인된 실제 사례
첫 질문:
```text
LC 실란트 자재를 찾아줘.
```
Agent는 LC SEALANT 5개를 정상 반환했다.

후속 질문:
```text
그 중에서 9000번대로 시작하는 자재가 있어?
```
의도상 직전 5개 결과 중 `9000-290004`만 찾아야 하지만, Agent는 전체 자재에서 9000번대 자재를 다시 검색하여 관련 없는 자재까지 반환했다.

## 2. 원인
Streamlit 화면에는 이전 메시지가 존재하지만 Agent가 다음 요청을 처리할 때 이전 Conversation/Tool Observation이 충분한 Context로 전달되지 않는다.

## 3. 1차 구현 대상: Short-term Conversation Memory
```text
Streamlit session_state.messages
 ↓
AzureBomAgent.run(user_input, conversation_history)
 ↓
Azure OpenAI Messages
 ↓
이전 User/Assistant/Tool Observation 포함
```

목표 질의:
```text
LC 실란트 찾아줘.
그중 9000번대만 보여줘.
그 자재는 어느 BOM에 들어가?
그 제품 BOM도 보여줘.
```

## 4. 2차 구현 대상: Workflow State
설계변경에서는 단순 채팅 기록보다 구조화된 상태가 필요하다.

```json
{
  "workflow_id": "CHG-001",
  "intent": "design_change",
  "product_id": "LTA400HR01-0",
  "analysis_status": "CONDITIONAL",
  "approval_status": "PENDING",
  "apply_status": "NOT_APPLIED",
  "review_status": "NOT_STARTED",
  "current_step": "WAITING_APPROVAL"
}
```

## 5. 원칙
- Conversation Memory와 장기 지식 저장을 혼동하지 않는다.
- 현재는 Vector DB가 필요하지 않다.
- 최근 대화 + Tool 결과를 우선 안정화한다.
- Workflow State는 설계변경 단계에서 별도로 구조화한다.
