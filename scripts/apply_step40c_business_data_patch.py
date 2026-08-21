from __future__ import annotations

import argparse
from pathlib import Path

from database import SQLiteDatabase
from scripts.seed_phase3_business_sample import (
    AS_OF_DATE,
    SCENARIOS,
    _candidate_code,
    _candidate_name,
    _rule_evaluation_item,
    _upsert_material,
)


def patch(database: SQLiteDatabase) -> dict:
    """Correct only ADD business-sample metadata without rebuilding workflow history.

    This is a sample-data maintenance patch, not runtime branching.  It is safe for
    an existing Phase3 DB because it does not delete requests, approvals, previews,
    apply history, or candidate evidence already persisted for completed requests.
    """
    updated_candidates = 0
    cleaned_source_attributes = 0
    updated_rules = 0

    with database.transaction() as connection:
        for scenario in SCENARIOS:
            if scenario.get("primary_action") != "ADD":
                continue

            # The ADD conditions describe the new item family, not the existing BOM
            # anchor material. Remove only sample-seeded technical attributes that
            # were incorrectly copied to that anchor in older seeds.
            technical_names = [name for name in scenario.get("attributes", {}) if name != "lifecycle_status"]
            if technical_names:
                placeholders = ",".join("?" for _ in technical_names)
                cursor = connection.execute(
                    f"""DELETE FROM item_attribute_values
                        WHERE item_code=? AND source='PHASE3_BUSINESS_SAMPLE'
                          AND attribute_name IN ({placeholders})""",
                    [scenario["source"], *technical_names],
                )
                cleaned_source_attributes += max(0, int(cursor.rowcount or 0))

            # Refresh candidate names/descriptions so the UI reflects the family
            # being requested (e.g. EMI SHIELD TAPE), not the anchor material.
            if scenario.get("target_type") == "MATERIAL":
                for candidate_no in range(1, 6):
                    code = _candidate_code(scenario, candidate_no)
                    exists = connection.execute(
                        "SELECT 1 FROM item_master WHERE item_code=?", (code,)
                    ).fetchone()
                    if not exists:
                        continue
                    _upsert_material(
                        connection,
                        code,
                        _candidate_name(scenario, candidate_no),
                        scenario["material_group"],
                    )
                    updated_candidates += 1

            # Older seeds used the existing source name as the rule evaluation
            # item. Restore the intended ADD family label for rule scoping.
            rule_id = f"DC-R-{scenario['no']:03d}"
            cursor = connection.execute(
                """UPDATE rule_revisions SET evaluation_item=?
                   WHERE rule_id=? AND revision_no=1""",
                (_rule_evaluation_item(scenario), rule_id),
            )
            updated_rules += max(0, int(cursor.rowcount or 0))

    return {
        "updated_candidates": updated_candidates,
        "cleaned_source_attributes": cleaned_source_attributes,
        "updated_rules": updated_rules,
        "as_of_date": AS_OF_DATE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply STEP40-C Phase3 business-sample metadata corrections")
    parser.add_argument("--database", default="data/display_bom.db")
    args = parser.parse_args()
    result = patch(SQLiteDatabase(Path(args.database)))
    print("STEP40-C business sample patch applied")
    for key, value in result.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
