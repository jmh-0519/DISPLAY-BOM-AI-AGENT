from __future__ import annotations

import argparse

from rag.config import RagSettings
from rag.embedding_client import AzureOpenAIEmbeddingClient
from rag.retrieval_service import RagRetrievalService
from rag.vector_store import ChromaVectorStore, KnowledgeSearchFilter


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the local RAG knowledge index.")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--document-type")
    parser.add_argument("--material-type")
    parser.add_argument("--product-family")
    parser.add_argument("--tag")
    args = parser.parse_args()

    settings = RagSettings.from_env()
    service = RagRetrievalService(
        embedding_provider=AzureOpenAIEmbeddingClient(settings),
        vector_store=ChromaVectorStore(
            settings.vector_store_path,
            settings.collection_name,
        ),
    )
    response = service.search(
        args.query,
        top_k=args.top_k,
        filters=KnowledgeSearchFilter(
            document_type=args.document_type,
            material_type=args.material_type,
            product_family=args.product_family,
            tag=args.tag,
        ),
    )
    print(f"query: {response.query}")
    print(f"hits: {len(response.hits)}")
    for hit in response.hits:
        distance = "-" if hit.distance is None else f"{hit.distance:.6f}"
        print(
            f"[{hit.rank}] distance={distance} "
            f"{hit.document_type} / {hit.document_title} / {hit.section_path}"
        )
        print(f"    source: {hit.source_file}")
        print(f"    content: {hit.content[:240].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()
