from __future__ import annotations

from rag.config import RagSettings
from rag.embedding_client import AzureOpenAIEmbeddingClient


def main() -> None:
    settings = RagSettings.from_env()
    provider = AzureOpenAIEmbeddingClient(settings)
    embedding = provider.embed_query("Display BOM 설계변경 지식 검색")
    print("Azure OpenAI embedding smoke test passed")
    print(f"- deployment: {settings.azure_openai_embedding_deployment}")
    print(f"- dimension: {len(embedding)}")


if __name__ == "__main__":
    main()
