from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any

from agents.analysis_macro_dispatch import (
    MACRO_ANALYZE,
    DeterministicAnalysisMacroDispatch,
)
from agents.bom_graph_gateway import BomGraphGateway
from database import SQLiteDatabase
from mcp_client.client import DisplayBomMcpClient
from repositories.design_change_repository import SQLiteDesignChangeRepository
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class AcceptanceResult:
    scenario: str
    passed: bool
    detail: str


def _count(database: SQLiteDatabase, table: str) -> int:
    with database.connection() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS c FROM {table}"
        ).fetchone()
    return int(row["c"])


def _production_bom_fingerprint(database: SQLiteDatabase) -> str:
    """Stable fingerprint of active Production BOM rows."""
    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT
                plant_code,
                parent_item_code,
                child_item_code,
                location_code,
                quantity,
                valid_from,
                valid_to,
                status
            FROM bom_master
            ORDER BY
                plant_code,
                parent_item_code,
                child_item_code,
                COALESCE(location_code, ''),
                valid_from,
                COALESCE(valid_to, ''),
                status
            """
        ).fetchall()

    payload = [
        {
            key: row[key]
            for key in row.keys()
        }
        for row in rows
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dynamic_replace_context(database: SQLiteDatabase) -> dict[str, Any]:
    """Discover one valid REPLACE context from current DB metadata."""
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()

    with database.connection() as connection:
        sources = connection.execute(
            """
            SELECT DISTINCT
                r.source_item_code,
                i.item_name,
                i.item_type
            FROM substitution_relations r
            JOIN item_master i
              ON i.item_code=r.source_item_code
            WHERE r.active_yn='Y'
              AND i.active_yn='Y'
              AND r.valid_from<=?
              AND (r.valid_to IS NULL OR r.valid_to>=?)
            ORDER BY r.source_item_code
            """,
            (today, today),
        ).fetchall()

    for source in sources:
        with database.connection() as connection:
            plants = [
                row["plant_code"]
                for row in connection.execute(
                    """
                    SELECT DISTINCT plant_code
                    FROM bom_master
                    WHERE child_item_code=?
                      AND status='ACTIVE'
                      AND valid_from<=?
                      AND (valid_to IS NULL OR valid_to>=?)
                    ORDER BY plant_code
                    """,
                    (source["source_item_code"], today, today),
                ).fetchall()
            ]

        for plant_code in plants:
            ancestors = repository.get_recursive_ancestors(
                source["source_item_code"],
                plant_code,
                today,
            )
            for ancestor in ancestors:
                if ancestor["item_type"] != "VERSION":
                    continue

                relations = repository.find_version_source_relations(
                    version_code=ancestor["item_code"],
                    child_item_code=source["source_item_code"],
                    plant_code=plant_code,
                    as_of_date=today,
                )
                if len(relations) != 1:
                    continue

                relation = relations[0]
                return {
                    "today": today,
                    "version_code": ancestor["item_code"],
                    "plant_code": plant_code,
                    "source_item_code": source["source_item_code"],
                    "source_item_name": source["item_name"],
                    "source_item_type": source["item_type"],
                    "parent_item_code": relation["parent_item_code"],
                    "location_code": relation.get("location_code"),
                    "old_quantity": float(relation.get("quantity") or 1.0),
                }

    raise RuntimeError(
        "현재 DB에서 동적으로 검증 가능한 REPLACE Context를 찾지 못했습니다."
    )


def _dynamic_add_context(database: SQLiteDatabase) -> dict[str, Any]:
    """Discover a VERSION parent and one inactive edge target dynamically."""
    with database.connection() as connection:
        parent = connection.execute(
            """
            SELECT DISTINCT
                b.plant_code,
                b.parent_item_code AS version_code
            FROM bom_master b
            JOIN item_master p
              ON p.item_code=b.parent_item_code
            WHERE b.status='ACTIVE'
              AND p.item_type='VERSION'
              AND p.active_yn='Y'
            ORDER BY b.plant_code, b.parent_item_code
            LIMIT 1
            """
        ).fetchone()
        if parent is None:
            raise RuntimeError("ADD 검증용 활성 VERSION Parent가 없습니다.")

        target = connection.execute(
            """
            SELECT
                i.item_code,
                i.item_name,
                i.item_type
            FROM item_master i
            WHERE i.item_type='MATERIAL'
              AND i.active_yn='Y'
              AND NOT EXISTS (
                  SELECT 1
                  FROM bom_master b
                  WHERE b.plant_code=?
                    AND b.parent_item_code=?
                    AND b.child_item_code=i.item_code
                    AND b.status='ACTIVE'
              )
            ORDER BY i.item_code
            LIMIT 1
            """,
            (parent["plant_code"], parent["version_code"]),
        ).fetchone()
        if target is None:
            raise RuntimeError("ADD 검증용 MATERIAL Candidate가 없습니다.")

    return {
        "plant_code": parent["plant_code"],
        "version_code": parent["version_code"],
        "new_item_code": target["item_code"],
        "new_item_name": target["item_name"],
    }


def _selectable_candidate(analysis: dict[str, Any]) -> dict[str, Any]:
    for candidate in analysis.get("candidates") or []:
        if candidate.get("status") in {"PASS", "CONDITIONAL"}:
            return candidate
    raise RuntimeError("명시적 진행 경계 검증에 사용할 선택 가능 후보가 없습니다.")


def _run(target: Path) -> list[AcceptanceResult]:
    rebuild_latest_database(target)
    os.environ["BOM_SQLITE_PATH"] = str(target)
    os.environ["BOM_MCP_LOCAL_READ_FAST_PATH"] = "1"
    os.environ["BOM_MCP_LOCAL_ANALYSIS_FAST_PATH"] = "1"

    database = SQLiteDatabase(target)
    service = DesignChangeWorkflowService(database)
    mcp_client = DisplayBomMcpClient()
    dispatch = DeterministicAnalysisMacroDispatch()
    gateway = BomGraphGateway()

    context = _dynamic_replace_context(database)
    add_context = _dynamic_add_context(database)

    results: list[AcceptanceResult] = []
    before_bom = _production_bom_fingerprint(database)
    before_requests = _count(database, "change_requests")

    # 01. Forward BOM read.
    bom = mcp_client.call_tool(
        "get_bom",
        {
            "product_id": context["version_code"],
            "plant_code": context["plant_code"],
        },
    )
    results.append(AcceptanceResult(
        "01_FORWARD_BOM",
        isinstance(bom, list) and len(bom) > 0,
        f"{context['version_code']} / {context['plant_code']} rows={len(bom or [])}",
    ))

    # 02. Where-used read.
    where_used = mcp_client.call_tool(
        "get_bom_where_used",
        {
            "item_code": context["source_item_code"],
            "plant_code": context["plant_code"],
        },
    )
    top_models = (where_used or {}).get("top_models") or []
    results.append(AcceptanceResult(
        "02_WHERE_USED",
        isinstance(where_used, dict) and len(top_models) > 0,
        f"{context['source_item_code']} top_models={len(top_models)}",
    ))

    # 03. Active BOM Context inheritance + deterministic quantity Macro.
    active_context = {
        "product_id": context["version_code"],
        "plant_code": context["plant_code"],
        "source": "get_bom",
    }
    quantity_query = (
        f"{context['source_item_code']} 자재 수량을 "
        f"{context['old_quantity'] + 1:g}로 바꿔줘"
    )
    quantity_route = gateway.route({
        "messages": [],
        "user_query": quantity_query,
        "active_bom_context": active_context,
        "design_change": {"current_step": "NOT_STARTED"},
    })
    results.append(AcceptanceResult(
        "03_ACTIVE_BOM_CONTEXT",
        quantity_route == MACRO_ANALYZE,
        f"route={quantity_route}, inherited={context['version_code']}/{context['plant_code']}",
    ))

    # 04. REPLACE Macro Analysis.
    replace_query = (
        f"{context['version_code']} {context['plant_code']} 모델에서 "
        f"{context['source_item_code']} 자재를 변경하고싶어"
    )
    replace_spec = dispatch.build_spec(
        user_query=replace_query,
        workflow_state={"current_step": "NOT_STARTED"},
    )
    if replace_spec is None:
        raise RuntimeError("REPLACE Macro spec 생성 실패")
    replace_analysis = mcp_client.call_tool(
        "analyze_design_change_candidates",
        replace_spec,
    )
    results.append(AcceptanceResult(
        "04_REPLACE_ANALYSIS",
        (
            replace_analysis.get("workflow_status") == "ANALYSIS_READY"
            and replace_analysis.get("request_created") is False
            and len(replace_analysis.get("candidates") or []) > 0
        ),
        (
            f"analysis={replace_analysis.get('analysis_id')}, "
            f"candidates={len(replace_analysis.get('candidates') or [])}, "
            f"status={replace_analysis.get('analysis_status')}"
        ),
    ))

    # 05. ADD Analysis on a dynamically absent BOM edge.
    add_analysis = service.analyze_candidates(
        {
            "version_code": add_context["version_code"],
            "plant_code": add_context["plant_code"],
            "original_request": "사용자 요청으로 자재를 추가하고싶어",
        },
        [{
            "action_type": "ADD",
            "target_type": "MATERIAL",
            "new_item_code": add_context["new_item_code"],
        }],
    )
    results.append(AcceptanceResult(
        "05_ADD_ANALYSIS",
        (
            add_analysis.get("workflow_status") == "ANALYSIS_READY"
            and add_analysis.get("request_created") is False
            and len(add_analysis.get("actions") or []) == 1
        ),
        (
            f"{add_context['new_item_code']} "
            f"status={add_analysis.get('analysis_status')}"
        ),
    ))

    # 06. DELETE Analysis.
    delete_analysis = service.analyze_candidates(
        {
            "version_code": context["version_code"],
            "plant_code": context["plant_code"],
            "original_request": "사용자 요청으로 현재 자재를 삭제하고싶어",
        },
        [{
            "action_type": "DELETE",
            "old_item_code": context["source_item_code"],
        }],
    )
    delete_action = (delete_analysis.get("actions") or [{}])[0]
    results.append(AcceptanceResult(
        "06_DELETE_ANALYSIS",
        (
            delete_analysis.get("workflow_status") == "ANALYSIS_READY"
            and delete_analysis.get("request_created") is False
            and delete_action.get("action_type") == "DELETE"
        ),
        f"status={delete_action.get('evaluation_status')}",
    ))

    # 07. QUANTITY_CHANGE Analysis.
    quantity_analysis = service.analyze_candidates(
        {
            "version_code": context["version_code"],
            "plant_code": context["plant_code"],
            "original_request": "사용자 요청으로 BOM 수량을 변경하고싶어",
        },
        [{
            "action_type": "QUANTITY_CHANGE",
            "old_item_code": context["source_item_code"],
            "new_quantity": context["old_quantity"] + 1,
        }],
    )
    quantity_action = (quantity_analysis.get("actions") or [{}])[0]
    results.append(AcceptanceResult(
        "07_QUANTITY_ANALYSIS",
        (
            quantity_analysis.get("workflow_status") == "ANALYSIS_READY"
            and quantity_analysis.get("request_created") is False
            and quantity_action.get("action_type") == "QUANTITY_CHANGE"
        ),
        (
            f"{quantity_action.get('old_quantity')} -> "
            f"{quantity_action.get('new_quantity')}, "
            f"status={quantity_action.get('evaluation_status')}"
        ),
    ))

    # 08. Analysis boundary: no Request before explicit proceed.
    after_analysis_requests = _count(database, "change_requests")
    results.append(AcceptanceResult(
        "08_ANALYSIS_NO_REQUEST",
        after_analysis_requests == before_requests,
        f"change_requests {before_requests} -> {after_analysis_requests}",
    ))

    # 09. Analysis boundary: no Production BOM modification.
    after_analysis_bom = _production_bom_fingerprint(database)
    results.append(AcceptanceResult(
        "09_ANALYSIS_NO_PRODUCTION_CHANGE",
        after_analysis_bom == before_bom,
        f"bom_fingerprint_unchanged={after_analysis_bom == before_bom}",
    ))

    # 10. Explicit proceed is the first Request-creation point.
    candidate = _selectable_candidate(replace_analysis)
    selections = [{
        "action_id": candidate["action_id"],
        "candidate_item_code": candidate["candidate_item_code"],
        "supplier_item_id": candidate.get("recommended_supplier_item_id"),
    }]
    impact = service.preview_analysis_impact(
        replace_analysis,
        selections,
    )
    committed = service.commit_analysis_as_request(
        analysis=replace_analysis,
        selections=selections,
        approved_by="demo-acceptance",
        exception_reason=(
            "Acceptance Harness conditional candidate confirmation"
            if candidate.get("status") == "CONDITIONAL"
            else None
        ),
        impact_confirmed=bool(impact.get("requires_impact_approval")) or True,
    )
    after_commit_requests = _count(database, "change_requests")
    after_commit_bom = _production_bom_fingerprint(database)
    results.append(AcceptanceResult(
        "10_EXPLICIT_PROCEED_CREATES_REQUEST_ONLY",
        (
            committed.get("request_created") is True
            and bool(committed.get("request_id"))
            and after_commit_requests == before_requests + 1
            and after_commit_bom == before_bom
        ),
        (
            f"request_id={committed.get('request_id')}, "
            f"change_requests={after_commit_requests}, "
            f"production_bom_unchanged={after_commit_bom == before_bom}"
        ),
    ))

    return results


def _print(results: list[AcceptanceResult]) -> None:
    print("\n=== Design Change Demo Acceptance ===")
    print(f"{'RESULT':<7} {'SCENARIO':<42} DETAIL")
    print("-" * 100)
    for result in results:
        label = "PASS" if result.passed else "FAIL"
        print(f"{label:<7} {result.scenario:<42} {result.detail}")
    passed = sum(result.passed for result in results)
    print("-" * 100)
    print(f"TOTAL: {passed}/{len(results)} PASS")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run non-Production Design Change demo acceptance checks."
    )
    parser.add_argument(
        "--database",
        help=(
            "Acceptance용 임시 DB 경로. 생략하면 OS temp 아래에 생성하고 "
            "검증 후 자동 정리합니다."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="결과를 JSON으로도 출력합니다.",
    )
    args = parser.parse_args()

    if args.database:
        target = Path(args.database).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        results = _run(target)
    else:
        with tempfile.TemporaryDirectory(prefix="display-bom-demo-acceptance-") as temp:
            target = Path(temp) / "acceptance.db"
            results = _run(target)

    _print(results)
    if args.json:
        print(json.dumps(
            [asdict(result) for result in results],
            ensure_ascii=False,
            indent=2,
        ))

    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
