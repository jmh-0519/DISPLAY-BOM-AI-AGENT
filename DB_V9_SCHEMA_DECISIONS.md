# Display BOM DB v9 — Schema Decisions

## Authority

- `item_master`: global item identity, type, common display fields, active lifecycle and timestamps.
- `version_master`: VERSION/FA-only business attributes.
- `assembly_master`: ASSY-only process/usage/specification attributes.
- `material_master`: MATERIAL-only group/unit/specification attributes.
- `supplier_items`: the only item-supplier relationship authority.
- `bom_master.status`: administrative row state. Effective BOM also requires valid_from/valid_to date conditions.

## v9 physical changes

### version_master

Removed:
- route_code
- specification JSON
- active_yn
- created_at
- updated_at

Added typed columns:
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

Removed:
- active_yn
- created_at
- updated_at

### material_master

Removed:
- supplier_code
- active_yn
- created_at
- updated_at

`material_name` is intentionally retained for one compatibility release because the current
repository/test suite contains direct SQL references. `item_master.item_name` is the semantic
authority. v9 adds insert/update triggers that prevent the mirror from diverging.

## Supplier migration policy

Legacy `material_master.supplier_code` is not copied into `supplier_items` because the audit
showed that it uses a different supplier-code population and conflicts with the current primary
supplier relationship. Existing `supplier_items` rows remain unchanged.

## BOM validity policy

No BOM history rows are rewritten.

Current effective BOM means:

`status='ACTIVE' AND valid_from <= :as_of_date AND (valid_to IS NULL OR valid_to >= :as_of_date)`
