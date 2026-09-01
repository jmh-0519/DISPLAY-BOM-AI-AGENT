from rag.query_router import KnowledgeQueryRouter


def test_routes_high_confidence_knowledge_questions():
    router = KnowledgeQueryRouter()
    assert router.route("단종 자재 교체 기준이 뭐야?").eligible is True
    assert router.route("재고 관련 설계변경 정책 알려줘").eligible is True
    assert router.route("단종 자재 교체 기준 설명해줘").eligible is True
    decision = router.route("자재 사양 문서에서 DRIVE-IC 요구사항 알려줘")
    assert decision.eligible is True
    assert decision.document_type == "MATERIAL_SPEC"


def test_rejects_action_and_structured_bom_requests():
    router = KnowledgeQueryRouter()
    assert router.route("단종으로 LJ94-100001을 교체해줘").eligible is False
    assert router.route("LTA400HR01-001 P01 BOM 보여줘").eligible is False
    assert router.route("현재 SEALANT 수량이 몇이야?").eligible is False
