PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_versions (
  version INTEGER PRIMARY KEY,
  description TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_versions(version, description)
VALUES (2, 'STEP24-A2 v2 FA-root BOM domain schema');

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
  FOREIGN KEY(parent_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(child_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(location_code) REFERENCES location_master(location_code),
  CHECK(parent_item_code <> child_item_code),
  CHECK(valid_to IS NULL OR valid_to >= valid_from),
  UNIQUE(parent_item_code, child_item_code, location_code, valid_from)
);

CREATE TABLE IF NOT EXISTS material_attributes (
  item_code TEXT NOT NULL,
  attribute_name TEXT NOT NULL,
  attribute_value TEXT,
  unit TEXT,
  PRIMARY KEY(item_code, attribute_name),
  FOREIGN KEY(item_code) REFERENCES item_master(item_code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS material_compatibility (
  compatibility_id TEXT PRIMARY KEY,
  source_item_code TEXT NOT NULL,
  target_type TEXT NOT NULL
    CHECK(target_type IN ('MATERIAL','VERSION','ASSEMBLY','MATERIAL_GROUP')),
  target_code TEXT NOT NULL,
  result TEXT NOT NULL
    CHECK(result IN ('COMPATIBLE','CONDITIONAL','INCOMPATIBLE')),
  reason TEXT,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  FOREIGN KEY(source_item_code) REFERENCES item_master(item_code)
);

CREATE TABLE IF NOT EXISTS design_rules (
  rule_id TEXT PRIMARY KEY,
  rule_type TEXT NOT NULL,
  rule_name TEXT NOT NULL,
  scope TEXT,
  condition_expression TEXT,
  severity TEXT,
  active_yn TEXT NOT NULL DEFAULT 'Y' CHECK(active_yn IN ('Y','N')),
  metric TEXT,
  operator TEXT,
  expected_value TEXT,
  expected_value_max TEXT,
  unit TEXT,
  aggregation TEXT,
  target_category TEXT,
  message_ko TEXT
);

CREATE TABLE IF NOT EXISTS design_changes (
  change_id TEXT PRIMARY KEY,
  version_code TEXT NOT NULL,
  change_type TEXT NOT NULL
    CHECK(change_type IN ('REPLACE','ADD','DELETE','QUANTITY_CHANGE')),
  requested_date TEXT NOT NULL,
  effective_date TEXT,
  reason TEXT,
  analysis_result TEXT NOT NULL DEFAULT 'PENDING'
    CHECK(analysis_result IN ('PENDING','PASS','CONDITIONAL','FAIL')),
  approval_status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK(approval_status IN ('PENDING','AI_REVIEW_PENDING','APPROVED','REJECTED')),
  apply_status TEXT NOT NULL DEFAULT 'REQUESTED'
    CHECK(apply_status IN ('REQUESTED','REVIEW_READY','IN_REVIEW','APPROVED_TO_APPLY',
                           'APPLIED','VALIDATION_FAILED','APPLY_FAILED')),
  workflow_status TEXT NOT NULL DEFAULT 'REQUESTED'
    CHECK(workflow_status IN ('REQUESTED','ANALYZED','REVIEW_READY','IN_REVIEW',
                              'AWAITING_HUMAN_APPROVAL','APPROVED_TO_APPLY','REJECTED',
                              'APPLIED','VALIDATION_FAILED','APPLY_FAILED')),
  expected_bom_revision INTEGER CHECK(expected_bom_revision IS NULL OR expected_bom_revision >= 1),
  row_revision INTEGER NOT NULL DEFAULT 1 CHECK(row_revision >= 1),
  requested_by TEXT,
  approved_by TEXT,
  approved_at TEXT,
  applied_by TEXT,
  applied_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(version_code) REFERENCES version_master(version_code)
);

CREATE TABLE IF NOT EXISTS design_change_items (
  change_id TEXT NOT NULL,
  item_seq INTEGER NOT NULL CHECK(item_seq >= 1),
  action TEXT NOT NULL
    CHECK(action IN ('REPLACE','ADD','DELETE','QUANTITY_CHANGE')),
  parent_item_code TEXT NOT NULL,
  old_item_code TEXT,
  new_item_code TEXT,
  location_code TEXT NOT NULL DEFAULT 'N/A',
  sequence_no INTEGER,
  quantity REAL CHECK(quantity IS NULL OR quantity > 0),
  effective_date TEXT,
  PRIMARY KEY(change_id, item_seq),
  FOREIGN KEY(change_id) REFERENCES design_changes(change_id) ON DELETE CASCADE,
  FOREIGN KEY(parent_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(old_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(new_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(location_code) REFERENCES location_master(location_code),
  CHECK(action <> 'REPLACE' OR
        (old_item_code IS NOT NULL AND new_item_code IS NOT NULL
         AND old_item_code <> new_item_code))
);

CREATE TABLE IF NOT EXISTS design_change_checks (
  change_id TEXT NOT NULL,
  item_seq INTEGER NOT NULL,
  check_seq INTEGER NOT NULL,
  check_type TEXT NOT NULL,
  target_code TEXT,
  result TEXT NOT NULL CHECK(result IN ('PASS','CONDITIONAL','FAIL')),
  actual_value TEXT,
  expected_value TEXT,
  blocking_yn TEXT NOT NULL CHECK(blocking_yn IN ('Y','N')),
  message TEXT,
  checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(change_id, item_seq, check_seq),
  FOREIGN KEY(change_id, item_seq)
    REFERENCES design_change_items(change_id, item_seq) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS design_change_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  change_id TEXT NOT NULL UNIQUE,
  version_code TEXT NOT NULL,
  source_bom_revision INTEGER NOT NULL CHECK(source_bom_revision >= 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(change_id) REFERENCES design_changes(change_id) ON DELETE CASCADE,
  FOREIGN KEY(version_code) REFERENCES version_master(version_code)
);

CREATE TABLE IF NOT EXISTS design_change_snapshot_items (
  snapshot_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id TEXT NOT NULL,
  parent_item_code TEXT NOT NULL,
  child_item_code TEXT NOT NULL,
  location_code TEXT NOT NULL,
  sequence_no INTEGER NOT NULL,
  quantity REAL NOT NULL CHECK(quantity > 0),
  level INTEGER NOT NULL CHECK(level >= 1),
  bom_path TEXT NOT NULL,
  required_quantity REAL NOT NULL CHECK(required_quantity > 0),
  change_action TEXT NOT NULL,
  FOREIGN KEY(snapshot_id) REFERENCES design_change_snapshots(snapshot_id) ON DELETE CASCADE,
  FOREIGN KEY(parent_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(child_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(location_code) REFERENCES location_master(location_code),
  UNIQUE(snapshot_id, bom_path)
);

CREATE TABLE IF NOT EXISTS review_boms (
  review_id TEXT PRIMARY KEY,
  change_id TEXT NOT NULL UNIQUE,
  version_code TEXT NOT NULL,
  review_status TEXT NOT NULL
    CHECK(review_status IN ('CREATED','IN_REVIEW','RECHECK_REQUIRED',
                            'AWAITING_HUMAN_APPROVAL','APPROVED','REJECTED','COMPLETED')),
  current_revision INTEGER NOT NULL DEFAULT 1 CHECK(current_revision >= 1),
  approved_revision INTEGER,
  created_by TEXT,
  reviewed_by TEXT,
  decision_reason TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(change_id) REFERENCES design_changes(change_id),
  FOREIGN KEY(version_code) REFERENCES version_master(version_code),
  CHECK(approved_revision IS NULL OR approved_revision >= 1)
);

CREATE TABLE IF NOT EXISTS review_bom_revisions (
  review_id TEXT NOT NULL,
  revision_no INTEGER NOT NULL CHECK(revision_no >= 1),
  based_on_revision INTEGER,
  source TEXT NOT NULL,
  created_by TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(review_id, revision_no),
  FOREIGN KEY(review_id) REFERENCES review_boms(review_id) ON DELETE CASCADE,
  CHECK(based_on_revision IS NULL OR based_on_revision < revision_no)
);

CREATE TABLE IF NOT EXISTS review_bom_items (
  review_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id TEXT NOT NULL,
  revision_no INTEGER NOT NULL,
  version_code TEXT NOT NULL,
  parent_item_code TEXT NOT NULL,
  child_item_code TEXT NOT NULL,
  location_code TEXT NOT NULL,
  sequence_no INTEGER NOT NULL,
  quantity REAL NOT NULL CHECK(quantity > 0),
  level INTEGER NOT NULL CHECK(level >= 1),
  bom_path TEXT NOT NULL,
  required_quantity REAL NOT NULL CHECK(required_quantity > 0),
  review_action TEXT NOT NULL,
  source TEXT,
  modified_yn TEXT NOT NULL DEFAULT 'N' CHECK(modified_yn IN ('Y','N')),
  modified_by TEXT,
  modified_at TEXT,
  remark TEXT,
  FOREIGN KEY(review_id, revision_no)
    REFERENCES review_bom_revisions(review_id, revision_no) ON DELETE CASCADE,
  FOREIGN KEY(version_code) REFERENCES version_master(version_code),
  FOREIGN KEY(parent_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(child_item_code) REFERENCES item_master(item_code),
  FOREIGN KEY(location_code) REFERENCES location_master(location_code),
  UNIQUE(review_id, revision_no, bom_path)
);

CREATE TABLE IF NOT EXISTS bom_reviews (
  bom_review_id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL,
  revision_no INTEGER NOT NULL,
  reviewer_type TEXT NOT NULL CHECK(reviewer_type IN ('AI','HUMAN')),
  result TEXT NOT NULL
    CHECK(result IN ('PENDING','PASS','CONDITIONAL','FAIL','APPROVED','REJECTED')),
  reviewer_id TEXT,
  decision_reason TEXT,
  started_at TEXT,
  completed_at TEXT,
  FOREIGN KEY(review_id, revision_no)
    REFERENCES review_bom_revisions(review_id, revision_no) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bom_review_checks (
  bom_review_id TEXT NOT NULL,
  check_seq INTEGER NOT NULL,
  check_type TEXT NOT NULL,
  target_code TEXT,
  result TEXT NOT NULL CHECK(result IN ('PASS','CONDITIONAL','FAIL')),
  actual_value TEXT,
  expected_value TEXT,
  blocking_yn TEXT NOT NULL CHECK(blocking_yn IN ('Y','N')),
  message TEXT,
  checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(bom_review_id, check_seq),
  FOREIGN KEY(bom_review_id) REFERENCES bom_reviews(bom_review_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_checklists (
  check_id TEXT PRIMARY KEY,
  check_type TEXT NOT NULL,
  check_name TEXT NOT NULL,
  category TEXT,
  severity TEXT,
  required_yn TEXT NOT NULL CHECK(required_yn IN ('Y','N')),
  check_description TEXT,
  purpose TEXT
);

CREATE TABLE IF NOT EXISTS production_apply_history (
  application_id TEXT PRIMARY KEY,
  change_id TEXT NOT NULL,
  review_id TEXT,
  version_code TEXT NOT NULL,
  approved_review_revision INTEGER,
  before_bom_revision INTEGER,
  after_bom_revision INTEGER,
  apply_result TEXT NOT NULL CHECK(apply_result IN ('STARTED','SUCCEEDED','FAILED')),
  failure_code TEXT,
  failure_message TEXT,
  applied_by TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  FOREIGN KEY(change_id) REFERENCES design_changes(change_id),
  FOREIGN KEY(review_id) REFERENCES review_boms(review_id),
  FOREIGN KEY(version_code) REFERENCES version_master(version_code)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_apply_success_change
  ON production_apply_history(change_id) WHERE apply_result = 'SUCCEEDED';

CREATE TABLE IF NOT EXISTS workflow_events (
  event_id TEXT PRIMARY KEY,
  change_id TEXT,
  review_id TEXT,
  event_type TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  actor_type TEXT NOT NULL CHECK(actor_type IN ('AGENT','USER','SYSTEM')),
  actor_id TEXT,
  reason TEXT,
  correlation_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(change_id) REFERENCES design_changes(change_id),
  FOREIGN KEY(review_id) REFERENCES review_boms(review_id)
);

CREATE TABLE IF NOT EXISTS legacy_change_history (
  legacy_history_id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_change_id TEXT NOT NULL,
  change_date TEXT,
  version_code TEXT,
  change_type TEXT,
  old_item_code TEXT,
  new_item_code TEXT,
  reason TEXT,
  approval_status TEXT,
  analysis_result TEXT,
  migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
  ON bom_master(parent_item_code, status, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_bom_child_dates
  ON bom_master(child_item_code, status, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS ix_bom_parent_sequence
  ON bom_master(parent_item_code, sequence_no);
CREATE INDEX IF NOT EXISTS ix_change_version_status
  ON design_changes(version_code, workflow_status);
CREATE INDEX IF NOT EXISTS ix_review_change
  ON review_boms(change_id);
CREATE INDEX IF NOT EXISTS ix_event_change_time
  ON workflow_events(change_id, created_at);

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

CREATE TRIGGER IF NOT EXISTS trg_material_item_type_insert
BEFORE INSERT ON material_master
FOR EACH ROW
WHEN COALESCE((SELECT item_type FROM item_master WHERE item_code = NEW.material_code), '') <> 'MATERIAL'
BEGIN
  SELECT RAISE(ABORT, 'material_master requires MATERIAL item');
END;
