from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class RagSettings:
    """Runtime settings for knowledge embedding and local vector retrieval."""

    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_api_version: str
    azure_openai_embedding_deployment: str
    vector_store_path: Path = Path("data/rag/chroma")
    collection_name: str = "display_bom_knowledge"
    embedding_batch_size: int = 64

    @classmethod
    def from_env(cls) -> "RagSettings":
        # Standalone RAG scripts must load the same project .env as the main app.
        load_dotenv()
        values = {
            "azure_openai_api_key": os.getenv("AZURE_OPENAI_API_KEY", "").strip(),
            "azure_openai_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", "").strip(),
            "azure_openai_api_version": os.getenv("AZURE_OPENAI_API_VERSION", "").strip(),
            "azure_openai_embedding_deployment": os.getenv(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", ""
            ).strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(
                "RAG 필수 환경설정이 누락되었습니다: " + ", ".join(missing)
            )

        vector_path = Path(
            os.getenv("RAG_VECTOR_STORE_PATH", "data/rag/chroma").strip()
            or "data/rag/chroma"
        )
        collection_name = (
            os.getenv("RAG_COLLECTION_NAME", "display_bom_knowledge").strip()
            or "display_bom_knowledge"
        )
        batch_size_raw = os.getenv("RAG_EMBEDDING_BATCH_SIZE", "64").strip() or "64"
        try:
            batch_size = int(batch_size_raw)
        except ValueError as exc:
            raise ValueError("RAG_EMBEDDING_BATCH_SIZE는 정수여야 합니다.") from exc
        if batch_size < 1 or batch_size > 2048:
            raise ValueError("RAG_EMBEDDING_BATCH_SIZE는 1~2048 범위여야 합니다.")

        return cls(
            azure_openai_api_key=values["azure_openai_api_key"],
            azure_openai_endpoint=values["azure_openai_endpoint"].rstrip("/"),
            azure_openai_api_version=values["azure_openai_api_version"],
            azure_openai_embedding_deployment=values[
                "azure_openai_embedding_deployment"
            ],
            vector_store_path=vector_path,
            collection_name=collection_name,
            embedding_batch_size=batch_size,
        )


__all__ = ["RagSettings"]
