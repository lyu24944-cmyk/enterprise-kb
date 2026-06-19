"""RAG 检索评测：对比 有/无 Rerank 的 Hit@5。"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

EVAL_SET = [
    ("公司年假多少天", ["年假", "5 天", "5天", "10 天", "10天"]),
    ("事假怎么申请", ["事假", "OA", "主管"]),
    ("病假需要什么材料", ["病假", "医院", "证明"]),
    ("合同总金额多少", ["500,000", "500000", "五十万"]),
    ("乙方延期交付违约金", ["0.5%", "违约金"]),
    ("知识产权归谁", ["甲方", "知识产权"]),
    ("请假审批时限", ["2个工作日", "主管审批"]),
    ("婚假多少天", ["婚假", "3 天", "3天"]),
]


def _hit_at_k(texts: list[str], keywords: list[str], k: int = 5) -> bool:
    blob = " ".join(texts[:k])
    return any(kw in blob for kw in keywords)


def _raw_retrieve(query: str, top_k: int) -> list[str]:
    from llama_index.core import VectorStoreIndex

    from app.rag.embeddings import get_embedding_model
    from app.rag.indexer import get_indexer

    idx = VectorStoreIndex.from_vector_store(
        get_indexer()._vector_store,
        embed_model=get_embedding_model(),
    )
    nodes = idx.as_retriever(similarity_top_k=top_k).retrieve(query)
    return [n.node.get_content() for n in nodes]


def run_eval() -> None:
    from app.core.config import get_settings
    from app.rag.retriever import get_retriever

    settings = get_settings()
    retriever = get_retriever()
    top_n = settings.rerank_top_n
    top_k = settings.retrieval_top_k

    hit_with, hit_without = 0, 0

    print(f"向量库: {settings.vector_store} | Embedding: {settings.embedding_model}")
    print(f"Rerank: {settings.rerank_model if settings.rerank_enabled else 'disabled'}")
    print("-" * 52)

    for query, keywords in EVAL_SET:
        reranked = retriever.retrieve(query)
        ok_r = _hit_at_k([c.text for c in reranked], keywords, top_n)
        if ok_r:
            hit_with += 1

        plain = _raw_retrieve(query, top_k)[:top_n]
        ok_n = _hit_at_k(plain, keywords, top_n)
        if ok_n:
            hit_without += 1

        print(f"  [{'✓' if ok_r else '✗'} rerank / {'✓' if ok_n else '✗'} plain] {query}")

    total = len(EVAL_SET)
    print("-" * 52)
    print(f"Hit@{top_n} 无 Rerank: {hit_without}/{total} = {hit_without/total:.1%}")
    print(f"Hit@{top_n} 有 Rerank: {hit_with}/{total} = {hit_with/total:.1%}")
    diff = hit_with - hit_without
    if diff > 0:
        print(f"Rerank 多命中 {diff} 条")


if __name__ == "__main__":
    run_eval()
