import json
from collections.abc import AsyncIterator
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.doc_filter import resolve_doc_ids
from app.agents.prompts import LEAVE_FORM_SYSTEM, RAG_SYSTEM, RISK_SYSTEM, SUMMARY_SYSTEM
from app.core.llm import get_chat_llm
from app.models.database import Document
from app.models.schemas import Citation, LeaveFormResult, RiskClause, SummaryResult
from app.parsers import parse_file
from app.rag.retriever import RetrievedChunk, get_retriever


async def _run_retrieve(query: str, doc_ids: list[str] | None) -> list[RetrievedChunk]:
    import asyncio

    retriever = get_retriever()
    return await asyncio.to_thread(retriever.retrieve, query, doc_ids)


def _format_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        loc = []
        if c.filename:
            loc.append(c.filename)
        if c.page:
            loc.append(f"第{c.page}页")
        if c.section:
            loc.append(c.section)
        header = " | ".join(loc) or f"片段{i}"
        parts.append(f"[{header}]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def chunks_to_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            doc_id=c.doc_id,
            filename=c.filename,
            page=c.page,
            section=c.section,
            text=c.text[:300] + ("..." if len(c.text) > 300 else ""),
        )
        for c in chunks
    ]


async def _stream_llm_tokens(system: str, user: str) -> AsyncIterator[str]:
    llm = get_chat_llm()
    async for chunk in llm.astream([SystemMessage(content=system), HumanMessage(content=user)]):
        if chunk.content:
            yield chunk.content


async def _collect_llm(system: str, user: str) -> str:
    parts: list[str] = []
    async for token in _stream_llm_tokens(system, user):
        parts.append(token)
    return "".join(parts)


async def _get_document_text(session: AsyncSession, doc_id: str) -> tuple[Document, str]:
    result = await session.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError("文档不存在")
    parsed = parse_file(Path(doc.file_path))
    text = "\n\n".join(b.text for b in parsed.blocks)
    if not text.strip():
        raise ValueError("文档无有效文本")
    return doc, text


async def stream_policy_qa(
    message: str,
    doc_ids: list[str] | None,
) -> AsyncIterator[dict]:
    yield {"event": "status", "message": "正在检索知识库..."}
    chunks = await _run_retrieve(message, doc_ids)
    if not chunks:
        yield {"event": "token", "content": "未在知识库中找到相关信息，请先上传相关制度文档。"}
        return

    yield {"event": "status", "message": f"已找到 {len(chunks)} 条相关内容，正在生成回答..."}
    context = _format_context(chunks)
    prompt = f"【检索上下文】\n{context}\n\n【用户问题】\n{message}"
    async for token in _stream_llm_tokens(RAG_SYSTEM, prompt):
        yield {"event": "token", "content": token}
    yield {"event": "citation", "sources": [c.model_dump() for c in chunks_to_citations(chunks)]}


async def stream_leave_form(
    message: str,
    doc_ids: list[str] | None,
) -> AsyncIterator[dict]:
    yield {"event": "status", "message": "正在检索请假制度..."}
    chunks = await _run_retrieve("请假 制度 流程 年假 事假 病假", doc_ids)
    context = _format_context(chunks) if chunks else "（未检索到请假制度，请基于通用企业规范生成并注明需 HR 确认）"
    yield {"event": "status", "message": "正在生成请假申请..."}
    prompt = f"【请假制度上下文】\n{context}\n\n【用户需求】\n{message}"
    async for token in _stream_llm_tokens(LEAVE_FORM_SYSTEM, prompt):
        yield {"event": "token", "content": token}


async def stream_summary(session: AsyncSession, doc_id: str) -> AsyncIterator[dict]:
    doc, text = await _get_document_text(session, doc_id)
    yield {"event": "status", "message": f"正在分析《{doc.filename}》..."}
    if len(text) > 12000:
        yield {"event": "status", "message": "文档较长，分段摘要中..."}
        segments = [text[i : i + 6000] for i in range(0, len(text), 6000)]
        partials = []
        for i, ch in enumerate(segments, 1):
            yield {"event": "status", "message": f"摘要片段 {i}/{len(segments)}..."}
            part = await _collect_llm(SUMMARY_SYSTEM, f"文档《{doc.filename}》片段：\n{ch}")
            partials.append(part)
        yield {"event": "status", "message": "正在合并摘要..."}
        content = await _collect_llm(
            SUMMARY_SYSTEM,
            "请合并以下分段摘要为一份完整总结：\n\n" + "\n\n".join(partials),
        )
    else:
        yield {"event": "status", "message": "正在生成摘要..."}
        content = await _collect_llm(SUMMARY_SYSTEM, f"文档《{doc.filename}》\n\n{text}")
    yield {"event": "token", "content": content}


