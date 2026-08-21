from database import SQLiteDatabase, SchemaManager
from repositories.design_change_repository import SQLiteDesignChangeRepository
from services.impact_analysis_service import ImpactAnalysisService


def setup_common_assy(tmp_path):
    db = SQLiteDatabase(tmp_path / "impact.db")
    SchemaManager(db).initialize()
    with db.transaction() as con:
        for code, kind in (
            ("FA-1", "VERSION"), ("FA-2", "VERSION"),
            ("COMMON", "ASSEMBLY"), ("NEW-ASSY", "ASSEMBLY"),
            ("OLD-MAT", "MATERIAL"), ("NEW-MAT", "MATERIAL"),
        ):
            item_name = "FA" if kind == "VERSION" else "OLB" if kind == "ASSEMBLY" else code
            con.execute(
                "INSERT INTO item_master(item_code,item_type,item_name) VALUES(?,?,?)",
                (code, kind, item_name),
            )
            if kind == "VERSION":
                con.execute("INSERT INTO version_master(version_code) VALUES(?)", (code,))
            elif kind == "ASSEMBLY":
                con.execute("INSERT INTO assembly_master(assembly_code,process_name,usage_type) VALUES(?, 'OLB', ?)", (code, "COMMON" if code == "COMMON" else "DEDICATED"))
            else:
                con.execute("INSERT INTO material_master(material_code,material_name) VALUES(?,?)", (code, code))
        con.executemany(
            """INSERT INTO bom_master(parent_item_code,child_item_code,location_code,
               sequence_no,quantity,valid_from,status) VALUES(?,?,'N/A',1,1,'2026-01-01','ACTIVE')""",
            [("FA-1", "COMMON"), ("FA-2", "COMMON"), ("COMMON", "OLD-MAT")],
        )
    return db


def insert_request(db, request_id, version, action):
    repository = SQLiteDesignChangeRepository(db)
    repository.create_request(
        {"request_id": request_id, "version_code": version, "reasons": ["COMMONIZATION"],
         "as_of_date": "2026-08-14", "effective_date": "2026-08-20",
         "demand_source": "USER", "demand_quantity": 1, "requested_by": "tester"},
        [action],
    )
    with db.transaction() as con:
        con.execute("UPDATE change_actions SET evaluation_status='PASS' WHERE request_id=?", (request_id,))
    return repository


def test_internal_common_assy_change_impacts_all_models(tmp_path):
    db = setup_common_assy(tmp_path)
    repo = insert_request(db, "REQ-1", "FA-1", {
        "action_id": "ACT-1", "action_type": "REPLACE", "target_type": "MATERIAL",
        "parent_item_code": "COMMON", "old_item_code": "OLD-MAT",
        "new_item_code": "NEW-MAT", "location_code": "N/A",
    })
    preview = ImpactAnalysisService(repo).create_preview("REQ-1", "tester")
    models = {row["impacted_item_code"] for row in preview["impacts"] if row["impact_type"] == "MODEL"}
    assert models == {"FA-1", "FA-2"}
    assert preview["validation_status"] == "PASS"


def test_model_assy_connection_replace_only_impacts_target_model(tmp_path):
    db = setup_common_assy(tmp_path)
    repo = insert_request(db, "REQ-2", "FA-1", {
        "action_id": "ACT-2", "action_type": "REPLACE", "target_type": "ASSY",
        "parent_item_code": "FA-1", "old_item_code": "COMMON",
        "new_item_code": "NEW-ASSY", "location_code": "N/A",
    })
    preview = ImpactAnalysisService(repo).create_preview("REQ-2", "tester")
    assert [(row["impacted_item_code"], row["impact_type"]) for row in preview["impacts"]] == [
        ("FA-1", "MODEL_CONNECTION"),
    ]
    with db.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM change_impacts WHERE request_id='REQ-2'").fetchone()[0] == 1
