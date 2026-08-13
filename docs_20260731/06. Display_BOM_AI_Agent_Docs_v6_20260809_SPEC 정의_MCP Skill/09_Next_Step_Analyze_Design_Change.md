# Next Step - analyze_design_change 상세 설계

## 1. 다음 개발 대상

v6의 첫 신규 업무 Capability는 다음으로 정한다.

```text
analyze_design_change
```

## 2. 먼저 코딩하지 않는 이유

설계변경 적합성은 단순 데이터 조회가 아니다.

다음 요소를 결합해야 한다.

- 현재 BOM
- 기존 자재
- 신규 자재
- 승인 상태
- Lifecycle
- 호환성
- 설계변경 Rule
- 영향 범위
- 경고
- 최종 판정

따라서 구현 전에 Tool Contract와 업무 판정 기준을 확정해야 한다.

## 3. 다음 회차에서 결정할 항목

### Input
예상 후보:

```json
{
  "product_id": "PRD-LED-43-A",
  "old_material_id": "CMP-SPEAKER-5W",
  "new_material_id": "CMP-SPEAKER-20W"
}
```

### Output
예상 후보:

```json
{
  "result": "CONDITIONAL",
  "changeable": true,
  "affected_items": [],
  "warnings": [],
  "checks": []
}
```

※ 위 구조는 아직 최종 Contract가 아니며 다음 상세 설계 단계에서 확정한다.

## 4. 사용할 데이터

우선 검토 대상:

```text
bom.csv
materials.csv
compatibility.csv
rules.csv
```

## 5. 완료 기준

다음이 정의되면 구현 단계로 넘어간다.

- 입력 Contract 확정
- 출력 Contract 확정
- 검증 Rule 확정
- PASS / CONDITIONAL / FAIL 또는 별도 판정 체계 확정
- 예외 처리 기준 확정
- 테스트 Case 정의
