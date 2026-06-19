from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Enterprise Knowledge Base"
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_mode: str = "light"  # light | cross_encoder
    rerank_enabled: bool = True
    rerank_max_candidates: int = 5
    vector_store: str = "chroma"
    chroma_persist_dir: str = str(_PROJECT_ROOT / "data" / "chroma")
    chroma_collection: str = "enterprise_kb"
    faiss_index_path: str = str(_PROJECT_ROOT / "data" / "faiss" / "index.bin")

    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 10
    rerank_top_n: int = 5

    database_url: str = f"sqlite+aiosqlite:///{(_PROJECT_ROOT / 'data' / 'app.db').as_posix()}"
    upload_dir: str = str(_PROJECT_ROOT / "data" / "files")
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)

    @property
    def faiss_path(self) -> Path:
        return Path(self.faiss_index_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
