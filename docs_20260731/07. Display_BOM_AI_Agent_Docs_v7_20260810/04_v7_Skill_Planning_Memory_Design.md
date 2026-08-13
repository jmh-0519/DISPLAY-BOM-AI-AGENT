# v7 Skill / Planning / Memory Design

## 1. 현재 상태
v6에서 정의한 Skill / Planning / Memory 개념은 유효하지만 아직 본격 구현 전이다.

현재 설계변경 업무의 실제 Business Logic과 UI가 먼저 구현되어 향후 Skill과 Planner가 호출할 Capability가 구체화된 상태다.

## 2. BOM Design Change Skill

목표 절차:

```text
설계변경 요청
↓
대상 제품/자재 명확화
↓
현재 BOM 확인
↓
설계변경 분석
↓
검증 결과 확인
↓
Preview BOM 생성
↓
사용자 승인
↓
실제 변경 적용
↓
BOM Review
↓
필요 시 수정 및 재검증
↓
완료 보고서
```

## 3. Planning

Planner는 위 Skill을 참고하여 요청별 실행 순서를 생성한다.

예:
```text
1. 제품과 변경 자재 확인
2. analyze_design_change
3. 결과가 FAIL이면 중단
4. PASS/CONDITIONAL이면 Preview
5. 사용자에게 변경 전후와 위험 제시
6. 승인 대기
7. 승인 후 apply_design_change
8. evaluate_bom_review
9. 필요 시 Review BOM 수정/재검증
10. generate_change_report
```

## 4. Workflow State

향후 최소 상태 예:

```json
{
  "workflow_id": "CHG-001",
  "intent": "design_change",
  "product_id": "LTA400HR01-0",
  "old_material_id": "0001-200010",
  "new_material_id": "9000-290004",
  "analysis_status": "CONDITIONAL",
  "preview_created": true,
  "approval_status": "PENDING",
  "apply_status": "NOT_APPLIED",
  "review_status": "NOT_STARTED",
  "current_step": "WAITING_APPROVAL"
}
```

## 5. 구현 원칙
- Skill은 절차 정의
- Planner는 실행 순서 결정
- MCP는 Capability 실행
- Service는 Business Logic
- Memory는 진행 상태 저장

책임을 혼합하지 않는다.
