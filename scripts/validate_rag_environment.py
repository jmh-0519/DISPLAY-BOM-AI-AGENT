from __future__ import annotations

import importlib.metadata as metadata

from rag.config import RagSettings


def main() -> None:
    settings = RagSettings.from_env()
    packages = {}
    for name in ("openai", "chromadb", "pypdf", "python-docx"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = "NOT INSTALLED"
    if packages["chromadb"] == "NOT INSTALLED":
        raise RuntimeError("chromadb가 설치되어 있지 않습니다.")
    print("RAG environment validation passed")
    print(f"- embedding_deployment: {settings.azure_openai_embedding_deployment}")
    print(f"- vector_store_path: {settings.vector_store_path}")
    print(f"- collection_name: {settings.collection_name}")
    print(f"- packages: {packages}")


if __name__ == "__main__":
    main()
