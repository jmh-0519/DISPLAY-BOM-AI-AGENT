# v7 Design Change Workflow

## 1. 목표 Workflow

```text
User Request
   ↓
Intent: Design Change
   ↓
Analyze
   ↓
PASS / CONDITIONAL / FAIL
   ↓
Preview
   ↓
Human Approval
   ↓
Apply
   ↓
Review
   ↓
Revalidation
   ↓
Report
```

## 2. 현재 구현된 분석 검증

현재 설계변경 분석에서는 다음 검증을 수행할 수 있다.

```text
PRODUCT_EXISTS
OLD_MATERIAL_IN_BOM
NEW_MATERIAL_EXISTS
NEW_MATERIAL_APPROVAL
NEW_MATERIAL_LIFECYCLE
COMPATIBILITY
RULE_VALIDATION
```

UI에서는 내부 코드를 업무 친화적인 한글 명칭으로 변환한다.

## 3. Compatibility
신규 자재를 source로 하여 활성 Compatibility를 확인한다.

대상:
- MODEL: 현재 제품과 target_id 비교
- MATERIAL: Exploded BOM 내 target_id 존재 여부

결과:
- COMPATIBLE → PASS
- CONDITIONAL → CONDITIONAL
- INCOMPATIBLE → FAIL + blocking reason

## 4. Preview
Preview는 실제 Production BOM을 변경하지 않는다.

```text
Analyze
  ↓
Preview BOM
  ↓
사용자 확인
```

입력 조건이 변경되면 이전 Preview를 재사용하지 않도록 상태를 초기화한다.

## 5. Apply
실제 Apply는 Analysis/Preview와 분리한다.

향후 Agent Workflow에서는 반드시 Human Approval 이후 실행하도록 연결한다.

## 6. Review
Review 단계에서는 Review BOM을 별도로 관리하고 재검증할 수 있다.

검증결과는 Review Revision과 연결하여 저장하며 재검증 시 이전 결과를 교체할 수 있다.

## 7. 미완성 단계
- Agent Planner 기반 자동 단계 전환
- Human Approval State
- 실제 MCP 호출 흐름
- 완료 보고서
