PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_versions (
  version INTEGER PRIMARY KEY,
  description TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_versions(version, description)
VALUES (2, 'STEP24-A2 v2 FA-root BOM domain schema');

INSERT OR IGNORE INTO schema_versions(version, description)
VALUES (3, 'STEP26-B Phase3 recommendation and multi-action workflow schema');

INSERT OR IGNORE INTO schema_versions(version, description)
VALUES (4, 'STEP27 Plant-scoped BOM and design-change reason metadata');

INSERT OR IGNORE INTO schema_versions(version, description)
VALUES (5, 'STEP30 ASSY process-name invariant and candidate display normalization');

INSERT OR IGNORE INTO schema_versions(version, description)
VALUES (6, 'STEP32 detailed evaluation evidence and impact analysis');

INSERT OR IGNORE INTO schema_versions(version, description)
VALUES (7, 'Clean Core schema without legacy review and superseded design-change tables');

CREATE TABLE IF NOT EXISTS plants (
  plant_code TEXT PRIMARY KEY,
  plant_name TEXT NOT NULL UNIQUE,
  country_code TEXT NOT NULL DEFAULT 'KR' CHECK(country_code IN ('KR','CN','VN')),
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N'))
);

INSERT INTO plants(plant_code,plant_name,country_code,active_yn) VALUES
  ('P01','국내 AA PLANT','KR','Y'),
  ('P02','국내 BB PLANT','KR','Y'),
  ('P03','중국 CC PLANT','CN','Y'),
  ('P04','베트남 DD PLANT','VN','Y')
ON CONFLICT(plant_code) DO UPDATE SET
  plant_name=excluded.plant_name,
  country_code=excluded.country_code,
  active_yn=excluded.active_yn;

CREATE TABLE IF NOT EXISTS supplier_master (
  supplier_code TEXT PRIMARY KEY,
  supplier_name TEXT NOT NULL UNIQUE,
  country TEXT,
  specialty TEXT,
  grade TEXT,
  quality_score REAL,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_master (
  customer_code TEXT PRIMARY KEY,
  customer_name TEXT NOT NULL UNIQUE,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_master (
  item_code TEXT PRIMARY KEY,
  item_type TEXT NOT NULL CHECK(item_type IN ('VERSION','ASSEMBLY','MATERIAL')),
  item_name TEXT NOT NULL,
  description TEXT,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS version_master (
  version_code TEXT PRIMARY KEY,
  version_no TEXT,
  route_code TEXT,
  specification TEXT,
  customer_code TEXT,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(version_code) REFERENCES item_master(item_code),
  FOREIGN KEY(customer_code) REFERENCES customer_master(customer_code)
);

CREATE TABLE IF NOT EXISTS assembly_master (
  assembly_code TEXT PRIMARY KEY,
  process_name TEXT NOT NULL
    CHECK(process_name IN ('OLB','CP','BIN','LC','CF','TFT')),
  usage_type TEXT NOT NULL DEFAULT 'DEDICATED'
    CHECK(usage_type IN ('COMMON','DEDICATED')),
  specification TEXT,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(assembly_code) REFERENCES item_master(item_code)
);

CREATE TABLE IF NOT EXISTS material_master (
  material_code TEXT PRIMARY KEY,
  material_name TEXT NOT NULL,
  material_group TEXT,
  unit TEXT,
  supplier_code TEXT,
  specification TEXT,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(material_code) REFERENCES item_master(item_code),
  FOREIGN KEY(supplier_code) REFERENCES supplier_master(supplier_code)
);

CREATE TABLE IF NOT EXISTS location_master (
  location_code TEXT PRIMARY KEY,
  location_name TEXT NOT NULL UNIQUE,
  sort_order INTEGER NOT NULL CHECK(sort_order >= 0),
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N'))
);

INSERT OR IGNORE INTO location_master(location_code, location_name, sort_order) VALUES
  ('N/A', '해당 없음', 0),
  ('ALL', '전체', 10),
  ('TOP', '상단', 20),
  ('BOTTOM', '하단', 30),
  ('LEFT', '좌측', 40),
  ('RIGHT', '우측', 50),
  ('TOP_LEFT', '좌측 상단', 60),
  ('TOP_RIGHT', '우측 상단', 70),
  ('BOTTOM_LEFT', '좌측 하단', 80),
  ('BOTTOM_RIGHT', '우측 하단', 90),
  ('CENTER', '중앙', 100);

CREATE TABLE IF NOT EXISTS bom_hierarchy_rules (
  parent_type TEXT NOT NULL,
  parent_process TEXT NOT NULL DEFAULT '',
  child_type TEXT NOT NULL,
  child_process TEXT NOT NULL DEFAULT '',
  description_ko TEXT,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  PRIMARY KEY(parent_type, parent_process, child_type, child_process),
  CHECK(parent_type IN ('VERSION','ASSEMBLY')),
  CHECK(child_type IN ('ASSEMBLY','MATERIAL'))
);

INSERT OR IGNORE INTO bom_hierarchy_rules
  (parent_type, parent_process, child_type, child_process, description_ko)
VALUES
  ('VERSION', '', 'ASSEMBLY', 'OLB', 'FA 하위 OLB'),
  ('VERSION', '', 'MATERIAL', '', 'FA 하위 일반 자재'),
  ('ASSEMBLY', 'OLB', 'ASSEMBLY', 'CP', 'OLB 하위 CP'),
  ('ASSEMBLY', 'OLB', 'MATERIAL', '', 'OLB 하위 일반 자재'),
  ('ASSEMBLY', 'CP', 'ASSEMBLY', 'BIN', 'CP 하위 BIN'),
  ('ASSEMBLY', 'CP', 'MATERIAL', '', 'CP 하위 일반 자재'),
  ('ASSEMBLY', 'BIN', 'ASSEMBLY', 'LC', 'BIN 하위 LC'),
  ('ASSEMBLY', 'BIN', 'MATERIAL', '', 'BIN 하위 일반 자재'),
  ('ASSEMBLY', 'LC', 'ASSEMBLY', 'CF', 'LC 하위 CF'),
  ('ASSEMBLY', 'LC', 'ASSEMBLY', 'TFT', 'LC 하위 TFT'),
  ('ASSEMBLY', 'LC', 'MATERIAL', '', 'LC 하위 일반 자재'),
  ('ASSEMBLY', 'CF', 'MATERIAL', '', 'CF 하위 일반 자재'),
  ('ASSEMBLY', 'TFT', 'MATERIAL', '', 'TFT 하위 일반 자재');

CREATE TABLE IF NOT EXISTS bom_master (
  bom_id INTEGER PRIMARY KEY AUTOINCREMENT,
  plant_code TEXT NOT NULL DEFAULT 'P01',
  parent_item_code TEXT NOT NULL,
  child_item_code TEXT NOT NULL,
  location_code TEXT NOT NULL DEFAULT 'N/A',
  sequence_no INTEGER NOT NULL DEFAULT 0 CHECK(sequence_no >= 0),
  quantity REAL NOT NULL CHECK(quantity > 0),
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  row_revision INTEGER NOT NULL DEFAULT 1 CHECK(row_revision >= 1),
  status TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK(status IN ('DRAFT','ACTIVE','INACTIVE')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(plant_code) REFERENCES plants(plant_code),
  FOREIGN KEY(parent_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(child_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(location_code) REFERENCES location_master(location_code),
  CHECK(parent_item_code <> child_item_code),
  CHECK(valid_to IS NULL OR valid_to >= valid_from),
  UNIQUE(plant_code, parent_item_code, child_item_code, location_code, valid_from)
);

CREATE TABLE IF NOT EXISTS query_aliases (
  alias TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  alias_type TEXT NOT NULL,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  PRIMARY KEY(alias, alias_type)
);

CREATE INDEX IF NOT EXISTS ix_item_name_type
  ON item_master(item_name, item_type);
CREATE INDEX IF NOT EXISTS ix_material_name
  ON material_master(material_name);
CREATE INDEX IF NOT EXISTS ix_bom_parent_dates
  ON bom_master(plant_code, parent_item_code, status, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_bom_child_dates
  ON bom_master(plant_code, child_item_code, status, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_bom_parent_sequence
  ON bom_master(plant_code, parent_item_code, sequence_no);

CREATE TRIGGER IF NOT EXISTS trg_version_item_type_insert
BEFORE INSERT ON version_master
FOR EACH ROW
WHEN COALESCE((SELECT item_type FROM item_master WHERE item_code = NEW.version_code), '') <> 'VERSION'
BEGIN
  SELECT RAISE(ABORT, 'version_master requires VERSION item');
END;

CREATE TRIGGER IF NOT EXISTS trg_assembly_item_type_insert
BEFORE INSERT ON assembly_master
FOR EACH ROW
WHEN COALESCE((SELECT item_type FROM item_master WHERE item_code = NEW.assembly_code), '') <> 'ASSEMBLY'
BEGIN
  SELECT RAISE(ABORT, 'assembly_master requires ASSEMBLY item');
END;


CREATE TRIGGER IF NOT EXISTS trg_item_assy_process_name_insert
BEFORE INSERT ON item_master
FOR EACH ROW
WHEN NEW.item_type='ASSEMBLY'
 AND NEW.item_name NOT IN ('OLB','CP','BIN','LC','CF','TFT')
BEGIN
  SELECT RAISE(ABORT, 'ASSEMBLY item_name must be a process name');
END;

CREATE TRIGGER IF NOT EXISTS trg_item_assy_process_name_update
BEFORE UPDATE OF item_type,item_name ON item_master
FOR EACH ROW
WHEN NEW.item_type='ASSEMBLY'
 AND NEW.item_name NOT IN ('OLB','CP','BIN','LC','CF','TFT')
BEGIN
  SELECT RAISE(ABORT, 'ASSEMBLY item_name must be a process name');
END;

CREATE TRIGGER IF NOT EXISTS trg_assembly_process_matches_item_insert
BEFORE INSERT ON assembly_master
FOR EACH ROW
WHEN COALESCE((SELECT item_name FROM item_master WHERE item_code=NEW.assembly_code), '') <> NEW.process_name
BEGIN
  SELECT RAISE(ABORT, 'ASSEMBLY item_name must match process_name');
END;

CREATE TRIGGER IF NOT EXISTS trg_assembly_process_matches_item_update
BEFORE UPDATE OF process_name ON assembly_master
FOR EACH ROW
WHEN COALESCE((SELECT item_name FROM item_master WHERE item_code=NEW.assembly_code), '') <> NEW.process_name
BEGIN
  SELECT RAISE(ABORT, 'ASSEMBLY item_name must match process_name');
END;

CREATE TRIGGER IF NOT EXISTS trg_material_item_type_insert
BEFORE INSERT ON material_master
FOR EACH ROW
WHEN COALESCE((SELECT item_type FROM item_master WHERE item_code = NEW.material_code), '') <> 'MATERIAL'
BEGIN
  SELECT RAISE(ABORT, 'material_master requires MATERIAL item');
END;

-- Phase3 item properties and registered substitution relations
CREATE TABLE IF NOT EXISTS item_attribute_values (
  item_code TEXT NOT NULL REFERENCES item_master(item_code),
  attribute_name TEXT NOT NULL,
  attribute_value TEXT,
  value_type TEXT NOT NULL DEFAULT 'TEXT' CHECK(value_type IN ('TEXT','NUMBER','BOOLEAN','DATE')),
  unit TEXT,
  valid_from TEXT NOT NULL DEFAULT '2000-01-01',
  valid_to TEXT,
  source TEXT NOT NULL DEFAULT 'MASTER',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(item_code, attribute_name, valid_from),
  CHECK(valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS substitution_relations (
  source_item_code TEXT NOT NULL REFERENCES item_master(item_code),
  candidate_item_code TEXT NOT NULL REFERENCES item_master(item_code),
  relation_type TEXT NOT NULL DEFAULT 'REGISTERED' CHECK(relation_type IN ('REGISTERED','ATTRIBUTE_SIMILAR','COMMONIZATION')),
  priority INTEGER NOT NULL DEFAULT 100,
  valid_from TEXT NOT NULL DEFAULT '2000-01-01',
  valid_to TEXT,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(source_item_code, candidate_item_code, valid_from),
  CHECK(source_item_code <> candidate_item_code),
  CHECK(valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS supplier_items (
  supplier_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_code TEXT NOT NULL REFERENCES supplier_master(supplier_code),
  item_code TEXT NOT NULL REFERENCES item_master(item_code),
  unit_price REAL CHECK(unit_price IS NULL OR unit_price >= 0),
  currency_code TEXT NOT NULL DEFAULT 'KRW',
  lead_time_days INTEGER CHECK(lead_time_days IS NULL OR lead_time_days >= 0),
  quality_grade TEXT,
  stability_score REAL CHECK(stability_score IS NULL OR (stability_score >= 0 AND stability_score <= 100)),
  primary_yn TEXT NOT NULL DEFAULT 'N' CHECK(primary_yn IN ('Y','N')),
  supply_status TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK(supply_status IN ('AVAILABLE','LIMITED','STOPPED')),
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(supplier_code, item_code, valid_from),
  CHECK(valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS warehouses (
  warehouse_code TEXT PRIMARY KEY,
  plant_code TEXT NOT NULL REFERENCES plants(plant_code),
  warehouse_name TEXT NOT NULL,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  UNIQUE(plant_code, warehouse_name)
);

CREATE TABLE IF NOT EXISTS inventory_locations (
  inventory_location_code TEXT PRIMARY KEY,
  warehouse_code TEXT NOT NULL REFERENCES warehouses(warehouse_code),
  location_name TEXT NOT NULL,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  UNIQUE(warehouse_code, location_name)
);

CREATE TABLE IF NOT EXISTS inventory_balances (
  inventory_location_code TEXT NOT NULL REFERENCES inventory_locations(inventory_location_code),
  item_code TEXT NOT NULL REFERENCES item_master(item_code),
  on_hand_quantity REAL NOT NULL DEFAULT 0 CHECK(on_hand_quantity >= 0),
  reserved_quantity REAL NOT NULL DEFAULT 0 CHECK(reserved_quantity >= 0),
  safety_stock REAL NOT NULL DEFAULT 0 CHECK(safety_stock >= 0),
  hold_quantity REAL NOT NULL DEFAULT 0 CHECK(hold_quantity >= 0),
  incoming_quantity REAL NOT NULL DEFAULT 0 CHECK(incoming_quantity >= 0),
  incoming_date TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(inventory_location_code, item_code)
);

CREATE TABLE IF NOT EXISTS production_plans (
  plan_id TEXT PRIMARY KEY,
  version_code TEXT NOT NULL REFERENCES version_master(version_code),
  plant_code TEXT NOT NULL REFERENCES plants(plant_code),
  plan_date TEXT NOT NULL,
  planned_quantity REAL NOT NULL CHECK(planned_quantity > 0),
  status TEXT NOT NULL DEFAULT 'CONFIRMED' CHECK(status IN ('DRAFT','CONFIRMED','CANCELLED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(version_code, plant_code, plan_date)
);

CREATE TABLE IF NOT EXISTS change_reason_master (
  reason_code TEXT PRIMARY KEY,
  reason_name_ko TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  category TEXT NOT NULL,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  valid_from TEXT NOT NULL DEFAULT '2026-01-01',
  valid_to TEXT,
  CHECK(valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS change_reason_alias (
  alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
  alias_text TEXT NOT NULL,
  normalized_alias TEXT NOT NULL,
  reason_code TEXT NOT NULL REFERENCES change_reason_master(reason_code),
  language_code TEXT NOT NULL DEFAULT 'KO' CHECK(language_code IN ('KO','EN')),
  match_type TEXT NOT NULL DEFAULT 'EXACT' CHECK(match_type IN ('EXACT','KEYWORD')),
  priority INTEGER NOT NULL DEFAULT 100 CHECK(priority >= 1),
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  UNIQUE(normalized_alias,reason_code)
);

CREATE TABLE IF NOT EXISTS change_reason_scope (
  reason_code TEXT NOT NULL REFERENCES change_reason_master(reason_code),
  target_type TEXT NOT NULL CHECK(target_type IN ('MATERIAL','ASSY')),
  action_type TEXT NOT NULL CHECK(action_type IN ('REPLACE','ADD','DELETE','QUANTITY_CHANGE')),
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  PRIMARY KEY(reason_code,target_type,action_type)
);

CREATE TABLE IF NOT EXISTS change_reason_evidence_rules (
  evidence_rule_id TEXT PRIMARY KEY,
  reason_code TEXT NOT NULL REFERENCES change_reason_master(reason_code),
  target_type TEXT NOT NULL CHECK(target_type IN ('MATERIAL','ASSY','ALL')),
  attribute_name TEXT NOT NULL,
  operator TEXT NOT NULL CHECK(operator IN ('EQ','NE','GT','GE','LT','LE','IN','PRESENT')),
  expected_value TEXT,
  evidence_role TEXT NOT NULL DEFAULT 'SUPPORT' CHECK(evidence_role IN ('SUPPORT','CONFLICT')),
  required_yn TEXT NOT NULL DEFAULT 'N' CHECK(required_yn IN ('Y','N')),
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N'))
);

INSERT OR IGNORE INTO change_reason_master
  (reason_code,reason_name_ko,description,category)
VALUES
  ('EOL','단종 대응','품목의 생산 또는 공급 수명 종료에 대응','LIFECYCLE'),
  ('SUPPLIER_STOP','공급 중단 대응','특정 공급사의 공급 중단에 대응','SUPPLY'),
  ('LEAD_TIME','납기 개선','조달 또는 생산 납기 단축','SUPPLY'),
  ('COST','원가 절감','구매비 또는 제조비 절감','COST'),
  ('INVENTORY','재고 문제 대응','재고 부족·과잉·장기재고 문제 해결','INVENTORY'),
  ('QUALITY','품질 개선','불량·신뢰성·성능 문제 개선','QUALITY'),
  ('CUSTOMER_SPEC','고객 사양 대응','고객 요구사항 신규 또는 변경 대응','SPECIFICATION'),
  ('REGULATION','규제 대응','법규·환경·인증 조건 충족','REGULATION'),
  ('COMMONIZATION','부품 공용화','모델 간 자재 또는 ASSY 통합','COMMONIZATION'),
  ('USER_REQUEST','사용자 요청','사용자가 별도 업무 사유를 명시하지 않은 직접 설계변경 요청','GENERAL');

INSERT OR IGNORE INTO change_reason_alias
  (alias_text,normalized_alias,reason_code,language_code,match_type,priority)
VALUES
  ('단종','단종','EOL','KO','KEYWORD',10),
  ('생산 종료','생산종료','EOL','KO','KEYWORD',20),
  ('END OF LIFE','ENDOFLIFE','EOL','EN','KEYWORD',20),
  ('OBSOLETE','OBSOLETE','EOL','EN','KEYWORD',20),
  ('DISCONTINUED','DISCONTINUED','EOL','EN','KEYWORD',20),
  ('공급 중단','공급중단','SUPPLIER_STOP','KO','KEYWORD',10),
  ('납품 중단','납품중단','SUPPLIER_STOP','KO','KEYWORD',20),
  ('납기','납기','LEAD_TIME','KO','KEYWORD',10),
  ('LEAD TIME','LEADTIME','LEAD_TIME','EN','KEYWORD',20),
  ('원가','원가','COST','KO','KEYWORD',10),
  ('단가 절감','단가절감','COST','KO','KEYWORD',20),
  ('재고','재고','INVENTORY','KO','KEYWORD',10),
  ('품질','품질','QUALITY','KO','KEYWORD',10),
  ('고객 사양','고객사양','CUSTOMER_SPEC','KO','KEYWORD',10),
  ('규제','규제','REGULATION','KO','KEYWORD',10),
  ('인증','인증','REGULATION','KO','KEYWORD',20),
  ('공용화','공용화','COMMONIZATION','KO','KEYWORD',10),
  ('공통화','공통화','COMMONIZATION','KO','KEYWORD',20);

INSERT OR IGNORE INTO change_reason_scope(reason_code,target_type,action_type)
SELECT reason_code,target_type,action_type FROM (
  SELECT 'EOL' reason_code,'MATERIAL' target_type,'REPLACE' action_type UNION ALL
  SELECT 'EOL','ASSY','REPLACE' UNION ALL
  SELECT 'SUPPLIER_STOP','MATERIAL','REPLACE' UNION ALL
  SELECT 'SUPPLIER_STOP','ASSY','REPLACE' UNION ALL
  SELECT 'LEAD_TIME','MATERIAL','REPLACE' UNION ALL
  SELECT 'LEAD_TIME','ASSY','REPLACE' UNION ALL
  SELECT 'COST','MATERIAL','REPLACE' UNION ALL
  SELECT 'COST','ASSY','REPLACE' UNION ALL
  SELECT 'INVENTORY','MATERIAL','REPLACE' UNION ALL
  SELECT 'INVENTORY','ASSY','REPLACE' UNION ALL
  SELECT 'QUALITY','MATERIAL','REPLACE' UNION ALL
  SELECT 'QUALITY','ASSY','REPLACE' UNION ALL
  SELECT 'CUSTOMER_SPEC','MATERIAL','ADD' UNION ALL
  SELECT 'CUSTOMER_SPEC','MATERIAL','REPLACE' UNION ALL
  SELECT 'CUSTOMER_SPEC','ASSY','ADD' UNION ALL
  SELECT 'CUSTOMER_SPEC','ASSY','REPLACE' UNION ALL
  SELECT 'REGULATION','MATERIAL','REPLACE' UNION ALL
  SELECT 'REGULATION','ASSY','REPLACE' UNION ALL
  SELECT 'COMMONIZATION','MATERIAL','REPLACE' UNION ALL
  SELECT 'COMMONIZATION','MATERIAL','DELETE' UNION ALL
  SELECT 'COMMONIZATION','MATERIAL','QUANTITY_CHANGE' UNION ALL
  SELECT 'COMMONIZATION','ASSY','REPLACE' UNION ALL
  SELECT 'COMMONIZATION','ASSY','QUANTITY_CHANGE' UNION ALL
  SELECT 'USER_REQUEST','MATERIAL','REPLACE' UNION ALL
  SELECT 'USER_REQUEST','MATERIAL','ADD' UNION ALL
  SELECT 'USER_REQUEST','MATERIAL','DELETE' UNION ALL
  SELECT 'USER_REQUEST','MATERIAL','QUANTITY_CHANGE' UNION ALL
  SELECT 'USER_REQUEST','ASSY','REPLACE' UNION ALL
  SELECT 'USER_REQUEST','ASSY','ADD' UNION ALL
  SELECT 'USER_REQUEST','ASSY','DELETE' UNION ALL
  SELECT 'USER_REQUEST','ASSY','QUANTITY_CHANGE'
);

INSERT OR IGNORE INTO change_reason_evidence_rules
  (evidence_rule_id,reason_code,target_type,attribute_name,operator,expected_value,evidence_role,required_yn)
VALUES
  ('RE-EOL-001','EOL','ALL','lifecycle_status','EQ','EOL','SUPPORT','N'),
  ('RE-SUP-001','SUPPLIER_STOP','ALL','supply_status','EQ','STOPPED','SUPPORT','N'),
  ('RE-INV-001','INVENTORY','ALL','shortage_quantity','GT','0','SUPPORT','N'),
  ('RE-QUA-001','QUALITY','ALL','quality_status','IN','FAIL,HOLD','SUPPORT','N');

CREATE TABLE IF NOT EXISTS rule_definitions (
  rule_id TEXT PRIMARY KEY,
  rule_name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rule_revisions (
  rule_id TEXT NOT NULL REFERENCES rule_definitions(rule_id),
  revision_no INTEGER NOT NULL CHECK(revision_no >= 1),
  target_type TEXT NOT NULL CHECK(target_type IN ('MATERIAL','ASSY','ALL')),
  change_reason TEXT NOT NULL,
  evaluation_item TEXT NOT NULL,
  required_yn TEXT NOT NULL DEFAULT 'N' CHECK(required_yn IN ('Y','N')),
  weight REAL NOT NULL CHECK(weight >= 0),
  pass_score REAL,
  conditional_score REAL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  active_yn TEXT NOT NULL DEFAULT 'N' CHECK(active_yn IN ('Y','N')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(rule_id, revision_no),
  FOREIGN KEY(change_reason) REFERENCES change_reason_master(reason_code),
  CHECK(valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS rule_conditions (
  rule_id TEXT NOT NULL,
  revision_no INTEGER NOT NULL,
  condition_seq INTEGER NOT NULL CHECK(condition_seq >= 1),
  attribute_name TEXT NOT NULL,
  operator TEXT NOT NULL CHECK(operator IN ('EQ','NE','GT','GE','LT','LE','IN','PRESENT')),
  expected_value TEXT,
  missing_result TEXT NOT NULL DEFAULT 'CONDITIONAL' CHECK(missing_result IN ('CONDITIONAL','FAIL')),
  fail_result TEXT NOT NULL DEFAULT 'FAIL' CHECK(fail_result IN ('CONDITIONAL','FAIL')),
  score REAL NOT NULL DEFAULT 100 CHECK(score >= 0 AND score <= 100),
  PRIMARY KEY(rule_id, revision_no, condition_seq),
  FOREIGN KEY(rule_id, revision_no) REFERENCES rule_revisions(rule_id, revision_no)
);

CREATE TABLE IF NOT EXISTS change_requests (
  request_id TEXT PRIMARY KEY,
  plant_code TEXT NOT NULL DEFAULT 'P01' REFERENCES plants(plant_code),
  version_code TEXT NOT NULL REFERENCES version_master(version_code),
  original_request TEXT,
  normalized_request TEXT,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  as_of_date TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  demand_quantity REAL CHECK(demand_quantity IS NULL OR demand_quantity > 0),
  demand_source TEXT NOT NULL CHECK(demand_source IN ('USER','PRODUCTION_PLAN','UNAVAILABLE')),
  workflow_status TEXT NOT NULL DEFAULT 'REQUESTED',
  candidate_approval_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(candidate_approval_status IN ('PENDING','APPROVED','REJECTED')),
  final_approval_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(final_approval_status IN ('PENDING','APPROVED','REJECTED')),
  apply_status TEXT NOT NULL DEFAULT 'NOT_APPLIED' CHECK(apply_status IN ('NOT_APPLIED','APPLIED','BLOCKED','FAILED')),
  requested_by TEXT NOT NULL,
  row_revision INTEGER NOT NULL DEFAULT 1 CHECK(row_revision >= 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK(effective_date >= as_of_date)
);

CREATE TABLE IF NOT EXISTS change_actions (
  action_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES change_requests(request_id),
  action_seq INTEGER NOT NULL CHECK(action_seq >= 1),
  plant_code TEXT NOT NULL DEFAULT 'P01' REFERENCES plants(plant_code),
  action_type TEXT NOT NULL CHECK(action_type IN ('REPLACE','ADD','DELETE','QUANTITY_CHANGE')),
  target_type TEXT NOT NULL CHECK(target_type IN ('MATERIAL','ASSY')),
  parent_item_code TEXT NOT NULL REFERENCES item_master(item_code),
  old_item_code TEXT REFERENCES item_master(item_code),
  new_item_code TEXT REFERENCES item_master(item_code),
  location_code TEXT NOT NULL REFERENCES location_master(location_code),
  old_quantity REAL,
  new_quantity REAL,
  evaluation_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(evaluation_status IN ('PENDING','PASS','CONDITIONAL','FAIL')),
  selected_candidate_id TEXT,
  selected_supplier_item_id INTEGER REFERENCES supplier_items(supplier_item_id),
  row_revision INTEGER NOT NULL DEFAULT 1 CHECK(row_revision >= 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(request_id, action_seq)
);

CREATE TABLE IF NOT EXISTS change_action_reasons (
  action_id TEXT NOT NULL REFERENCES change_actions(action_id) ON DELETE CASCADE,
  reason_code TEXT NOT NULL REFERENCES change_reason_master(reason_code),
  raw_reason_text TEXT,
  llm_reason_code TEXT,
  resolution_status TEXT NOT NULL
    CHECK(resolution_status IN ('RESOLVED','REASON_RESOLUTION_REQUIRED','CONFLICT')),
  resolution_source TEXT NOT NULL,
  confidence REAL CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1),
  is_primary TEXT NOT NULL DEFAULT 'Y' CHECK(is_primary IN ('Y','N')),
  confirmed_by TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(action_id,reason_code)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_change_action_primary_reason
  ON change_action_reasons(action_id) WHERE is_primary='Y';

CREATE TABLE IF NOT EXISTS candidate_evaluations (
  candidate_id TEXT PRIMARY KEY,
  action_id TEXT NOT NULL REFERENCES change_actions(action_id),
  plant_code TEXT NOT NULL DEFAULT 'P01' REFERENCES plants(plant_code),
  candidate_item_code TEXT NOT NULL REFERENCES item_master(item_code),
  recommended_supplier_item_id INTEGER REFERENCES supplier_items(supplier_item_id),
  final_status TEXT NOT NULL CHECK(final_status IN ('PASS','CONDITIONAL','FAIL')),
  total_score REAL NOT NULL CHECK(total_score >= 0 AND total_score <= 100),
  grade TEXT NOT NULL CHECK(grade IN ('S','A','B','C')),
  rank_no INTEGER,
  missing_data_json TEXT NOT NULL DEFAULT '[]',
  conditional_reasons_json TEXT NOT NULL DEFAULT '[]',
  attribute_comparison_json TEXT NOT NULL DEFAULT '{}',
  inventory_result_json TEXT NOT NULL DEFAULT '{}',
  supplier_evaluation_json TEXT NOT NULL DEFAULT '{}',
  demand_context_json TEXT NOT NULL DEFAULT '{}',
  impact_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(action_id, candidate_item_code)
);

CREATE TABLE IF NOT EXISTS candidate_rule_results (
  candidate_id TEXT NOT NULL REFERENCES candidate_evaluations(candidate_id),
  result_seq INTEGER NOT NULL CHECK(result_seq >= 1),
  rule_id TEXT NOT NULL,
  rule_revision INTEGER NOT NULL,
  rule_snapshot_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PASS','CONDITIONAL','FAIL')),
  raw_score REAL NOT NULL,
  weight REAL NOT NULL,
  weighted_score REAL NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY(candidate_id, result_seq)
);

CREATE TABLE IF NOT EXISTS change_approvals (
  approval_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES change_requests(request_id),
  approval_stage TEXT NOT NULL CHECK(approval_stage IN ('CANDIDATE','FINAL_APPLY','CONDITIONAL_EXCEPTION')),
  decision TEXT NOT NULL CHECK(decision IN ('APPROVED','REJECTED')),
  decision_reason TEXT,
  selection_json TEXT NOT NULL DEFAULT '{}',
  approved_by TEXT NOT NULL,
  approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(request_id, approval_stage, approved_at)
);

CREATE TABLE IF NOT EXISTS change_impacts (
  request_id TEXT NOT NULL REFERENCES change_requests(request_id),
  action_id TEXT NOT NULL REFERENCES change_actions(action_id),
  plant_code TEXT NOT NULL DEFAULT 'P01' REFERENCES plants(plant_code),
  impacted_item_code TEXT NOT NULL REFERENCES item_master(item_code),
  impact_type TEXT NOT NULL CHECK(impact_type IN ('TARGET','PARENT_ASSY','MODEL','MODEL_CONNECTION')),
  impact_path TEXT NOT NULL,
  PRIMARY KEY(request_id, action_id, plant_code, impacted_item_code, impact_type)
);

CREATE TABLE IF NOT EXISTS change_previews (
  preview_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES change_requests(request_id),
  plant_code TEXT NOT NULL DEFAULT 'P01' REFERENCES plants(plant_code),
  preview_revision INTEGER NOT NULL CHECK(preview_revision >= 1),
  validation_status TEXT NOT NULL CHECK(validation_status IN ('PASS','CONDITIONAL','FAIL')),
  snapshot_json TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(request_id, preview_revision)
);

CREATE TABLE IF NOT EXISTS change_apply_results (
  apply_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES change_requests(request_id),
  plant_code TEXT NOT NULL DEFAULT 'P01' REFERENCES plants(plant_code),
  preview_id TEXT NOT NULL REFERENCES change_previews(preview_id),
  final_approval_id TEXT NOT NULL REFERENCES change_approvals(approval_id),
  result TEXT NOT NULL CHECK(result IN ('APPLIED','ROLLED_BACK','BLOCKED')),
  applied_by TEXT NOT NULL,
  result_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(request_id)
);

CREATE TABLE IF NOT EXISTS decision_traces (
  trace_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES change_requests(request_id),
  event_type TEXT NOT NULL,
  anonymized_input_json TEXT NOT NULL DEFAULT '{}',
  decision_json TEXT NOT NULL DEFAULT '{}',
  feedback_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS performance_outcomes (
  outcome_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES change_requests(request_id),
  measurement_day INTEGER NOT NULL CHECK(measurement_day IN (30,60,90)),
  outcome_json TEXT NOT NULL,
  user_rating INTEGER CHECK(user_rating IS NULL OR user_rating BETWEEN 1 AND 5),
  measured_at TEXT NOT NULL,
  UNIQUE(request_id, measurement_day)
);

CREATE TABLE IF NOT EXISTS dataset_exports (
  export_id TEXT PRIMARY KEY,
  date_from TEXT,
  date_to TEXT,
  record_count INTEGER NOT NULL CHECK(record_count >= 0),
  checksum TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_attributes_item_date ON item_attribute_values(item_code, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_substitution_source_date ON substitution_relations(source_item_code, active_yn, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_supplier_items_item_date ON supplier_items(item_code, supply_status, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_inventory_item ON inventory_balances(item_code);
CREATE INDEX IF NOT EXISTS ix_plan_version_date ON production_plans(plant_code, version_code, plan_date, status);
CREATE INDEX IF NOT EXISTS ix_rule_active_date ON rule_revisions(change_reason, target_type, active_yn, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_request_status ON change_requests(plant_code, workflow_status, apply_status);
CREATE INDEX IF NOT EXISTS ix_action_request ON change_actions(request_id, action_seq);
CREATE INDEX IF NOT EXISTS ix_candidate_action_rank ON candidate_evaluations(action_id, final_status, rank_no);
CREATE INDEX IF NOT EXISTS ix_approval_request_stage ON change_approvals(request_id, approval_stage);
CREATE INDEX IF NOT EXISTS ix_impact_item ON change_impacts(impacted_item_code);
