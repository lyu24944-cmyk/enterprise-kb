import json
from pathlib import Path

import chromadb
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.vector_stores import VectorStore
from llama_index.vector_stores.chroma import ChromaVectorStore

from app.core.config import Settings


def create_vector_store(settings: Settings) -> tuple[VectorStore, StorageContext, object | None]:
    """创建向量存储。返回 (vector_store, storage_context, cleanup_handle)。"""
    if settings.vector_store == "faiss":
        return _create_faiss_store(settings)
    return _create_chroma_store(settings)


def _create_chroma_store(settings: Settings) -> tuple[VectorStore, StorageContext, chromadb.Collection]:
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection = client.get_or_create_collection(settings.chroma_collection)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage = StorageContext.from_defaults(vector_store=vector_store)
    return vector_store, storage, collection


def _create_faiss_store(settings: Settings) -> tuple[VectorStore, StorageContext, Path]:
    import faiss
    from llama_index.vector_stores.faiss import FaissVectorStore

    from app.rag.embeddings import get_embedding_dim

    settings.faiss_path.parent.mkdir(parents=True, exist_ok=True)
    dim = get_embedding_dim()
    meta_path = settings.faiss_path.with_suffix(".meta.json")

    if settings.faiss_path.exists() and meta_path.exists():
        index = faiss.read_index(str(settings.faiss_path))
    else:
        index = faiss.IndexFlatL2(dim)

    vector_store = FaissVectorStore(faiss_index=index)
    storage = StorageContext.from_defaults(vector_store=vector_store)
    return vector_store, storage, settings.faiss_path


def persist_faiss_if_needed(settings: Settings, vector_store: VectorStore) -> None:
    if settings.vector_store != "faiss":
        return
    import faiss

    from llama_index.vector_stores.faiss import FaissVectorStore

    if isinstance(vector_store, FaissVectorStore):
        faiss.write_index(vector_store.faiss_index, str(settings.faiss_path))


def delete_by_doc_id(settings: Settings, handle: object | None, doc_id: str) -> None:
    if settings.vector_store == "chroma" and handle is not None:
        try:
            handle.delete(where={"doc_id": doc_id})  # type: ignore[union-attr]
        except Exception:
            pass
    # FAISS 删除需重建索引，MVP 阶段仅 Chroma 支持按 doc_id 删除
