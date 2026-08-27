import json

from langchain_core.messages import HumanMessage, ToolMessage

from agents.llm_context_compactor import LlmContextCompactor


def _rows():
    rows = []
    for i in range(120):
        rows.append({
            "plant_code": "P01",
            "bom_parent": "LJ94-100004",
            "bom_child": f"0001-{200000+i:06d}",
            "bom_child_name": f"PART-{i}",
            "description": "GENERAL",
            "quantity": 1,
        })
    rows[77].update({
        "bom_child": "0001-200010",
        "bom_child_name": "SEALANT",
        "description": "LC SEALANT",
    })
    return rows


def test_mixed_english_korean_particle_keeps_canonical_material_term():
    terms = LlmContextCompactor._query_match_terms(
        "LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"
    )

    assert "SEALANT" in terms
    assert "SEALANT를" not in terms


def test_large_bom_selects_sealant_row_when_korean_particle_is_attached():
    query = "LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"
    compacted, _ = LlmContextCompactor().compact(
        [
            HumanMessage(content=query),
            ToolMessage(
                content=json.dumps(_rows()),
                tool_call_id="bom-call",
                name="get_bom",
            ),
        ],
        current_user_query=query,
    )
    payload = json.loads(compacted[-1].content)

    assert payload["selection"] == "query_matching_rows"
    assert any(
        row.get("bom_child") == "0001-200010"
        for row in payload["rows"]
    )


def test_explicit_item_code_still_selects_target_row():
    query = "LTA400HR01-001에서 0001-200010 자재를 변경하고싶어"
    compacted, _ = LlmContextCompactor().compact(
        [
            HumanMessage(content=query),
            ToolMessage(
                content=json.dumps(_rows()),
                tool_call_id="bom-call",
                name="get_bom",
            ),
        ],
        current_user_query=query,
    )
    payload = json.loads(compacted[-1].content)

    assert payload["selection"] == "query_matching_rows"
    assert any(
        row.get("bom_child") == "0001-200010"
        for row in payload["rows"]
    )
