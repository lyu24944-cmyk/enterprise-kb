import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.router import detect_intent
from app.models.database import Document

INTENT_CATEGORIES: dict[str, list[str]] = {
    "policy_qa": ["policy"],
    "form_generation": ["policy"],
    "document_summary": ["contract"],
    "risk_extraction": ["contract"],
}


async def _docs_by_ids(session: AsyncSession, ids: list[str]) -> list[Document]:
    if not ids:
        return []
    result = await session.execute(select(Document).where(Document.id.in_(ids)))
    return list(result.scalars().all())


async def resolve_doc_ids(
    session: AsyncSession,
    message: str,
    user_doc_ids: list[str] | None,
) -> tuple[str, list[str] | None, str | None]:
    intent = detect_intent(message)
    categories = INTENT_CATEGORIES.get(intent)

    if user_doc_ids:
        selected = await _docs_by_ids(session, user_doc_ids)
        if categories and selected:
            filtered = [d for d in selected if d.category in categories]
            if filtered and len(filtered) < len(selected):
                skip = len(selected) - len(filtered)
                label = "制度" if "policy" in categories else "合同"
                hint = f"已自动忽略 {skip} 份非{label}类文档，避免检索噪声"
                return intent, [d.id for d in filtered], hint
            if filtered:
                return intent, [d.id for d in filtered], None
        return intent, user_doc_ids, None

    if not categories:
        return intent, None, None

    result = await session.execute(
        select(Document).where(Document.status == "ready", Document.category.in_(categories))
    )
    matched = list(result.scalars().all())

    if intent in ("document_summary", "risk_extraction"):
        if len(matched) == 1:
            return intent, [matched[0].id], None
        if not matched:
            return intent, [], "未找到合同类文档，请上传合同或手动勾选。"
        return intent, [], "请勾选一份要分析的合同文档。"

    if matched:
        hint = f"已自动筛选 {len(matched)} 份制度类文档（未勾选时将忽略合同等无关文件）"
        return intent, [d.id for d in matched], hint

    return intent, None, None
