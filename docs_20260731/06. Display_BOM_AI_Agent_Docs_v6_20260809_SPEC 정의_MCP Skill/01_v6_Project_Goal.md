# v6 Project Goal

## 1. v5까지의 상태

v5의 기본 실행 흐름은 다음과 같다.

```text
사용자
  ↓
Streamlit
  ↓
AzureBomAgent
  ↓
Azure OpenAI
  ↓
Tool 선택
  ↓
ToolExecutor
  ↓
Service / CSV
  ↓
Tool 결과
  ↓
Azure OpenAI 최종 답변
```

현재 조회 Capability는 다음 5개 Tool로 구성된다.

```text
get_bom
list_products
search_product
list_materials
search_material
```

## 2. v6에서 해결할 문제

v5는 사용자의 질문을 이해하고 적절한 조회 Tool을 선택할 수 있지만, 여러 단계로 구성된 BOM 업무 Workflow를 계획하고 수행하는 수준은 아니다.

v6에서는 다음과 같은 요청을 처리하는 것을 목표로 한다.

> 특정 제품의 기존 자재를 신규 자재로 변경하고, 변경 적합성을 분석한 후 승인 절차를 거쳐 BOM에 반영하고, 품평회 검증 및 완료 보고서까지 작성한다.

## 3. v6 최종 목표

```text
사용자 요청
   ↓
Intent 이해
   ↓
Skill 참조
   ↓
Planning
   ↓
Workflow State / Memory
   ↓
MCP Tool 실행
   ↓
결과 검증
   ↓
필요 시 다음 Tool 실행
   ↓
Human Approval
   ↓
최종 업무 완료 / 보고
```

즉 v6의 핵심은 **단일 Tool 호출 Agent → 업무 Workflow 수행 Agent**로의 발전이다.
