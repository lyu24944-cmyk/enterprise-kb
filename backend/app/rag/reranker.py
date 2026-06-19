from functools import lru_cache

from app.core.config import get_settings


def _light_rerank(query: str, texts: list[str]) -> list[tuple[int, float]]:
    """轻量重排：中文关键词命中 + 位置加权，毫秒级完成。"""
    q_chars = set(query.replace("？", "").replace("?", "").strip())
    q_words = [w for w in query.replace("？", " ").replace("?", " ").split() if len(w) >= 2]

    scored: list[tuple[int, float]] = []
    for i, text in enumerate(texts):
        score = 0.0
        for w in q_words:
            if w in text:
                score += 2.0
        overlap = sum(1 for c in q_chars if c in text)
        score += overlap / max(len(q_chars), 1)
        scored.append((i, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


@lru_cache
def get_cross_encoder():
    from sentence_transformers import CrossEncoder

    settings = get_settings()
    return CrossEncoder(settings.rerank_model, max_length=512)


def rerank(query: str, texts: list[str]) -> list[tuple[int, float]]:
    if not texts:
        return []

    settings = get_settings()
    if not settings.rerank_enabled:
        return [(i, 0.0) for i in range(len(texts))]

    if settings.rerank_mode == "cross_encoder":
        # 仅对少量候选做 Cross-Encoder，避免 CPU 上 100s+ 阻塞
        candidates = texts[: settings.rerank_max_candidates]
        model = get_cross_encoder()
        pairs = [[query, t] for t in candidates]
        scores = model.predict(pairs)
        ranked = sorted(enumerate(scores), key=lambda x: float(x[1]), reverse=True)
        return [(i, float(s)) for i, s in ranked]

    return _light_rerank(query, texts)
