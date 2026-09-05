# Display BOM Database Schema

## 1. Scope

`v4.0.0`은 SQLite를 PoC 업무 데이터의 Source of Truth로 사용합니다.

- `data/display_bom_seed.db`: Canonical Seed DB
- `data/display_bom.db`: Runtime / Demo DB
- pytest: Disposable Test DB

현재 Schema Version은 9입니다.

## 2. Master Authority

- `item_master`: global item identity, type, common display fields, active lifecycle
- `version_master`: VERSION / FA business attributes
- `assembly_master`: ASSY process / usage / specification
- `material_master`: MATERIAL group / unit / specification
- `supplier_items`: item-supplier relationship authority
- `bom_master`: BOM administration / effective period

## 3. BOM Ontology

```text
MODEL / PRODUCT
  ↓
VERSION
  ↓
PLANT
  ↓
BOM
  ↓
BOM EDGE = Parent + Child + LOCATION
```

동일 ASSY 하위 동일 품목은 LOCATION으로 구분할 수 있습니다.

## 4. Current Schema Normalization

### version_master

주요 typed attribute:

- product_name
- product_type
- screen_size_inch
- resolution
- refresh_hz
- market
- legacy_product_id
- material_specification
- dataset_tag

### assembly_master

ASSY 전용 process / usage / specification을 관리합니다.

### material_master

MATERIAL 전용 group / unit / specification을 관리합니다.

`item_master.item_name`이 품목명 semantic authority입니다.

### supplier_items

자재-공급사 관계의 단일 Authority이며 단가 / 납기 / 품질 / 공급 상태 Evidence를 제공합니다.

## 5. BOM Validity

Current effective BOM:

```sql
status = 'ACTIVE'
AND valid_from <= :as_of_date
AND (valid_to IS NULL OR valid_to >= :as_of_date)
```

BOM history row는 임의로 rewrite하지 않습니다.

## 6. Design Change Evidence

설계변경은 Analysis / Request / Approval / Preview / Apply Evidence를 분리하여 저장합니다.

- Analysis 중에는 Request / Production BOM write 없음
- Request는 사용자 진행 승인 후 생성
- Preview와 Final Approval 이후에만 Apply
- Apply는 Atomic Transaction
- History / Word Report는 persisted DB Evidence에서 생성

## 7. Migration

`database/migrations/v8_to_v9.py`와 `scripts/migrate_database_v8_to_v9.py`는 실제 Schema migration utility이므로 최종 소스에 유지합니다. 버전 번호는 개발 Task명이 아니라 DB Schema migration 계약입니다.
