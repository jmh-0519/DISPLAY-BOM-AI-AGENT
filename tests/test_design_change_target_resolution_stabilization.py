from agents.analysis_macro_dispatch import DeterministicAnalysisMacroDispatch
from agents.domain_intent_router import DomainIntentRouter


def test_named_target_strips_model_plant_scope_particle_and_reason_clause():
    router = DomainIntentRouter()
    query = "LTA400HR01-001 P01에서 DRIVE-IC 자재를 단종 때문에 교체해줘"
    assert router.extract_named_change_target(query) == "DRIVE-IC"


def test_target_correction_extracts_new_target():
    router = DomainIntentRouter()
    assert router.extract_target_correction(
        "아, drive-ic가 아니라 gate-ic 자재였어."
    ) == "gate-ic"


def test_macro_reuses_previous_scope_action_and_reason_on_target_correction():
    dispatch = DeterministicAnalysisMacroDispatch(DomainIntentRouter())
    previous = "LTA400HR01-001 P01에서 DRIVE-IC 자재를 단종 때문에 교체해줘"
    current = "아, drive-ic가 아니라 gate-ic 자재였어."
    spec = dispatch.build_spec(
        user_query=current,
        previous_user_query=previous,
        active_bom_context={"product_id": "LTA400HR01-001", "plant_code": "P01"},
        workflow_state={"current_step": "NOT_STARTED"},
    )
    assert spec is not None
    assert spec["request"]["version_code"] == "LTA400HR01-001"
    assert spec["request"]["plant_code"] == "P01"
    assert "단종" in spec["request"]["original_request"]
    assert spec["actions"] == [{"action_type": "REPLACE", "target_item_name": "gate-ic"}]
