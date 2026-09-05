# RAG Knowledge Evidence

RAG는 Display BOM AI Agent의 **Read-only Knowledge Evidence 계층**입니다.

## Responsibility

- 설계변경 Policy / Rule / Reason / Guide / FAQ / Material / Supplier 문서를 검색합니다.
- `FAST_KNOWLEDGE`는 정책/기준/가이드/사양 질문을 deterministic하게 처리합니다.
- Design Change 분석에서는 필요한 Knowledge Evidence를 Workflow Composition에 제공합니다.
- BOM 사실, 공급사, 재고, 비용, PASS / CONDITIONAL / FAIL 및 Apply Authority는 SQLite / Service / Rule Engine에 남습니다.
- RAG 결과만으로 Production 변경을 수행하지 않습니다.

## Knowledge Source

```text
knowledge/
├─ rules/
├─ reasons/
└─ documents/
```

## Runtime

- Azure OpenAI Embedding
- Chroma Vector Store
- Metadata filtering
- deterministic query routing
- Evidence selection / enrichment

환경 변수:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `RAG_VECTOR_STORE_PATH` (optional)
- `RAG_COLLECTION_NAME` (optional)
- `RAG_EMBEDDING_BATCH_SIZE` (optional)

## Commands

```powershell
python -m scripts.validate_rag_environment
python -m scripts.smoke_test_rag_embedding
python -m scripts.build_rag_index
python -m scripts.search_rag_knowledge "단종 자재 교체 기준" --top-k 5
python -m scripts.run_rag_retrieval_evaluation --rebuild-index --strict
```

## v4.0 Evaluation

```text
Cases                     56
Hit Rate@1                94.64%
Hit Rate@3                100.00%
Hit Rate@5                100.00%
Mean Recall@5             100.00%
MRR                       0.9702
Metadata Filter Accuracy  100.00%
P95 Latency               176.83 ms
Gate                      PASS
```

Chroma index는 local runtime data이며 Git에 포함하지 않습니다.