async def stream_risk_extract(session: AsyncSession, doc_id: str) -> AsyncIterator[dict]:
    doc, text = await _get_document_text(session, doc_id)
    yield {"event": "status", "message": f"正在扫描《{doc.filename}》风险条款..."}
    segments = [text[i : i + 4000] for i in range(0, len(text), 3500)]
    all_items: list[dict] = []
    for i, seg in enumerate(segments, 1):
        yield {"event": "status", "message": f"分析片段 {i}/{len(segments)}..."}
        raw = await _collect_llm(RISK_SYSTEM, f"《{doc.filename}》\n\n{seg}")
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                all_items.extend(items)
        except json.JSONDecodeError:
            continue

    seen: set[str] = set()
    results: list[RiskClause] = []
    for item in all_items:
        clause = item.get("clause", "")
        if not clause or clause in seen:
            continue
        seen.add(clause)
        results.append(
            RiskClause(
                clause=clause,
                risk_level=item.get("risk_level", "medium"),
                category=item.get("category", "其他"),
                suggestion=item.get("suggestion", ""),
                location=item.get("location"),
            )
        )

    if not results:
        yield {"event": "token", "content": "未识别到明显风险条款。"}
        return

    lines = ["| 风险等级 | 类别 | 条款 | 建议 |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.risk_level} | {r.category} | {r.clause[:80]}... | {r.suggestion} |")
    yield {"event": "token", "content": "\n".join(lines)}


async def stream_chat(
    session: AsyncSession,
    message: str,
    user_doc_ids: list[str] | None = None,
) -> AsyncIterator[dict]:
    intent, doc_ids, hint = await resolve_doc_ids(session, message, user_doc_ids or [])

    if hint and doc_ids == []:
        yield {"event": "meta", "intent": intent}
        yield {"event": "token", "content": hint}
        return

    yield {"event": "meta", "intent": intent}
    if hint:
        yield {"event": "status", "message": hint}

    if intent == "document_summary":
        if doc_ids:
            async for ev in stream_summary(session, doc_ids[0]):
                yield ev
        else:
            yield {"event": "token", "content": "请勾选一份合同文档，再说「总结这份合同」。"}
        return

    if intent == "risk_extraction":
        if doc_ids:
            async for ev in stream_risk_extract(session, doc_ids[0]):
                yield ev
        else:
            yield {"event": "token", "content": "请勾选要分析的合同文档，再说「提取风险条款」。"}
        return

    if intent == "form_generation":
        async for ev in stream_leave_form(message, doc_ids):
            yield ev
        return

    async for ev in stream_policy_qa(message, doc_ids):
        yield ev


# ---- 非流式兼容（tasks API） ----

async def run_policy_qa(message: str, doc_ids: list[str] | None = None) -> tuple[str, list[Citation]]:
    chunks = await _run_retrieve(message, doc_ids)
    if not chunks:
        return "未在知识库中找到相关信息，请先上传相关制度文档。", []
    context = _format_context(chunks)
    content = await _collect_llm(RAG_SYSTEM, f"【检索上下文】\n{context}\n\n【用户问题】\n{message}")
    return content, chunks_to_citations(chunks)


async def run_summary(session: AsyncSession, doc_id: str) -> SummaryResult:
    parts: list[str] = []
    async for ev in stream_summary(session, doc_id):
        if ev.get("event") == "token":
            parts.append(ev["content"])
    content = "".join(parts)
    outline = [ln.strip("- ").strip() for ln in content.splitlines() if ln.strip().startswith("-")]
    return SummaryResult(summary=content, outline=outline)


async def run_risk_extract(session: AsyncSession, doc_id: str) -> list[RiskClause]:
    # tasks API 保留；流式路径已覆盖主流程
    doc, text = await _get_document_text(session, doc_id)
    raw = await _collect_llm(RISK_SYSTEM, f"《{doc.filename}》\n\n{text[:8000]}")
    try:
        items = json.loads(raw.strip().removeprefix("```json").removesuffix("```"))
        if isinstance(items, list):
            return [
                RiskClause(
                    clause=i.get("clause", ""),
                    risk_level=i.get("risk_level", "medium"),
                    category=i.get("category", "其他"),
                    suggestion=i.get("suggestion", ""),
                    location=i.get("location"),
                )
                for i in items
                if i.get("clause")
            ]
    except (json.JSONDecodeError, AttributeError):
        pass
    return []


async def run_leave_form(session: AsyncSession, message: str, doc_ids: list[str] | None = None) -> LeaveFormResult:
    parts: list[str] = []
    async for ev in stream_leave_form(message, doc_ids):
        if ev.get("event") == "token":
            parts.append(ev["content"])
    return LeaveFormResult(form_markdown="".join(parts), policy_refs=[])


async def handle_chat(
    session: AsyncSession,
    message: str,
    doc_ids: list[str] | None = None,
) -> tuple[str, str, list[Citation]]:
    intent, resolved, hint = await resolve_doc_ids(session, message, doc_ids or [])
    if hint and resolved == []:
        return intent, hint, []

    parts: list[str] = []
    citations: list[Citation] = []
    async for ev in stream_chat(session, message, doc_ids):
        if ev.get("event") == "token":
            parts.append(ev["content"])
        elif ev.get("event") == "citation":
            citations = [Citation(**c) for c in ev["sources"]]
    return intent, "".join(parts), citations
