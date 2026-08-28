from agents.bom_graph_gateway import (
    AGENT_PATH,
    FAST_BOM_READ,
    FAST_CHAT,
    FAST_CURRENT_BOM_QUANTITY,
    FAST_WHERE_USED,
    BomGraphGateway,
)


ACTIVE_CONTEXT = {
    "product_id": "LTA400HR01-001",
    "plant_code": "P01",
    "source": "get_bom",
}


def test_gateway_symbols_are_restored():
    assert FAST_CHAT == "fast_chat"
    assert FAST_BOM_READ == "fast_bom_read"
    assert FAST_WHERE_USED == "fast_where_used"
    assert FAST_CURRENT_BOM_QUANTITY == "fast_current_bom_quantity"
    assert AGENT_PATH == "agent"


def test_current_bom_quantity_fast_path_context_inheritance_is_preserved():
    gateway = BomGraphGateway()

    assert gateway.can_inherit_active_bom_context(
        "실런트 수량은 몇이야?",
        ACTIVE_CONTEXT,
    ) is True






def test_explicit_model_and_plant_is_not_active_context_inheritance():
    gateway = BomGraphGateway()

    assert gateway.can_inherit_active_bom_context(
        "LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어",
        ACTIVE_CONTEXT,
    ) is False
