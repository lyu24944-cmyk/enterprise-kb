import uuid
from pathlib import Path

from llama_index.core import Document as LlamaDocument
from llama_index.core import VectorStoreIndex

from app.core.config import Settings, get_settings
from app.parsers import parse_file
from app.rag.chunking import chunk_document
from app.rag.embeddings import get_embedding_model
from app.rag.vector_store import (
    create_vector_store,
    delete_by_doc_id,
    persist_faiss_if_needed,
)


class KnowledgeIndexer:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._vector_store, self._storage, self._handle = create_vector_store(self.settings)
        self._embed = get_embedding_model()

    def index_file(self, file_path: Path, doc_id: str | None = None) -> tuple[str, int, str]:
        doc_id = doc_id or str(uuid.uuid4())
        parsed = parse_file(file_path)
        chunks = chunk_document(
            parsed,
            doc_id=doc_id,
            filename=file_path.name,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )
        if not chunks:
            raise ValueError("文档解析后无有效文本，可能是扫描件 PDF")

        llama_docs = [
            LlamaDocument(text=c["text"], metadata={**c["metadata"], "doc_id": doc_id})
            for c in chunks
        ]
        VectorStoreIndex.from_documents(
            llama_docs,
            storage_context=self._storage,
            embed_model=self._embed,
            show_progress=False,
        )
        persist_faiss_if_needed(self.settings, self._vector_store)
        return doc_id, len(chunks), parsed.category

    def delete_document(self, doc_id: str) -> None:
        delete_by_doc_id(self.settings, self._handle, doc_id)


_indexer: KnowledgeIndexer | None = None


def get_indexer() -> KnowledgeIndexer:
    global _indexer
    if _indexer is None:
        _indexer = KnowledgeIndexer()
    return _indexer
