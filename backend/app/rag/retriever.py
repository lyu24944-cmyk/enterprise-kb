from dataclasses import dataclass

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import NodeWithScore

from app.core.config import get_settings
from app.rag.embeddings import get_embedding_model
from app.rag.indexer import get_indexer
from app.rag.reranker import rerank


@dataclass
class RetrievedChunk:
    text: str
    doc_id: str
    filename: str
    page: int | None
    section: str | None
    score: float


class KnowledgeRetriever:
    def __init__(self):
        self.settings = get_settings()
        indexer = get_indexer()
        self._index = VectorStoreIndex.from_vector_store(
            indexer._vector_store,
            embed_model=get_embedding_model(),
        )

    def retrieve(self, query: str, doc_ids: list[str] | None = None, top_k: int | None = None) -> list[RetrievedChunk]:
        k = top_k or self.settings.retrieval_top_k
        retriever = self._index.as_retriever(similarity_top_k=k)
        nodes: list[NodeWithScore] = retriever.retrieve(query)

        results: list[RetrievedChunk] = []
        for node in nodes:
            meta = node.node.metadata or {}
            doc_id = str(meta.get("doc_id", ""))
            if doc_ids and doc_id and doc_id not in doc_ids:
                continue
            results.append(
                RetrievedChunk(
                    text=node.node.get_content(),
                    doc_id=doc_id,
                    filename=str(meta.get("filename", "")),
                    page=meta.get("page"),
                    section=meta.get("section"),
                    score=float(node.score or 0),
                )
            )
        return self._rerank(query, results)[: self.settings.rerank_top_n]

    def _rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return chunks
        if self.settings.rerank_enabled:
            ranked = rerank(query, [c.text for c in chunks])
            out: list[RetrievedChunk] = []
            for idx, score in ranked:
                c = chunks[idx]
                out.append(
                    RetrievedChunk(
                        text=c.text,
                        doc_id=c.doc_id,
                        filename=c.filename,
                        page=c.page,
                        section=c.section,
                        score=score,
                    )
                )
            return out
        return sorted(chunks, key=lambda c: c.score, reverse=True)


_retriever: KnowledgeRetriever | None = None


def get_retriever() -> KnowledgeRetriever:
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever
