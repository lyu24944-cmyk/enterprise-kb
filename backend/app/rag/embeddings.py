from functools import lru_cache

from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from app.core.config import get_settings

_DIM_CACHE: dict[str, int] = {
    "BAAI/bge-small-zh-v1.5": 512,
    "BAAI/bge-m3": 1024,
}


@lru_cache
def get_embedding_model() -> HuggingFaceEmbedding:
    settings = get_settings()
    return HuggingFaceEmbedding(model_name=settings.embedding_model)


def get_embedding_dim() -> int:
    settings = get_settings()
    if settings.embedding_model in _DIM_CACHE:
        return _DIM_CACHE[settings.embedding_model]
    return 512
