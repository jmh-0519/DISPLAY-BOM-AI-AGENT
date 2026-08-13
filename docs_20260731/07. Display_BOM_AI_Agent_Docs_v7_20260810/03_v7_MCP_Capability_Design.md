# v7 MCP Capability Design

## 1. 기본 방향
v6에서 정의한 단일 `Display BOM MCP Server` 방향을 유지한다.

현재는 MCP 자체보다 Service 구현이 먼저 진행되었다. v7에서는 이미 검증된 Service를 MCP Capability로 감싸는 방식으로 진행한다.

## 2. Capability

### Query
```text
get_bom
list_products
search_product
list_materials
search_material
```

현재 Tool Registry / Executor 기반 기능을 재사용한다.

### Design Change Analysis
```text
analyze_design_change
```

현재 구현된 검증 범위:
- 대상 제품 확인
- 기존 자재 BOM 존재 확인
- 신규 자재 존재 확인
- 승인 상태
- Lifecycle
- Compatibility
- BOM Rule
- 변경 가능 여부
- Blocking Reason
- Conditional Review 항목

데이터 변경 없음.

### Design Change Apply
```text
apply_design_change
```

원칙:
- Analysis와 분리
- 실제 적용 전 Preview 지원
- Production BOM과 Preview 분리
- 변경 이력 관리 대상

### BOM Review
```text
evaluate_bom_review
```

현재 Review Service에서 구현/테스트된 범위:
- Review 생성
- Review BOM 수정
- 재검증
- Rule / Compatibility 결과 저장
- 이전 검증결과 교체
- Check Type 분류

### Report Generation
```text
generate_change_report
```

아직 구현 전이다.

## 3. 다음 구현 원칙
MCP Tool 내부에 Business Rule을 중복 구현하지 않는다.

```text
MCP Tool
   ↓
Existing Service
   ↓
Business Logic / Data
```

이 구조를 유지한다.
