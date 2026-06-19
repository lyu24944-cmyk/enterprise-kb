from pathlib import Path

import fitz

from app.parsers.base import ParsedBlock, ParsedDocument


def parse_pdf(path: Path) -> ParsedDocument:
    blocks: list[ParsedBlock] = []
    doc = fitz.open(path)
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text:
            blocks.append(ParsedBlock(text=text, page=i + 1))
    doc.close()
    return ParsedDocument(blocks=blocks, doc_type="pdf", category=_guess_category(path.name))


def _guess_category(filename: str) -> str:
    name = filename.lower()
    if any(k in name for k in ("合同", "contract", "协议")):
        return "contract"
    if any(k in name for k in ("手册", "制度", "policy", "员工")):
        return "policy"
    return "other"
