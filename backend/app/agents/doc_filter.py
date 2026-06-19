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


async def resolve_doc_ids(
    session: AsyncSession,
    message: str,
    user_doc_ids: list[str] | None,
) -> tuple[str, list[str] | None, str | None]:
    """
    解析应检索的文档范围。
    返回 (intent, doc_ids|None, hint_message|None)
    - doc_ids=None 表示不限制文档
  - doc_ids=[] 不应出现
    """
    intent = detect_intent(message)
    if user_doc_ids:
        return intent, user_doc_ids, None

    categories = INTENT_CATEGORIES.get(intent)
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
