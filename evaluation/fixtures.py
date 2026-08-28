from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sqlite3
from typing import Any


REQUIRED_FIXTURES = frozenset({
    "MODEL_A",
    "MODEL_B",
    "PLANT_A",
    "PLANT_B",
    "MATERIAL_A",
    "MATERIAL_B",
    "MATERIAL_C",
    "MATERIAL_NAME_A",
    "MATERIAL_NAME_B",
    "MATERIAL_FAMILY_A",
    "ASSY_A",
    "ASSY_NAME_A",
    "INVALID_MODEL",
    "INVALID_ITEM",
})


@dataclass(frozen=True)
class ResolvedFixtures:
    """Dynamic evaluation fixtures resolved from the current BOM database."""

    values: dict[str, str]
    evidence: dict[str, Any]

    def validate(self) -> None:
        missing = REQUIRED_FIXTURES - set(self.values)
        blank = sorted(key for key, value in self.values.items() if not str(value).strip())
        if missing:
            raise ValueError(f"Missing resolved fixtures: {sorted(missing)}")
        if blank:
            raise ValueError(f"Blank resolved fixtures: {blank}")


class EvaluationFixtureResolver:
    """Resolve evaluation data from SQLite instead of hard-coding sample IDs.

    The resolver deliberately chooses a coherent MODEL/PLANT/BOM scope, then
    derives material/assembly fixtures from the active BOM graph.  This keeps
    the evaluation dataset stable even when the concrete sample codes change.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        as_of_date: str | date | None = None,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.as_of_date = (
            as_of_date.isoformat()
            if isinstance(as_of_date, date)
            else str(as_of_date or date.today().isoformat())
        )

    def resolve(self) -> ResolvedFixtures:
        if not self.database_path.exists():
            raise FileNotFoundError(f"Evaluation database not found: {self.database_path}")

        with sqlite3.connect(self.database_path) as con:
            con.row_factory = sqlite3.Row
            items = {
                str(row["item_code"]).upper(): dict(row)
                for row in con.execute(
                    """
                    SELECT item_code,item_type,item_name,description,active_yn
                    FROM item_master
                    WHERE active_yn='Y'
                    """
                )
            }
            plant_rows = {
                str(row["plant_code"]).upper(): dict(row)
                for row in con.execute(
                    """
                    SELECT plant_code,plant_name,country_code,active_yn
                    FROM plants
                    WHERE active_yn='Y'
                    """
                )
            }
            edges = [
                dict(row)
                for row in con.execute(
                    """
                    SELECT plant_code,parent_item_code,child_item_code,location_code,quantity
                    FROM bom_master
                    WHERE status='ACTIVE'
                      AND valid_from<=?
                      AND (valid_to IS NULL OR valid_to>=?)
                    """,
                    (self.as_of_date, self.as_of_date),
                )
            ]

        if not items or not plant_rows or not edges:
            raise RuntimeError("Evaluation fixture resolution requires active master/BOM data.")

        adjacency: dict[str, dict[str, list[str]]] = {}
        direct_edges: dict[tuple[str, str], list[str]] = {}
        for row in edges:
            plant = str(row["plant_code"]).upper()
            parent = str(row["parent_item_code"]).upper()
            child = str(row["child_item_code"]).upper()
            adjacency.setdefault(plant, {}).setdefault(parent, []).append(child)
            direct_edges.setdefault((plant, parent), []).append(child)

        model_pairs: list[tuple[str, str, set[str]]] = []
        for plant_code, parent_map in adjacency.items():
            for parent_code in parent_map:
                item = items.get(parent_code) or {}
                if str(item.get("item_type") or "").upper() != "VERSION":
                    continue
                descendants = self._descendants(parent_map, parent_code)
                material_count = sum(
                    str((items.get(code) or {}).get("item_type") or "").upper() == "MATERIAL"
                    for code in descendants
                )
                assy_count = sum(
                    str((items.get(code) or {}).get("item_type") or "").upper() == "ASSEMBLY"
                    for code in descendants
                )
                if material_count >= 2 and assy_count >= 1:
                    model_pairs.append((plant_code, parent_code, descendants))

        if not model_pairs:
            raise RuntimeError("No active MODEL/PLANT BOM is rich enough for evaluation fixtures.")

        model_pairs.sort(
            key=lambda value: (
                self._richness(value[2], items),
                value[0],
                value[1],
            ),
            reverse=True,
        )
        plant_a, model_a, descendants_a = model_pairs[0]

        material_codes_a = sorted(
            code for code in descendants_a
            if str((items.get(code) or {}).get("item_type") or "").upper() == "MATERIAL"
        )
        assy_codes_a = sorted(
            code for code in descendants_a
            if str((items.get(code) or {}).get("item_type") or "").upper() == "ASSEMBLY"
        )
        if len(material_codes_a) < 2 or not assy_codes_a:
            raise RuntimeError("Selected evaluation MODEL does not contain required BOM content.")

        material_groups: dict[str, list[str]] = {}
        for code, item in items.items():
            if str(item.get("item_type") or "").upper() != "MATERIAL":
                continue
            name = str(item.get("item_name") or "").strip().upper()
            if name:
                material_groups.setdefault(name, []).append(code)

        family_options: list[tuple[int, str, str, str]] = []
        set_a = set(material_codes_a)
        model_a_family_counts: dict[str, int] = {}
        for code in material_codes_a:
            family = str(items[code].get("item_name") or "").strip().upper()
            model_a_family_counts[family] = model_a_family_counts.get(family, 0) + 1

        for code in material_codes_a:
            family = str(items[code].get("item_name") or "").strip().upper()
            group = sorted(material_groups.get(family, []))
            outside = [candidate for candidate in group if candidate not in set_a]
            # Name-based follow-up cases require an unambiguous current BOM row.
            if outside and model_a_family_counts.get(family) == 1:
                family_options.append((len(group), family, code, outside[0]))
        if not family_options:
            raise RuntimeError(
                "No material family has both an in-BOM item and an out-of-BOM ADD candidate."
            )
        family_options.sort(reverse=True)
        _, material_family_a, material_a, material_c = family_options[0]
        material_name_a = str(items[material_a].get("item_name") or material_family_a).strip()

        # Select a second MODEL, preferring a different Plant and overlapping
        # material names so follow-up/name-based cases stay business-valid.
        names_a = {
            str(items[code].get("item_name") or "").strip().upper()
            for code in material_codes_a
        }
        model_b_options: list[tuple[int, int, int, str, str, set[str]]] = []
        for plant, model, descendants in model_pairs[1:]:
            mats = [
                code for code in descendants
                if str((items.get(code) or {}).get("item_type") or "").upper() == "MATERIAL"
            ]
            names = {
                str(items[code].get("item_name") or "").strip().upper()
                for code in mats
            }
            overlap = len(names_a & names)
            different_plant = int(plant != plant_a)
            model_b_options.append(
                (different_plant, overlap, self._richness(descendants, items), plant, model, descendants)
            )
        if not model_b_options:
            plant_b, model_b, descendants_b = plant_a, model_a, descendants_a
        else:
            model_b_options.sort(reverse=True)
            _, _, _, plant_b, model_b, descendants_b = model_b_options[0]

        names_b = {
            str(items[code].get("item_name") or "").strip().upper()
            for code in descendants_b
            if str((items.get(code) or {}).get("item_type") or "").upper() == "MATERIAL"
        }

        # Prefer a material name that exists in MODEL_A and MODEL_B and is used
        # by multiple MODELs in PLANT_A. This makes Where-used/common-impact
        # evaluation meaningful without using a fixed sample code.
        model_descendants_a_plant = [
            descendants for plant, _, descendants in model_pairs if plant == plant_a
        ]
        material_b_options: list[tuple[int, int, str]] = []
        for code in material_codes_a:
            if code == material_a:
                continue
            name = str(items[code].get("item_name") or "").strip().upper()
            if model_a_family_counts.get(name) != 1:
                continue
            usage_count = sum(code in descendants for descendants in model_descendants_a_plant)
            cross_model_name = int(name in names_b)
            material_b_options.append((cross_model_name, usage_count, code))
        if not material_b_options:
            material_b = material_codes_a[1]
        else:
            material_b_options.sort(reverse=True)
            material_b = material_b_options[0][2]
        material_name_b = str(items[material_b].get("item_name") or "").strip()

        assy_a, assy_name_a = self._resolve_assy_add_fixture(
            plant_code=plant_a,
            assy_codes=assy_codes_a,
            items=items,
            direct_edges=direct_edges,
        )

        invalid_model = self._unused_code("EVALMODEL-999", items)
        invalid_item = self._unused_code("9999-999999", items)

        values = {
            "MODEL_A": model_a,
            "MODEL_B": model_b,
            "PLANT_A": plant_a,
            "PLANT_B": plant_b,
            "MATERIAL_A": material_a,
            "MATERIAL_B": material_b,
            "MATERIAL_C": material_c,
            "MATERIAL_NAME_A": material_name_a,
            "MATERIAL_NAME_B": material_name_b,
            "MATERIAL_FAMILY_A": material_family_a,
            "ASSY_A": assy_a,
            "ASSY_NAME_A": assy_name_a,
            "INVALID_MODEL": invalid_model,
            "INVALID_ITEM": invalid_item,
        }
        evidence = {
            "database": str(self.database_path),
            "as_of_date": self.as_of_date,
            "model_a_descendant_count": len(descendants_a),
            "model_b_descendant_count": len(descendants_b),
            "material_family_candidate_count": len(material_groups.get(material_family_a, [])),
            "material_c_not_in_model_a": material_c not in descendants_a,
            "plant_a_name": (plant_rows.get(plant_a) or {}).get("plant_name"),
            "plant_b_name": (plant_rows.get(plant_b) or {}).get("plant_name"),
        }
        result = ResolvedFixtures(values=values, evidence=evidence)
        result.validate()
        return result

    @staticmethod
    def _descendants(parent_map: dict[str, list[str]], root: str) -> set[str]:
        discovered: set[str] = set()
        stack = list(parent_map.get(root, []))
        while stack:
            code = stack.pop()
            if code in discovered:
                continue
            discovered.add(code)
            stack.extend(parent_map.get(code, []))
        return discovered

    @staticmethod
    def _richness(descendants: set[str], items: dict[str, dict[str, Any]]) -> int:
        material_count = sum(
            str((items.get(code) or {}).get("item_type") or "").upper() == "MATERIAL"
            for code in descendants
        )
        assy_count = sum(
            str((items.get(code) or {}).get("item_type") or "").upper() == "ASSEMBLY"
            for code in descendants
        )
        return material_count * 10 + assy_count

    @staticmethod
    def _resolve_assy_add_fixture(
        *,
        plant_code: str,
        assy_codes: list[str],
        items: dict[str, dict[str, Any]],
        direct_edges: dict[tuple[str, str], list[str]],
    ) -> tuple[str, str]:
        global_assy_names = sorted({
            str(item.get("item_name") or "").strip().upper()
            for item in items.values()
            if str(item.get("item_type") or "").upper() == "ASSEMBLY"
            and str(item.get("item_name") or "").strip()
        })
        for parent in assy_codes:
            child_names = {
                str((items.get(child) or {}).get("item_name") or "").strip().upper()
                for child in direct_edges.get((plant_code, parent), [])
                if str((items.get(child) or {}).get("item_type") or "").upper() == "ASSEMBLY"
            }
            parent_name = str((items.get(parent) or {}).get("item_name") or "").strip().upper()
            for target_name in global_assy_names:
                if target_name != parent_name and target_name not in child_names:
                    return parent, target_name
        raise RuntimeError("Could not resolve a safe ASSY ADD parent/name fixture.")

    @staticmethod
    def _unused_code(seed: str, items: dict[str, dict[str, Any]]) -> str:
        candidate = seed.upper()
        if candidate not in items:
            return candidate
        index = 1
        while True:
            candidate = f"{seed.upper()}-{index}"
            if candidate not in items:
                return candidate
            index += 1
