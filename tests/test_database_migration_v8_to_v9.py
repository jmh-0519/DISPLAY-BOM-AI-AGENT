from __future__ import annotations

import json
import sqlite3

from database.migrations.v8_to_v9 import migrate_connection_v8_to_v9


def _v8_database(tmp_path):
    path = tmp_path / "v8.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE schema_versions(
          version INTEGER PRIMARY KEY,
          description TEXT NOT NULL,
          applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO schema_versions(version,description) VALUES(8,'v8');

        CREATE TABLE item_master(
          item_code TEXT PRIMARY KEY,
          item_type TEXT NOT NULL,
          item_name TEXT NOT NULL,
          description TEXT,
          active_yn TEXT NOT NULL DEFAULT 'Y',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE supplier_master(
          supplier_code TEXT PRIMARY KEY,
          supplier_name TEXT NOT NULL
        );
        CREATE TABLE version_master(
          version_code TEXT PRIMARY KEY,
          version_no TEXT,
          route_code TEXT,
          specification TEXT,
          active_yn TEXT NOT NULL DEFAULT 'Y',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(version_code) REFERENCES item_master(item_code)
        );
        CREATE TABLE assembly_master(
          assembly_code TEXT PRIMARY KEY,
          process_name TEXT NOT NULL,
          usage_type TEXT NOT NULL DEFAULT 'DEDICATED',
          specification TEXT,
          active_yn TEXT NOT NULL DEFAULT 'Y',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(assembly_code) REFERENCES item_master(item_code)
        );
        CREATE TABLE material_master(
          material_code TEXT PRIMARY KEY,
          material_name TEXT NOT NULL,
          material_group TEXT,
          unit TEXT,
          supplier_code TEXT,
          specification TEXT,
          active_yn TEXT NOT NULL DEFAULT 'Y',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(material_code) REFERENCES item_master(item_code),
          FOREIGN KEY(supplier_code) REFERENCES supplier_master(supplier_code)
        );
        """
    )
    con.execute(
        "INSERT INTO item_master(item_code,item_type,item_name,description) "
        "VALUES('V1','VERSION','FA','40IN/FHD/60HZ')"
    )
    con.execute(
        "INSERT INTO item_master(item_code,item_type,item_name,description) "
        "VALUES('A1','ASSEMBLY','OLB','OLB/40IN/FHD')"
    )
    con.execute(
        "INSERT INTO item_master(item_code,item_type,item_name,description) "
        "VALUES('M1','MATERIAL','DRIVE-IC','OLB/DRIVER_IC')"
    )
    con.execute(
        "INSERT INTO supplier_master VALUES('SUP-OLD','Legacy Supplier')"
    )
    con.execute(
        "INSERT INTO version_master(version_code,version_no,specification) VALUES(?,?,?)",
        (
            "V1",
            "01",
            json.dumps(
                {
                    "legacy_product_id": "LEGACY-V1",
                    "product_name": "40IN FHD LCD MODEL",
                    "product_type": "LCD MODULE",
                    "screen_size_inch": "40",
                    "resolution": "FHD",
                    "refresh_hz": "60",
                    "market": "KR",
                    "material_specification": "40IN/FHD/60HZ",
                }
            ),
        ),
    )
    con.execute(
        "INSERT INTO assembly_master(assembly_code,process_name,specification) "
        "VALUES('A1','OLB','OLB/40IN/FHD')"
    )
    con.execute(
        "INSERT INTO material_master("
        "material_code,material_name,material_group,unit,supplier_code,specification"
        ") VALUES('M1','DRIVE-IC','OLB','EA','SUP-OLD','OLB/DRIVER_IC')"
    )
    con.commit()
    return con


def test_v8_to_v9_normalizes_subtype_authority(tmp_path):
    con = _v8_database(tmp_path)
    result = migrate_connection_v8_to_v9(con)

    assert result["target_version"] == 9
    assert con.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0] == 9

    version = con.execute("SELECT * FROM version_master").fetchone()
    assert version["legacy_product_id"] == "LEGACY-V1"
    assert version["screen_size_inch"] == 40.0
    assert version["refresh_hz"] == 60.0
    assert version["resolution"] == "FHD"

    material_columns = {
        row[1] for row in con.execute("PRAGMA table_info(material_master)")
    }
    assert "supplier_code" not in material_columns
    assert "active_yn" not in material_columns
    assert "created_at" not in material_columns
    assert "updated_at" not in material_columns

    assembly_columns = {
        row[1] for row in con.execute("PRAGMA table_info(assembly_master)")
    }
    assert "active_yn" not in assembly_columns

    version_columns = {
        row[1] for row in con.execute("PRAGMA table_info(version_master)")
    }
    assert "route_code" not in version_columns
    assert "specification" not in version_columns
    assert "active_yn" not in version_columns

    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
