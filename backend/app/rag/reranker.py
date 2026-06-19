from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def get_reranker():
    settings = get_settings()
    if not settings.rerank_enabled:
        return None
    from sentence_transformers import CrossEncoder

    return CrossEncoder(settings.rerank_model, max_length=512)


def rerank(query: str, texts: list[str]) -> list[tuple[int, float]]:
    """返回 (原索引, 分数) 按分数降序。"""
    if not texts:
        return []
    model = get_reranker()
    if model is None:
        return [(i, 0.0) for i in range(len(texts))]
    pairs = [[query, t] for t in texts]
    scores = model.predict(pairs)
    ranked = sorted(enumerate(scores), key=lambda x: float(x[1]), reverse=True)
    return [(i, float(s)) for i, s in ranked]
