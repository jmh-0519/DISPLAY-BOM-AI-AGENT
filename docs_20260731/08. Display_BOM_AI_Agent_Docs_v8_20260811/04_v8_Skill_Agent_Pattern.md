# v8 Skill and Agent Pattern

## 1. 현재 Agent Pattern 판단
현재 구현은 **Tool-Using Agent**를 기본 형태로 하며, 실행 관점에서는 ReAct와 유사한 Multi-step Tool Calling Loop를 사용한다.

```text
User Request
 ↓
LLM Reason/Decision
 ↓
Tool Call
 ↓
Observation
 ↓
LLM 재판단
 ↓
다음 Tool 또는 Final Answer
```

## 2. Skill의 역할
Skill은 Tool 자체가 아니라 업무 절차/지식 계층이다.

```text
MCP   = Tool 제공 / Capability Interface
Skill = Tool을 언제, 어떻게 조합해서 사용할지 안내
```

현재 `SKILL.md`에는 BOM/제품/자재 조회 시의 Tool 선택과 검색→정확한 ID 확보→상세 조회 같은 절차를 제공한다.

## 3. Planning과의 관계
현재 조회 업무는 비교적 짧아 LLM이 Skill을 참고하여 단계별 Tool을 선택한다. 설계변경처럼 긴 업무는 향후 명시적 Workflow State와 Planning을 결합한다.

## 4. 프로젝트가 추구하는 Planning
업무 프로세스를 모두 LLM에게 자유롭게 생성시키는 방식이 아니다.

```text
개발자가 정의한 Domain Workflow / Skill
          +
Agent의 상황별 실행 순서 판단
```

즉 **Controlled Planning** 방향이다.
