import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import DocumentOut
from app.services.db_service import SessionLocal, delete_document, ingest_document, list_documents, save_upload

router = APIRouter(prefix="/documents", tags=["documents"])


async def get_session():
    async with SessionLocal() as session:
        yield session


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in {".pdf", ".docx", ".pptx", ".xlsx"}:
        raise HTTPException(400, f"不支持的格式: {ext}")
    content = await file.read()
    if len(content) > 30 * 1024 * 1024:
        raise HTTPException(400, "文件不能超过 30MB")
    path = await save_upload(content, file.filename)
    try:
        doc = await ingest_document(session, path, file.filename)
    except Exception as exc:
        raise HTTPException(500, f"文档入库失败: {exc}") from exc
    return doc


@router.get("", response_model=list[DocumentOut])
async def get_documents(session: AsyncSession = Depends(get_session)):
    return await list_documents(session)


@router.delete("/{doc_id}")
async def remove_document(doc_id: str, session: AsyncSession = Depends(get_session)):
    ok = await delete_document(session, doc_id)
    if not ok:
        raise HTTPException(404, "文档不存在")
    return {"ok": True}
