# MCP Capability Design

## 1. 기본 방향

현재 프로젝트 규모에서는 MCP Server를 업무별로 여러 개 생성하지 않는다.

하나의 `Display BOM MCP Server` 안에서 업무 Capability를 분리한다.

## 2. Capability 구성

### A. Query Capability

기존 v5 기능을 재사용한다.

```text
get_bom
list_products
search_product
list_materials
search_material
```

책임:
- BOM 조회
- 전체 제품 조회
- 조건 제품 검색
- 전체 자재 조회
- 조건 자재 검색

데이터 변경: 없음

### B. Design Change Analysis

Tool 예시:

```text
analyze_design_change
```

책임:
- 현재 BOM 확인
- 기존 자재 존재 여부 확인
- 신규 자재 정보 확인
- 승인 상태 확인
- Lifecycle 확인
- 호환성 확인
- 설계변경 Rule 확인
- 영향 범위 분석
- 변경 가능 여부 및 경고 반환

데이터 변경: 없음

### C. Design Change Apply

Tool 예시:

```text
apply_design_change
```

책임:
- 승인된 설계변경안을 실제 BOM에 반영
- Before / After 정보 생성
- 변경 결과 및 변경 이력 반환

데이터 변경: 있음

중요:
`analyze_design_change`와 `apply_design_change`는 반드시 분리한다.

### D. BOM Review

Tool 예시:

```text
evaluate_bom_review
```

책임:
- 품평회 Rule 검증
- 자재 승인 상태 검증
- Lifecycle 검증
- 호환성 검증
- 필수 항목 검증
- 설계변경 영향 검토
- PASS / CONDITIONAL / FAIL 판정

데이터 변경: 없음

### E. Report Generation

Tool 예시:

```text
generate_change_report
```

책임:
- 설계변경 분석 결과
- 변경 적용 결과
- 품평회 결과
- 경고 및 특이사항

등을 입력받아 완료 보고서 데이터를 생성한다.

보고서 Tool이 앞 단계의 판단을 다시 수행하지 않도록 책임을 제한한다.

## 3. 전체 MCP Tool 후보

```text
Display BOM MCP Server
│
├─ Query
│  ├─ get_bom
│  ├─ list_products
│  ├─ search_product
│  ├─ list_materials
│  └─ search_material
│
├─ analyze_design_change
├─ apply_design_change
├─ evaluate_bom_review
└─ generate_change_report
```
