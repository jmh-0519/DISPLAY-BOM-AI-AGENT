# Design Change Workflow

## 1. 대표 사용자 요청

예:

> PRD-LED-43-A의 CMP-SPEAKER-5W를 CMP-SPEAKER-20W로 변경하고 품평회 후 보고서까지 만들어줘.

## 2. Agent의 예상 실행계획

```text
User Intent
   ↓
BOM 설계변경 전체 업무 수행
   ↓
BOM Design Change Skill
   ↓
Planner
   │
   ├─ Step 1. 현재 BOM 조회
   ├─ Step 2. 기존/신규 자재 조회
   ├─ Step 3. 변경 적합성 분석
   ├─ Step 4. 분석 결과 및 위험 확인
   ├─ Step 5. 사용자 승인
   ├─ Step 6. BOM 변경 적용
   ├─ Step 7. 품평회 수행
   └─ Step 8. 완료 보고서 작성
```

## 3. Tool 실행 예시

```text
get_bom
   ↓
search_material
   ↓
analyze_design_change
   ↓
[Human Approval]
   ↓
apply_design_change
   ↓
evaluate_bom_review
   ↓
generate_change_report
```

## 4. Human-in-the-loop

실제 BOM을 변경하는 `apply_design_change`는 조회/분석 Tool과 다르게 데이터를 변경한다.

따라서 목표 구조는 다음과 같다.

```text
설계변경 분석
↓
변경 가능 여부 / 영향 / 경고 제시
↓
사용자 승인
↓
apply_design_change 실행
```

승인 없이 자동으로 실제 BOM을 변경하지 않는 방향으로 설계한다.

## 5. 중요 원칙

다음과 같은 거대한 Tool은 만들지 않는다.

```text
apply_design_change_everything()
```

한 Tool이 조회 → 분석 → 변경 → 품평회 → 보고서를 모두 수행하면 Agent의 Planning 역할이 약화되고 책임 경계가 불명확해진다.

업무 Capability를 분리하고 Agent가 이를 조합하도록 한다.
