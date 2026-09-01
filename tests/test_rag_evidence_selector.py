from rag.evidence_selector import KnowledgeEvidenceSelector


def _hit(rank, doc_id, doc_type, source):
    return {
        "rank": rank,
        "document_id": doc_id,
        "document_title": doc_id,
        "document_type": doc_type,
        "section_path": doc_id,
        "source_file": source,
        "content": doc_id,
    }


def test_criteria_preserves_semantic_reason_rule_order_and_hides_evaluation():
    hits = [
        _hit(1, "EVAL", "MATERIAL_SPEC", "knowledge/documents/evaluation/MS.md"),
        _hit(2, "EOL", "CHANGE_REASON", "knowledge/reasons/EOL.md"),
        _hit(
            3,
            "RULE:EOL",
            "CHANGE_RULE",
            "knowledge/rules/DC-R-001_EOL_DRIVE_IC.md",
        ),
        _hit(4, "SUP", "SUPPLIER_TECHNICAL", "knowledge/documents/runtime/SUP.md"),
        _hit(5, "OTHER_REASON", "CHANGE_REASON", "knowledge/reasons/OTHER.md"),
    ]
    selected = KnowledgeEvidenceSelector().select(
        "단종 자재 교체 기준이 뭐야?", hits, max_hits=3
    )
    assert [hit["document_id"] for hit in selected] == ["EOL", "RULE:EOL"]
    assert all("/evaluation/" not in hit["source_file"] for hit in selected)


def test_criteria_does_not_promote_lower_ranked_reason_over_rule():
    hits = [
        _hit(1, "EOL", "CHANGE_REASON", "knowledge/reasons/EOL.md"),
        _hit(
            2,
            "RULE:EOL",
            "CHANGE_RULE",
            "knowledge/rules/DC-R-001_EOL_DRIVE_IC.md",
        ),
        _hit(3, "SUPPLIER_STOP", "CHANGE_REASON", "knowledge/reasons/SUPPLIER_STOP.md"),
    ]
    selected = KnowledgeEvidenceSelector().select(
        "단종 자재 교체 기준이 뭐야?", hits, max_hits=2
    )
    assert [hit["document_id"] for hit in selected] == ["EOL", "RULE:EOL"]


def test_process_question_drops_unrelated_supplier_technical():
    hits = [
        _hit(1, "SUP", "SUPPLIER_TECHNICAL", "knowledge/documents/runtime/SUP.md"),
        _hit(2, "REASON", "CHANGE_REASON", "knowledge/reasons/CUSTOMER_SPEC.md"),
        _hit(3, "POLICY", "CHANGE_POLICY", "knowledge/documents/runtime/POLICY.md"),
        _hit(4, "PROCESS", "PROCESS_GUIDE", "knowledge/documents/runtime/PROCESS.md"),
        _hit(5, "FAQ", "FAQ", "knowledge/documents/runtime/FAQ.md"),
    ]
    selected = KnowledgeEvidenceSelector().select(
        "고객사양 변경 시 설계변경 절차가 뭐야?", hits, max_hits=3
    )
    assert [hit["document_id"] for hit in selected] == ["REASON", "POLICY", "PROCESS"]
    assert all(hit["document_type"] != "SUPPLIER_TECHNICAL" for hit in selected)

def test_eol_query_excludes_supplier_stop_and_inventory_reason():
    hits = [
        _hit(1, "REASON:EOL", "CHANGE_REASON", "knowledge/reasons/EOL.md"),
        _hit(2, "REASON:SUPPLIER_STOP", "CHANGE_REASON", "knowledge/reasons/SUPPLIER_STOP.md"),
        _hit(3, "RULE:EOL", "CHANGE_RULE", "knowledge/rules/DC-R-001_EOL_DRIVE_IC.md"),
        _hit(4, "REASON:INVENTORY", "CHANGE_REASON", "knowledge/reasons/INVENTORY.md"),
        _hit(
            5,
            "RULE:SUPPLIER_STOP",
            "CHANGE_RULE",
            "knowledge/rules/DC-R-002_SUPPLIER_STOP_OLB_FPCB.md",
        ),
    ]
    selected = KnowledgeEvidenceSelector().select(
        "단종기준이 뭐야?", hits, max_hits=3
    )
    assert [hit["document_id"] for hit in selected] == ["REASON:EOL", "RULE:EOL"]


def test_customer_spec_query_excludes_other_reason_families():
    hits = [
        _hit(1, "REASON:CUSTOMER_SPEC", "CHANGE_REASON", "knowledge/reasons/CUSTOMER_SPEC.md"),
        _hit(2, "REASON:USER_REQUEST", "CHANGE_REASON", "knowledge/reasons/USER_REQUEST.md"),
        _hit(3, "RULE:CUSTOMER_SPEC", "CHANGE_RULE", "knowledge/rules/DC-R-007_CUSTOMER_SPEC_EMI_SHIELD_TAPE.md"),
        _hit(4, "REASON:REGULATION", "CHANGE_REASON", "knowledge/reasons/REGULATION.md"),
        _hit(
            5,
            "RULE:REGULATION",
            "CHANGE_RULE",
            "knowledge/rules/DC-R-008_REGULATION_OPTICAL_ADHESIVE.md",
        ),
    ]
    selected = KnowledgeEvidenceSelector().select(
        "고객사양 변경 기준이 뭐야?", hits, max_hits=3
    )
    assert [hit["document_id"] for hit in selected] == [
        "REASON:CUSTOMER_SPEC",
        "RULE:CUSTOMER_SPEC",
    ]

