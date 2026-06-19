from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, documents
from app.core.config import get_settings
from app.services.db_service import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0-mvp",
        description="AI Agent + RAG 企业知识库 MVP",
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
            "rerank": settings.rerank_model if settings.rerank_enabled else "disabled",
        }

    return app


app = create_app()
