from collections import Counter

from rag.evaluation import RagEvaluationDataset, validate_dataset_against_corpus
from rag.knowledge_corpus import KnowledgeCorpus


DATASET_PATH = "evaluation/rag/retrieval_cases.json"


def test_controlled_rag_evaluation_dataset_has_full_knowledge_coverage():
    dataset = RagEvaluationDataset.load(DATASET_PATH)
    corpus = KnowledgeCorpus.from_knowledge_root("knowledge")

    validate_dataset_against_corpus(dataset, corpus)

    assert len(dataset.cases) == 56
    assert sum(case.filters is not None for case in dataset.cases) == 28
    type_counts = Counter(document.metadata.document_type for document in corpus.active_documents)
    assert type_counts["CHANGE_REASON"] >= 10
    assert type_counts["CHANGE_RULE"] >= 10
    assert type_counts["DESIGN_GUIDE"] >= 3
    assert type_counts["MATERIAL_SPEC"] >= 3
    assert type_counts["PROCESS_GUIDE"] >= 3
    assert type_counts["CHANGE_POLICY"] >= 3
    assert type_counts["SUPPLIER_TECHNICAL"] >= 3
    assert type_counts["FAQ"] >= 3

    expected_ids = {
        document_id
        for case in dataset.cases
        for document_id in case.expected_document_ids
    }
    active_ids = {document.metadata.document_id for document in corpus.active_documents}
    assert len(expected_ids) == 38
    assert expected_ids.issubset(active_ids)


def test_each_controlled_general_document_has_two_paraphrase_cases():
    dataset = RagEvaluationDataset.load(DATASET_PATH)
    counts = Counter(
        document_id
        for case in dataset.cases
        if case.case_id.startswith("GEN-")
        for document_id in case.expected_document_ids
    )

    assert len(counts) == 18
    assert set(counts.values()) == {2}
