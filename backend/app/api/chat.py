import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import run_leave_form, run_risk_extract, run_summary, stream_chat
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
            _sse_stream(session, chat_session.id, req.message, req.doc_ids),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    from app.agents.service import handle_chat

    intent, content, citations = await handle_chat(session, req.message, req.doc_ids)
    await save_message(session, chat_session.id, "assistant", content, intent=intent, citations=citations)
    return ChatResponse(session_id=chat_session.id, intent=intent, content=content, citations=citations)


async def _sse_stream(session, session_id: str, message: str, doc_ids: list[str]):
    intent = "policy_qa"
    content_parts: list[str] = []
    citations = []

    try:
        yield f"event: meta\ndata: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"

        async for ev in stream_chat(session, message, doc_ids):
            event = ev.get("event", "message")
            if event == "meta":
                intent = ev.get("intent", intent)
                payload = {"session_id": session_id, "intent": intent}
                yield f"event: meta\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            elif event == "status":
                yield f"event: status\ndata: {json.dumps({'message': ev['message']}, ensure_ascii=False)}\n\n"
            elif event == "token":
                content_parts.append(ev["content"])
                yield f"event: token\ndata: {json.dumps({'content': ev['content']}, ensure_ascii=False)}\n\n"
            elif event == "citation":
                citations = ev["sources"]
                yield f"event: citation\ndata: {json.dumps({'sources': citations}, ensure_ascii=False)}\n\n"

        full_content = "".join(content_parts)
        await save_message(session, session_id, "assistant", full_content, intent=intent, citations=citations)
        yield f"event: done\ndata: {json.dumps({'session_id': session_id})}\n\n"
    except Exception as exc:
        err = f"处理失败：{exc}"
        yield f"event: error\ndata: {json.dumps({'message': err}, ensure_ascii=False)}\n\n"
        await save_message(session, session_id, "assistant", err, intent=intent)


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
