from agents.bom_graph_gateway import BomGraphGateway


def test_active_bom_quantity_change_bypasses_redundant_plant_gate():
    gateway = BomGraphGateway()
    context = {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }

    assert gateway.can_inherit_active_bom_context(
        "LJ94-100006 자재의 수량을 바꾸고싶어",
        context,
    ) is True


def test_read_only_request_does_not_inherit_active_bom_for_plant_gate():
    gateway = BomGraphGateway()
    context = {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }

    assert gateway.can_inherit_active_bom_context(
        "LJ94-100006 어디에 사용돼?",
        context,
    ) is False


def test_explicit_different_plant_does_not_inherit_active_bom():
    gateway = BomGraphGateway()
    context = {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }

    assert gateway.can_inherit_active_bom_context(
        "P02에서 LJ94-100006 수량 바꾸고싶어",
        context,
    ) is False


def test_explicit_different_model_does_not_inherit_active_bom():
    gateway = BomGraphGateway()
    context = {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }

    assert gateway.can_inherit_active_bom_context(
        "LTA750HR11-001 P01 모델에서 LJ94-100006 수량 바꾸고싶어",
        context,
    ) is False
