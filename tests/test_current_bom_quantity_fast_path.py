import json

from langchain_core.messages import HumanMessage, ToolMessage

from agents.bom_fast_path_nodes import (
    BomFastPathNodes,
    FAST_CURRENT_BOM_QUANTITY_CALL_PREFIX,
)
from agents.bom_graph_gateway import (
    BomGraphGateway,
    FAST_CURRENT_BOM_QUANTITY,
)
from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


class _Normalizer:
    def match_score(self, query, *values):
        normalized = str(query).strip().lower()
        haystack = " ".join(str(value) for value in values).upper()
        if normalized in {"실런트", "실란트", "sealant"} and "SEALANT" in haystack:
            return 1000
        return 0


def _active_context():
    return {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }


def test_router_classifies_quantity_question_as_read_only_context_fact():
    decision = DEFAULT_DOMAIN_INTENT_ROUTER.route(
        "실런트 자재수량은 몇이야?"
    )

    assert decision.intent == "CURRENT_BOM_QUANTITY"
    assert decision.change is False
    assert decision.quantity_change is False
    assert decision.current_bom_subject == "실런트"


def test_gateway_allows_context_quantity_fast_path_during_active_analysis():
    gateway = BomGraphGateway(
        design_change_active_steps={"ANALYSIS_READY"},
    )

    route = gateway.route({
        "messages": [HumanMessage(content="실런트 자재수량은 몇이야?")],
        "design_change": {
            "current_step": "ANALYSIS_READY",
            "analysis_id": "ANA-1",
            "candidates": [],
        },
        "active_bom_context": _active_context(),
    })

    assert route == FAST_CURRENT_BOM_QUANTITY


def test_current_bom_quantity_node_uses_active_bom_scope():
    nodes = BomFastPathNodes(query_normalizer=_Normalizer())
    result = nodes.current_bom_quantity({
        "messages": [HumanMessage(content="실런트 자재수량은 몇이야?")],
        "active_bom_context": _active_context(),
    })

    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "get_bom"
    assert call["args"] == {
        "plant_code": "P01",
        "product_id": "LTA400HR01-001",
    }
    assert call["id"].startswith(FAST_CURRENT_BOM_QUANTITY_CALL_PREFIX)


def test_current_bom_quantity_finalizer_returns_only_requested_quantity():
    nodes = BomFastPathNodes(query_normalizer=_Normalizer())
    tool_message = ToolMessage(
        content=json.dumps([
            {
                "plant_code": "P01",
                "bom_parent": "LJ94-100004",
                "bom_child": "0001-200010",
                "bom_child_name": "SEALANT",
                "location": "ALL",
                "quantity": 1,
                "required_quantity": 1,
            },
            {
                "plant_code": "P01",
                "bom_parent": "LJ94-100006",
                "bom_child": "0001-200014",
                "bom_child_name": "GATE-IC",
                "location": "ALL",
                "quantity": 4,
                "required_quantity": 4,
            },
        ]),
        tool_call_id=f"{FAST_CURRENT_BOM_QUANTITY_CALL_PREFIX}test",
        name="get_bom",
    )

    result = nodes.finalize_read({
        "messages": [
            HumanMessage(content="실런트 자재수량은 몇이야?"),
            tool_message,
        ],
        "active_bom_context": _active_context(),
    })

    answer = result["messages"][0].content
    assert "SEALANT(0001-200010)" in answer
    assert "BOM 수량은 1" in answer
    assert "GATE-IC" not in answer


def test_quantity_change_is_not_misclassified_as_quantity_fact():
    decision = DEFAULT_DOMAIN_INTENT_ROUTER.route(
        "실런트 자재 수량을 2로 바꿔줘"
    )

    assert decision.intent == "DESIGN_CHANGE"
    assert decision.quantity_change is True
    assert decision.current_bom_quantity is False
