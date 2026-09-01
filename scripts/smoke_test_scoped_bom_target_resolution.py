from __future__ import annotations

from datetime import date

from core.database_config import sqlite_database_path
from database import SQLiteDatabase
from services.design_change_workflow_service import DesignChangeWorkflowService


def main() -> None:
    service = DesignChangeWorkflowService(SQLiteDatabase(sqlite_database_path()))
    request = {
        "version_code": "LTA400HR01-001",
        "plant_code": "P01",
        "as_of_date": date.today().isoformat(),
    }
    relations = service.repository.list_version_component_relations(**request)
    if not relations:
        raise RuntimeError("Scoped BOM smoke fixture is unavailable.")

    checked = []
    for target_name in ("DRIVE-IC", "GATE-IC"):
        exact_codes = {
            str(row.get("child_item_code") or "").strip().upper()
            for row in relations
            if str(row.get("item_name") or "").strip().upper() == target_name
        }
        exact_codes.discard("")
        if len(exact_codes) != 1:
            raise RuntimeError(
                f"Expected one scoped {target_name} item in smoke fixture, got {sorted(exact_codes)}"
            )
        resolved = service._resolve_source_item_code_by_name(
            request=request,
            target_item_name=target_name,
        )
        expected = next(iter(exact_codes))
        if resolved != expected:
            raise RuntimeError(
                f"Scoped target mismatch for {target_name}: expected={expected}, resolved={resolved}"
            )
        checked.append((target_name, resolved))

    print("Scoped BOM target resolution smoke test passed")
    for target_name, code in checked:
        print(f"- {target_name}: {code}")


if __name__ == "__main__":
    main()
