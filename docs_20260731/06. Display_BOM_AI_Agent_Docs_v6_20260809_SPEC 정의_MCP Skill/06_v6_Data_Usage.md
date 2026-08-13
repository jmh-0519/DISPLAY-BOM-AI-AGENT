# v6 Data Usage

v5까지 생성한 CSV 데이터는 v6에서도 재사용한다.

## 주요 데이터와 예상 용도

| 데이터 | v6 예상 용도 |
|---|---|
| `bom.csv` | 현재 BOM 및 변경 대상 확인 |
| `materials.csv` | 기존/신규 자재 정보, 승인/Lifecycle 확인 |
| `products.csv` | 제품 정보 조회 |
| `compatibility.csv` | 자재 호환성 및 설계변경 적합성 분석 |
| `rules.csv` | 설계변경 및 품평회 업무 Rule |
| `change_history.csv` | 변경 이력 및 향후 Workflow/Memory 연계 |
| `suppliers.csv` | 공급사 관련 검증/품평회 |
| `data_dictionary.csv` | 데이터 구조 설명 |
| `test_questions.csv` | 향후 Agent 평가 시나리오 |

## v6 활용 방향

`analyze_design_change`를 구현하면서 우선 다음 데이터를 적극 활용한다.

```text
bom.csv
materials.csv
compatibility.csv
rules.csv
```

이후 `evaluate_bom_review` 구현 단계에서 품평회 규칙과 추가 데이터를 확장한다.
