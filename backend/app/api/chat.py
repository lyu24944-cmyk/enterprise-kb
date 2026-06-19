import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import handle_chat, run_leave_form, run_risk_extract, run_summary
from app.models.schemas import ChatRequest, ChatResponse, LeaveFormResult, RiskClause, SummaryResult, TaskRequest
from app.services.db_service import SessionLocal, create_task_record, get_document, get_or_create_session, save_message

router = APIRouter(tags=["chat"])


async def get_session():
    async with SessionLocal() as session:
        yield session


@router.post("/chat")
async def chat(req: ChatRequest, session: AsyncSession = Depends(get_session)):
    if not req.message.strip():
        raise HTTPException(400, "消息不能为空")

    chat_session = await get_or_create_session(session, req.session_id)
    await save_message(session, chat_session.id, "user", req.message)

    if req.stream:
        return StreamingResponse(
            _stream_chat(session, chat_session.id, req.message, req.doc_ids),
            media_type="text/event-stream",
        )

    intent, content, citations = await handle_chat(session, req.message, req.doc_ids)
    await save_message(session, chat_session.id, "assistant", content, intent=intent, citations=citations)
    return ChatResponse(session_id=chat_session.id, intent=intent, content=content, citations=citations)


async def _stream_chat(session, session_id: str, message: str, doc_ids: list[str]):
    intent, content, citations = await handle_chat(session, message, doc_ids)
    await save_message(session, session_id, "assistant", content, intent=intent, citations=citations)

    yield f"event: meta\ndata: {json.dumps({'session_id': session_id, 'intent': intent}, ensure_ascii=False)}\n\n"

    step = 20
    for i in range(0, len(content), step):
        chunk = content[i : i + step]
        yield f"event: token\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

    if citations:
        payload = [c.model_dump() for c in citations]
        yield f"event: citation\ndata: {json.dumps({'sources': payload}, ensure_ascii=False)}\n\n"

    yield f"event: done\ndata: {json.dumps({'session_id': session_id})}\n\n"


@router.post("/tasks/summary", response_model=SummaryResult)
async def task_summary(req: TaskRequest, session: AsyncSession = Depends(get_session)):
    doc = await get_document(session, req.doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    result = await run_summary(session, req.doc_id)
    await create_task_record(session, "summary", req.doc_id, req.extra, result.model_dump())
    return result


@router.post("/tasks/risk-extract", response_model=list[RiskClause])
async def task_risk(req: TaskRequest, session: AsyncSession = Depends(get_session)):
    doc = await get_document(session, req.doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    result = await run_risk_extract(session, req.doc_id)
    await create_task_record(session, "risk_extract", req.doc_id, req.extra, [r.model_dump() for r in result])
    return result


@router.post("/tasks/leave-form", response_model=LeaveFormResult)
async def task_leave(req: ChatRequest, session: AsyncSession = Depends(get_session)):
    result = await run_leave_form(session, req.message, doc_ids=req.doc_ids)
    return result
