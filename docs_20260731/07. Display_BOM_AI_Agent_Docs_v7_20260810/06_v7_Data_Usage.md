# v7 Data Usage

## 1. 기본 원칙
기존 CSV 기반 업무 데이터를 계속 재사용한다.

## 2. 주요 데이터

| 데이터 | 현재/예상 용도 |
|---|---|
| bom.csv | 현재 BOM, Exploded BOM, 변경 대상 확인 |
| materials.csv | 자재 존재, 승인, Lifecycle |
| products.csv | 대상 제품 확인 |
| compatibility.csv | MODEL/MATERIAL Compatibility |
| rules.csv | 설계변경 및 Review Rule |
| change_history.csv | Apply 변경 이력 / Workflow 연계 |
| suppliers.csv | 향후 공급사 검증 |
| data_dictionary.csv | 데이터 구조 정의 |
| test_questions.csv | Agent 평가 시나리오 |

## 3. 현재 적극 활용 영역
설계변경 분석에서 핵심적으로 다음 데이터를 사용한다.

```text
bom.csv
materials.csv
compatibility.csv
rules.csv
```

Review 기능에서도 Rule/Compatibility 검증결과를 저장하고 재검증하는 방향으로 확장되었다.

## 4. 데이터 변경 원칙
- 조회/분석은 원본 Production BOM을 변경하지 않는다.
- Preview는 별도 결과로 생성한다.
- 실제 Apply만 데이터 변경 책임을 가진다.
- Review BOM과 Production BOM의 책임을 분리한다.

향후 CSV를 DB로 교체하더라도 Service Contract를 최대한 유지한다.
