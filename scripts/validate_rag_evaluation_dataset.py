from __future__ import annotations

from collections import Counter

from rag.evaluation import RagEvaluationDataset, validate_dataset_against_corpus
from rag.knowledge_corpus import KnowledgeCorpus


DATASET_PATH = "evaluation/rag/retrieval_cases.json"


def main() -> None:
    dataset = RagEvaluationDataset.load(DATASET_PATH)
    corpus = KnowledgeCorpus.from_knowledge_root("knowledge")
    validate_dataset_against_corpus(dataset, corpus)

    categories = Counter(case.category for case in dataset.cases)
    filter_cases = sum(case.filters is not None for case in dataset.cases)
    expected_ids = {
        document_id
        for case in dataset.cases
        for document_id in case.expected_document_ids
    }
    print("RAG retrieval evaluation dataset validation passed")
    print(f"- dataset_id: {dataset.dataset_id}")
    print(f"- case_count: {len(dataset.cases)}")
    print(f"- filter_case_count: {filter_cases}")
    print(f"- expected_document_count: {len(expected_ids)}")
    print(f"- corpus_active_document_count: {len(corpus.active_documents)}")
    print(f"- categories: {dict(sorted(categories.items()))}")


if __name__ == "__main__":
    main()
