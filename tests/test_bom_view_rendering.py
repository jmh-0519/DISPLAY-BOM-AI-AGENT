from pathlib import Path


def test_assembly_child_highlights_entire_row():
    source = (
        Path(__file__).resolve().parents[1] / "app" / "views" / "bom_view.py"
    ).read_text(encoding="utf-8")
    assert '<tr{row_class}>' in source
    assert '.bom-assy-row td{color:#1677d2;font-weight:700}' in source
    assert 'index in {2, 3}' not in source
