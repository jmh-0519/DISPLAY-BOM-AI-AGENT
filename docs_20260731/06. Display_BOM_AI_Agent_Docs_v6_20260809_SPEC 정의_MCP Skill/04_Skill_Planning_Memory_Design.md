# Skill / Planning / Memory Design

## 1. Skill

Skill은 Tool이 아니다.

Skill은 Agent에게 **업무를 어떤 절차와 원칙으로 수행해야 하는지** 제공한다.

### BOM Design Change Skill 예시

```text
설계변경 요청 수신
↓
대상 명확화
↓
현재 BOM 확인
↓
변경 대상 자재 확인
↓
변경 적합성 분석
↓
위험 / 경고 확인
↓
사용자 승인
↓
변경 반영
↓
품평회
↓
보고서 생성
```

정의:

```text
Skill = 표준 업무 수행 방법
```

## 2. Planning

Planner는 Skill을 참고하여 이번 사용자 요청에 필요한 구체적인 실행 계획을 만든다.

정의:

```text
Plan = 이번 요청을 처리하기 위한 구체적인 실행 순서
```

예:

```text
1. 현재 제품 BOM 조회
2. 기존 자재 확인
3. 신규 자재 확인
4. 설계변경 적합성 분석
5. 사용자 승인
6. BOM 변경 적용
7. 품평회
8. 보고서 작성
```

## 3. Memory

v6에서는 우선 두 종류의 Memory를 고려한다.

### Conversation Memory
앞선 대화의 문맥을 유지한다.

예:
- 사용자가 앞에서 어떤 제품을 지정했는가?
- "그 제품", "아까 자재"가 무엇을 의미하는가?

### Workflow Memory / State
업무가 현재 어느 단계까지 진행됐는지 저장한다.

예:

```json
{
  "workflow_id": "CHG-001",
  "intent": "design_change",
  "product_id": "PRD-LED-43-A",
  "old_material_id": "CMP-SPEAKER-5W",
  "new_material_id": "CMP-SPEAKER-20W",
  "current_step": "WAITING_APPROVAL",
  "analysis_result": "CONDITIONAL",
  "approval_status": "PENDING"
}
```

이를 통해 사용자가 이후에 "아까 변경 건 진행해줘"라고 요청해도 Workflow를 이어갈 수 있도록 한다.

## 4. 구성요소 관계

```text
Constitution
     ↓
Skill
"업무를 어떻게 수행할 것인가"
     ↓
Planning
"이번 요청에서 무엇을 어떤 순서로 할 것인가"
     ↓
MCP Tool
"실제 업무 기능 수행"
     ↓
Memory
"무엇을 했고 현재 어디까지 진행됐는가"
```
