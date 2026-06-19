import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import LEAVE_FORM_SYSTEM, RAG_SYSTEM, RISK_SYSTEM, SUMMARY_SYSTEM
from app.agents.router import detect_intent
from app.core.llm import get_chat_llm
from app.models.database import Document
from app.models.schemas import Citation, LeaveFormResult, RiskClause, SummaryResult
from app.parsers import parse_file
from app.rag.retriever import RetrievedChunk, get_retriever


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


async def run_policy_qa(message: str, doc_ids: list[str] | None = None) -> tuple[str, list[Citation]]:
    retriever = get_retriever()
    chunks = retriever.retrieve(message, doc_ids=doc_ids)
    if not chunks:
        return "未在知识库中找到相关信息，请先上传相关制度文档。", []

    context = _format_context(chunks)
    llm = get_chat_llm()
    prompt = f"""【检索上下文】
{context}

【用户问题】
{message}"""
    resp = await llm.ainvoke([SystemMessage(content=RAG_SYSTEM), HumanMessage(content=prompt)])
    return resp.content, chunks_to_citations(chunks)


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


async def run_summary(session: AsyncSession, doc_id: str) -> SummaryResult:
    doc, text = await _get_document_text(session, doc_id)
    llm = get_chat_llm()
    # 长文档分段摘要
    if len(text) > 12000:
        chunks = [text[i : i + 6000] for i in range(0, len(text), 6000)]
        partials = []
        for ch in chunks:
            r = await llm.ainvoke(
                [SystemMessage(content=SUMMARY_SYSTEM), HumanMessage(content=f"文档《{doc.filename}》片段：\n{ch}")]
            )
            partials.append(r.content)
        merge = await llm.ainvoke(
            [
                SystemMessage(content=SUMMARY_SYSTEM),
                HumanMessage(content="请合并以下分段摘要为一份完整总结：\n\n" + "\n\n".join(partials)),
            ]
        )
        content = merge.content
    else:
        r = await llm.ainvoke(
            [SystemMessage(content=SUMMARY_SYSTEM), HumanMessage(content=f"文档《{doc.filename}》\n\n{text}")]
        )
        content = r.content

    outline = [ln.strip("- ").strip() for ln in content.splitlines() if ln.strip().startswith("-")]
    return SummaryResult(summary=content, outline=outline)


async def run_risk_extract(session: AsyncSession, doc_id: str) -> list[RiskClause]:
    doc, text = await _get_document_text(session, doc_id)
    llm = get_chat_llm()
    segments = [text[i : i + 4000] for i in range(0, len(text), 3500)]
    all_items: list[dict] = []
    for seg in segments:
        r = await llm.ainvoke(
            [SystemMessage(content=RISK_SYSTEM), HumanMessage(content=f"《{doc.filename}》\n\n{seg}")]
        )
        raw = r.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                all_items.extend(items)
        except json.JSONDecodeError:
            continue

    seen = set()
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
    return results


async def run_leave_form(session: AsyncSession, message: str, doc_ids: list[str] | None = None) -> LeaveFormResult:
    retriever = get_retriever()
    chunks = retriever.retrieve("请假 制度 流程 年假 事假 病假", doc_ids=doc_ids)
    context = _format_context(chunks) if chunks else "（未检索到请假制度，请基于通用企业规范生成并注明需 HR 确认）"
    llm = get_chat_llm()
    prompt = f"""【请假制度上下文】
{context}

【用户需求】
{message}"""
    r = await llm.ainvoke([SystemMessage(content=LEAVE_FORM_SYSTEM), HumanMessage(content=prompt)])
    refs = [f"{c.filename}" + (f" 第{c.page}页" if c.page else "") for c in chunks[:3]]
    return LeaveFormResult(form_markdown=r.content, policy_refs=refs)


async def handle_chat(
    session: AsyncSession,
    message: str,
    doc_ids: list[str] | None = None,
) -> tuple[str, str, list[Citation]]:
    intent = detect_intent(message)
    if intent == "document_summary":
        if doc_ids:
            result = await run_summary(session, doc_ids[0])
            return intent, result.summary, []
        return intent, "请先在左侧选择一份文档，或上传合同后说「总结这份合同」。", []

    if intent == "risk_extraction":
        if doc_ids:
            risks = await run_risk_extract(session, doc_ids[0])
            if not risks:
                return intent, "未识别到明显风险条款。", []
            lines = ["| 风险等级 | 类别 | 条款 | 建议 |", "|---|---|---|---|"]
            for r in risks:
                lines.append(f"| {r.risk_level} | {r.category} | {r.clause[:80]}... | {r.suggestion} |")
            return intent, "\n".join(lines), []

        return intent, "请先选择要分析的合同文档，再说「提取风险条款」。", []

    if intent == "form_generation":
        result = await run_leave_form(session, message, doc_ids=doc_ids)
        return intent, result.form_markdown, []

    content, citations = await run_policy_qa(message, doc_ids=doc_ids)
    return intent, content, citations
