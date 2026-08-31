from __future__ import annotations

import pytest

from database import SchemaManager, SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from repositories.sqlite_repository import SQLiteBomRepository
from services.change_reason_resolver import ChangeReasonResolver, ReasonResolutionError
from services.repository_bom_service import RepositoryBomService


def make_database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "plant-reason.db")
    SchemaManager(database).initialize()
    return database


def seed_relation(database: SQLiteDatabase) -> None:
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO item_master(item_code,item_type,item_name) VALUES('MODEL-1','VERSION','MODEL')"
        )
        connection.execute("INSERT INTO version_master(version_code) VALUES('MODEL-1')")
        connection.execute(
            "INSERT INTO item_master(item_code,item_type,item_name) VALUES('MAT-1','MATERIAL','MATERIAL')"
        )
        connection.execute(
            "INSERT INTO material_master(material_code,material_name) VALUES('MAT-1','MATERIAL')"
        )
        for plant_code, quantity in (("P01", 1), ("P02", 2)):
            connection.execute(
                """INSERT INTO bom_master(
                     plant_code,parent_item_code,child_item_code,location_code,
                     sequence_no,quantity,valid_from,status)
                   VALUES(?,'MODEL-1','MAT-1','N/A',1,?,'2026-01-01','ACTIVE')""",
                (plant_code, quantity),
            )


def test_plant_master_contains_the_four_confirmed_active_plants(tmp_path):
    database = make_database(tmp_path)
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT plant_code,plant_name,country_code,active_yn FROM plants ORDER BY plant_code"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("P01", "국내 AA PLANT", "KR", "Y"),
        ("P02", "국내 BB PLANT", "KR", "Y"),
        ("P03", "중국 CC PLANT", "CN", "Y"),
        ("P04", "베트남 DD PLANT", "VN", "Y"),
    ]


def test_same_bom_relation_is_independent_by_plant(tmp_path):
    database = make_database(tmp_path)
    seed_relation(database)
    service = RepositoryBomService(SQLiteBomRepository(database))

    p01 = service.get_bom("P01", "MODEL-1", "2026-08-18")
    p02 = service.get_bom("P02", "MODEL-1", "2026-08-18")

    assert p01[["plant_code", "quantity"]].to_dict("records") == [
        {"plant_code": "P01", "quantity": 1.0}
    ]
    assert p02[["plant_code", "quantity"]].to_dict("records") == [
        {"plant_code": "P02", "quantity": 2.0}
    ]


def test_reason_alias_is_resolved_and_persisted_as_action_primary_reason(tmp_path):
    database = make_database(tmp_path)
    seed_relation(database)
    repository = SQLiteDesignChangeRepository(database)
    resolved = ChangeReasonResolver(repository).resolve(
        proposed_reasons=["단종"],
        original_request="자재 단종으로 교체가 필요합니다",
        target_type="MATERIAL",
        action_type="REPLACE",
    )
    assert resolved.reason_code == "EOL"

    repository.create_request(
        {
            "request_id": "REQ-REASON-1",
            "plant_code": "P01",
            "version_code": "MODEL-1",
            "original_request": "자재 단종으로 교체가 필요합니다",
            "reasons": ["EOL"],
            "as_of_date": "2026-08-18",
            "effective_date": "2026-09-01",
            "requested_by": "tester",
        },
        [{
            "action_id": "ACT-REASON-1",
            "action_type": "REPLACE",
            "target_type": "MATERIAL",
            "parent_item_code": "MODEL-1",
            "old_item_code": "MAT-1",
            "location_code": "N/A",
        }],
        [resolved.as_record()],
    )
    request = repository.get_request("REQ-REASON-1")
    assert request["plant_code"] == "P01"
    assert request["actions"][0]["primary_reason"]["reason_code"] == "EOL"


def test_usage_type_is_not_a_design_change_reason_and_unknown_reason_stops(tmp_path):
    repository = SQLiteDesignChangeRepository(make_database(tmp_path))
    resolver = ChangeReasonResolver(repository)
    with pytest.raises(ReasonResolutionError, match="REASON_RESOLUTION_REQUIRED"):
        resolver.resolve(
            proposed_reasons=["COMMON_ASSY"],
            original_request="공용 ASSY입니다",
            target_type="ASSY",
            action_type="REPLACE",
        )

    reason_codes = {row["reason_code"] for row in repository.list_active_reason_metadata()}
    assert "COMMON_ASSY" not in reason_codes
    assert "COMMONIZATION" in reason_codes


def test_missing_reason_uses_registered_user_request_fallback(tmp_path):
    repository = SQLiteDesignChangeRepository(make_database(tmp_path))
    resolver = ChangeReasonResolver(repository)

    for target_type, action_type in (
        ("MATERIAL", "REPLACE"),
        ("MATERIAL", "ADD"),
        ("MATERIAL", "DELETE"),
        ("MATERIAL", "QUANTITY_CHANGE"),
        ("ASSY", "REPLACE"),
        ("ASSY", "ADD"),
        ("ASSY", "DELETE"),
        ("ASSY", "QUANTITY_CHANGE"),
    ):
        resolved = resolver.resolve(
            proposed_reasons=[],
            original_request="사용자가 변경을 요청했습니다.",
            target_type=target_type,
            action_type=action_type,
        )
        assert resolved.reason_code == "USER_REQUEST"
        assert resolved.resolution_source == "SYSTEM_DEFAULT"
        assert resolved.confidence == 1.0
