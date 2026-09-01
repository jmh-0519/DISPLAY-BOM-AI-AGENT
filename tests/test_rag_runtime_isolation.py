from pathlib import Path

from rag.knowledge_corpus import KnowledgeCorpus
from rag.runtime import search_knowledge
from rag.retrieval_service import RagSearchResponse
from rag.vector_store import KnowledgeSearchHit


def _write_doc(path: Path, document_id: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "+++\n"
        f'document_id = "{document_id}"\n'
        f'document_title = "{title}"\n'
        'document_type = "FAQ"\n'
        'version = "1"\n'
        'effective_date = "2026-01-01"\n'
        'status = "ACTIVE"\n'
        'language = "KO"\n'
        "+++\n\n"
        f"# {title}\n\n본문\n",
        encoding="utf-8",
    )


def test_runtime_corpus_excludes_evaluation_documents(tmp_path):
    root = tmp_path / "knowledge"
    _write_doc(root / "documents" / "runtime" / "RUN.md", "RUN", "운영 문서")
    _write_doc(root / "documents" / "evaluation" / "EVAL.md", "EVAL", "평가 문서")

    full = KnowledgeCorpus.from_knowledge_root(root, include_evaluation=True)
    runtime = KnowledgeCorpus.from_knowledge_root(root, include_evaluation=False)

    assert {doc.metadata.document_id for doc in full.documents} == {"RUN", "EVAL"}
    assert {doc.metadata.document_id for doc in runtime.documents} == {"RUN"}


class _FakeRetrieval:
    def search(self, query, *, top_k, filters):
        return RagSearchResponse(
            query=query,
            hits=(
                KnowledgeSearchHit(
                    rank=1,
                    chunk_id="eval:1",
                    content="evaluation",
                    distance=0.1,
                    document_id="EVAL",
                    document_title="평가 문서",
                    document_type="FAQ",
                    section_title="평가",
                    section_path="평가",
                    source_file="knowledge/documents/evaluation/EVAL.md",
                    source_page=None,
                    metadata={},
                ),
                KnowledgeSearchHit(
                    rank=2,
                    chunk_id="run:1",
                    content="runtime",
                    distance=0.2,
                    document_id="RUN",
                    document_title="운영 문서",
                    document_type="FAQ",
                    section_title="운영",
                    section_path="운영",
                    source_file="knowledge/documents/runtime/RUN.md",
                    source_page=None,
                    metadata={},
                ),
            ),
        )


def test_runtime_search_defensively_blocks_evaluation_hits():
    result = search_knowledge("설계변경 FAQ", top_k=5, retrieval_service=_FakeRetrieval())
    assert [hit["document_id"] for hit in result["hits"]] == ["RUN"]
