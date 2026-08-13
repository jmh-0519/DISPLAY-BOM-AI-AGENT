# 데이터 모델

## 1. 데이터 모델 목표

합성 데이터로 Display BOM의 주요 구조와 검증 시나리오를 표현한다. 현재 CSV를 사용하지만 향후 관계형 DB로 이전할 수 있도록 식별자와 관계를 명확히 한다.

## 2. 파일 목록

| 파일 | 설명 |
|---|---|
| `products.csv` | 완제품 및 제품 모델 정보 |
| `materials.csv` | 조립품과 부품 마스터 |
| `bom.csv` | Parent-Child BOM 관계 |
| `suppliers.csv` | 공급업체 정보 |
| `rules.csv` | BOM 검증 규칙 |
| `compatibility.csv` | 부품 간 호환성 정보 |
| `change_history.csv` | 설계변경 및 변경 이력 |
| `test_questions.csv` | Agent 테스트 질문 |
| `data_dictionary.csv` | 데이터 사전 |

## 3. 핵심 관계

```text
Product 1 ── N BOM
Material 1 ── N BOM(parent)
Material 1 ── N BOM(child)
Supplier 1 ── N Material
Material N ── N Compatibility
Product/Material 1 ── N Change History
```

## 4. 주요 식별자

- `product_id`: 제품 식별자
- `material_id`: 자재 식별자
- `parent_id`: 상위 제품 또는 조립품
- `child_id`: 하위 조립품 또는 부품
- `supplier_id`: 공급업체 식별자
- `rule_id`: 검증 규칙 식별자
- `change_id`: 변경 이력 식별자

## 5. 현재 확인할 제약사항

- ID는 대소문자 차이 없이 검색한다.
- BOM의 `parent_id`, `child_id` 참조 무결성을 확인한다.
- 수량은 0보다 커야 한다.
- 버전과 유효 기간 적용 방식을 추후 정의한다.
- 자재의 승인 상태와 Lifecycle 상태를 별도로 관리한다.

## 6. 향후 DB 전환 시 고려사항

- PK 및 FK 제약조건
- 인덱스: `parent_id`, `child_id`, `material_id`, `product_id`
- BOM 버전 및 유효 시작/종료일
- 변경 이력의 감사 컬럼
- Soft Delete 또는 Lifecycle 상태 정책
- 조회 성능을 위한 Recursive Query 전략
