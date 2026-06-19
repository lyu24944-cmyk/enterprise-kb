import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, documents
from app.core.config import get_settings
from app.services.db_service import init_db


def _warmup_models() -> None:
    from app.core.config import get_settings
    from app.rag.embeddings import get_embedding_model
    from app.rag.reranker import get_cross_encoder

    settings = get_settings()
    get_embedding_model()
    if settings.rerank_enabled and settings.rerank_mode == "cross_encoder":
        get_cross_encoder()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _warmup_models)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.1",
        description="AI Agent + RAG 企业知识库",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "llm": settings.llm_provider,
            "embedding": settings.embedding_model,
            "vector_store": settings.vector_store,
            "rerank": f"{settings.rerank_mode}" if settings.rerank_enabled else "disabled",
        }

    return app


app = create_app()
