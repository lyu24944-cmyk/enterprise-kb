import re

INTENT_RULES: dict[str, list[str]] = {
    "policy_qa": ["多少", "几天", "制度", "规定", "流程", "怎么", "如何", "是否", "可以", "年假", "考勤", "福利"],
    "document_summary": ["总结", "概括", "摘要", "梳理", "归纳", "大纲"],
    "risk_extraction": ["风险", "条款", "陷阱", "不利", "违约", "提取"],
    "form_generation": ["生成", "请假", "申请", "填写", "模板", "起草"],
}


def detect_intent(message: str) -> str:
    text = message.strip()
    scores: dict[str, int] = {k: 0 for k in INTENT_RULES}
    for intent, keywords in INTENT_RULES.items():
        for kw in keywords:
            if kw in text:
                scores[intent] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "policy_qa"
    return best


def extract_doc_reference(message: str) -> str | None:
    m = re.search(r"[「『\"](.+?)[」』\"]", message)
    return m.group(1) if m else None
