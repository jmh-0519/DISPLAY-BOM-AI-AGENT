from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag.evaluation import (
    RagEvaluationDataset,
    RagEvaluationError,
    RagRetrievalEvaluator,
)
from rag.retrieval_service import RagSearchResponse
from rag.vector_store import KnowledgeSearchHit


def _hit(rank: int, document_id: str, *, document_type: str = "FAQ") -> KnowledgeSearchHit:
    return KnowledgeSearchHit(
        rank=rank,
        chunk_id=f"{document_id}:{rank}",
        content="content",
        distance=float(rank) / 10.0,
        document_id=document_id,
        document_title=document_id,
        document_type=document_type,
        section_title="section",
        section_path="section",
        source_file=f"knowledge/{document_id}.md",
        source_page=None,
        metadata={
            "status": "ACTIVE",
            "language": "KO",
            "product_families_json": json.dumps(["DISPLAY"]),
            "material_types_json": json.dumps(["ASSY"]),
            "tags_json": json.dumps(["FAQ", "TEST"]),
        },
    )


class FakeRetrievalService:
    def search(self, query, *, top_k=5, filters=None):
        if query == "first":
            hits = (_hit(1, "DOC-A"), _hit(2, "DOC-X"))
        else:
            hits = (_hit(1, "DOC-X"), _hit(2, "DOC-B"))
        return RagSearchResponse(query=query, hits=hits[:top_k])


def _dataset(tmp_path: Path) -> RagEvaluationDataset:
    payload = {
        "dataset_id": "TEST",
        "version": "1",
        "gates": {
            "hit_rate_at_5_min": 1.0,
            "mean_recall_at_5_min": 1.0,
            "mrr_min": 0.70,
            "filter_accuracy_min": 1.0,
        },
        "cases": [
            {
                "case_id": "C1",
                "query": "first",
                "expected_document_ids": ["DOC-A"],
                "category": "FAQ",
                "top_k": 5,
            },
            {
                "case_id": "C2",
                "query": "second",
                "expected_document_ids": ["DOC-B"],
                "category": "FAQ",
                "top_k": 5,
                "filters": {"document_type": "FAQ", "tag": "TEST"},
            },
        ],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return RagEvaluationDataset.load(path)


def test_retrieval_evaluator_computes_rank_filter_and_gate_metrics(tmp_path):
    summary = RagRetrievalEvaluator(FakeRetrievalService()).evaluate(_dataset(tmp_path))

    assert summary.case_count == 2
    assert summary.hit_rate_at_1 == 0.5
    assert summary.hit_rate_at_3 == 1.0
    assert summary.hit_rate_at_5 == 1.0
    assert summary.mean_recall_at_5 == 1.0
    assert summary.mrr == pytest.approx(0.75)
    assert summary.filter_accuracy == 1.0
    assert summary.gate_pass is True
    assert summary.category_metrics["FAQ"]["case_count"] == 2
    assert summary.category_metrics["FAQ"]["hit_rate_at_5"] == 1.0
    assert summary.cases[1].relevant_ranks == (2,)


def test_dataset_rejects_duplicate_case_ids(tmp_path):
    payload = {
        "dataset_id": "TEST",
        "version": "1",
        "cases": [
            {"case_id": "DUP", "query": "a", "expected_document_ids": ["A"], "category": "FAQ", "top_k": 5},
            {"case_id": "DUP", "query": "b", "expected_document_ids": ["B"], "category": "FAQ", "top_k": 5},
        ],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RagEvaluationError, match="duplicate evaluation case ids"):
        RagEvaluationDataset.load(path)
