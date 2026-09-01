from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.chunker import StructureAwareChunker
from rag.config import RagSettings
from rag.embedding_client import AzureOpenAIEmbeddingClient
from rag.evaluation import (
    RagEvaluationDataset,
    RagRetrievalEvaluator,
    validate_dataset_against_corpus,
)
from rag.index_service import RagIndexService
from rag.knowledge_corpus import KnowledgeCorpus
from rag.retrieval_service import RagRetrievalService
from rag.vector_store import ChromaVectorStore


DEFAULT_DATASET = "evaluation/rag/retrieval_cases.json"
DEFAULT_OUTPUT = "data/rag/evaluation/retrieval_evaluation_latest.json"


def _percent(value: float) -> str:
    return f"{value * 100.0:.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate semantic retrieval quality against controlled RAG ground truth."
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--knowledge-root", default="knowledge")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Rebuild the persistent vector index before running retrieval evaluation.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with failure when the configured retrieval quality gate is not met.",
    )
    args = parser.parse_args()

    dataset = RagEvaluationDataset.load(args.dataset)
    corpus = KnowledgeCorpus.from_knowledge_root(
        args.knowledge_root, include_evaluation=True
    )
    validate_dataset_against_corpus(dataset, corpus)

    settings = RagSettings.from_env()
    embedding_provider = AzureOpenAIEmbeddingClient(settings)
    evaluation_store_path = settings.vector_store_path.parent / "evaluation" / "chroma"
    evaluation_collection_name = f"{settings.collection_name}_evaluation"
    vector_store = ChromaVectorStore(
        evaluation_store_path, evaluation_collection_name
    )

    chunker = StructureAwareChunker()
    expected_chunk_count = len(chunker.chunk_documents(corpus.active_documents))

    if args.rebuild_index:
        build_result = RagIndexService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            chunker=chunker,
        ).rebuild(corpus)
        print("RAG evaluation index rebuilt")
        print(f"- documents: {build_result.document_count}")
        print(f"- chunks: {build_result.chunk_count}")
        print(f"- embedding_dimension: {build_result.embedding_dimension}")
        print(f"- evaluation_store_path: {evaluation_store_path}")
        print(f"- evaluation_collection: {evaluation_collection_name}")
    elif vector_store.count() != expected_chunk_count:
        raise RuntimeError(
            "RAG vector index is stale: "
            f"index_chunks={vector_store.count()} corpus_chunks={expected_chunk_count}. "
            "Run with --rebuild-index."
        )

    service = RagRetrievalService(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )
    summary = RagRetrievalEvaluator(service).evaluate(dataset)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("RAG retrieval evaluation completed")
    print(f"- dataset: {summary.dataset_id} v{summary.dataset_version}")
    print(f"- cases: {summary.case_count}")
    print(f"- filter_cases: {summary.filter_case_count}")
    print(f"- Hit Rate@1: {_percent(summary.hit_rate_at_1)}")
    print(f"- Hit Rate@3: {_percent(summary.hit_rate_at_3)}")
    print(f"- Hit Rate@5: {_percent(summary.hit_rate_at_5)}")
    print(f"- Mean Recall@5: {_percent(summary.mean_recall_at_5)}")
    print(f"- MRR: {summary.mrr:.4f}")
    print(f"- Metadata Filter Accuracy: {_percent(summary.filter_accuracy)}")
    print(f"- Miss Rate@5: {_percent(summary.miss_rate_at_5)}")
    print(f"- Latency P50: {summary.latency_p50_ms:.2f}ms")
    print(f"- Latency P95: {summary.latency_p95_ms:.2f}ms")
    print(f"- Gate: {'PASS' if summary.gate_pass else 'FAIL'}")
    print("- Category metrics:")
    for category, metrics in summary.category_metrics.items():
        print(
            f"  {category}: cases={metrics['case_count']} "
            f"H@1={_percent(float(metrics['hit_rate_at_1']))} "
            f"H@5={_percent(float(metrics['hit_rate_at_5']))} "
            f"MRR={float(metrics['mrr']):.4f}"
        )
    print(f"- report: {output_path.as_posix()}")

    failed_cases = [case for case in summary.cases if not case.hit_at_5]
    if failed_cases:
        print("- Top-5 misses:")
        for case in failed_cases:
            retrieved = ", ".join(case.retrieved_document_ids[:5]) or "<none>"
            expected = ", ".join(case.expected_document_ids)
            print(f"  {case.case_id}: expected=[{expected}] retrieved=[{retrieved}]")

    if args.strict and not summary.gate_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
