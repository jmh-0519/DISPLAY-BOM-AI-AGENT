# RAG Foundation

The RAG layer is a knowledge-evidence subsystem. It does not replace BOM/Inventory/Supplier authority data or the deterministic Rule Engine.

## Required environment variables

The existing Azure OpenAI variables are reused:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`

RAG additionally requires:

- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`: Azure deployment name for the embedding model.

Optional:

- `RAG_VECTOR_STORE_PATH` (default: `data/rag/chroma`)
- `RAG_COLLECTION_NAME` (default: `display_bom_knowledge`)
- `RAG_EMBEDDING_BATCH_SIZE` (default: `64`)

## Local commands

```powershell
python -m scripts.validate_rag_environment
python -m scripts.smoke_test_rag_embedding
python -m scripts.build_rag_index
python -m scripts.search_rag_knowledge "단종 자재 교체 기준" --top-k 5
```

The Chroma index is local runtime data and is intentionally ignored by Git.
