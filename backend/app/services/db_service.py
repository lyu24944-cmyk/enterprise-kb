import json
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.database import Base, ChatMessage, ChatSession, Document, Task
from app.rag.indexer import get_indexer

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_upload(file_bytes: bytes, filename: str) -> Path:
    dest = settings.upload_path / f"{uuid.uuid4().hex}_{filename}"
    dest.write_bytes(file_bytes)
    return dest


async def ingest_document(session: AsyncSession, file_path: Path, filename: str) -> Document:
    doc = Document(
        id=str(uuid.uuid4()),
        filename=filename,
        doc_type=file_path.suffix.lower().lstrip("."),
        file_path=str(file_path),
        status="processing",
    )
    session.add(doc)
    await session.commit()

    try:
        indexer = get_indexer()
        doc_id, chunk_count, category = indexer.index_file(file_path, doc_id=doc.id)
        doc.id = doc_id
        doc.chunk_count = chunk_count
        doc.category = category
        doc.status = "ready"
    except Exception as exc:
        doc.status = "failed"
        await session.commit()
        raise exc

    await session.commit()
    await session.refresh(doc)
    return doc


async def list_documents(session: AsyncSession) -> list[Document]:
    result = await session.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars().all())


async def get_document(session: AsyncSession, doc_id: str) -> Document | None:
    result = await session.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()


async def delete_document(session: AsyncSession, doc_id: str) -> bool:
    doc = await get_document(session, doc_id)
    if not doc:
        return False
    get_indexer().delete_document(doc_id)
    Path(doc.file_path).unlink(missing_ok=True)
    await session.delete(doc)
    await session.commit()
    return True


async def get_or_create_session(session: AsyncSession, session_id: str | None) -> ChatSession:
    if session_id:
        result = await session.execute(select(ChatSession).where(ChatSession.id == session_id))
        found = result.scalar_one_or_none()
        if found:
            return found
    chat = ChatSession(id=str(uuid.uuid4()), title="新对话")
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    return chat


async def save_message(
    session: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    citations: list | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        citations=json.dumps([c.model_dump() if hasattr(c, "model_dump") else c for c in (citations or [])], ensure_ascii=False),
    )
    session.add(msg)
    await session.commit()
    return msg


async def create_task_record(
    session: AsyncSession,
    task_type: str,
    doc_id: str,
    input_data: dict,
    output_data: dict,
) -> Task:
    task = Task(
        id=str(uuid.uuid4()),
        task_type=task_type,
        doc_id=doc_id,
        input_json=json.dumps(input_data, ensure_ascii=False),
        output_json=json.dumps(output_data, ensure_ascii=False),
        status="done",
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task
