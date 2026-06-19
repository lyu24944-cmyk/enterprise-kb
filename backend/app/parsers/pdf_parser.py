import re
from pathlib import Path

import fitz

from app.parsers.base import ParsedBlock, ParsedDocument

_CHAPTER_RE = re.compile(r"(第[一二三四五六七八九十百千\d]+章[^\n]*)")
_SECTION_RE = re.compile(r"(\d+\.\d+[^\n]*)")


def parse_pdf(path: Path) -> ParsedDocument:
    blocks: list[ParsedBlock] = []
    doc = fitz.open(path)
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if not text:
            continue
        blocks.extend(_split_page(text, page=i + 1))
    doc.close()
    return ParsedDocument(blocks=blocks, doc_type="pdf", category=_guess_category(path.name))


def _split_page(text: str, page: int) -> list[ParsedBlock]:
    """按章节标题、小节、段落拆分单页，避免整页变成一个块。"""
    blocks: list[ParsedBlock] = []
    current_section = f"第{page}页"

    parts = _CHAPTER_RE.split(text)
    if len(parts) > 1:
        for j in range(0, len(parts), 2):
            heading = parts[j].strip()
            body = parts[j + 1].strip() if j + 1 < len(parts) else ""
            if heading:
                current_section = heading
                if len(heading) > 20:
                    blocks.append(ParsedBlock(text=heading, page=page, section=current_section))
            if body:
                blocks.extend(_split_by_paragraphs(body, page, current_section))
        return blocks or [ParsedBlock(text=text, page=page, section=current_section)]

    return _split_by_paragraphs(text, page, current_section)


def _split_by_paragraphs(text: str, page: int, section: str) -> list[ParsedBlock]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}|\n(?=\d+\.\d+)", text) if p.strip()]
    if not paragraphs:
        return [ParsedBlock(text=text, page=page, section=section)]

    blocks: list[ParsedBlock] = []
    buf: list[str] = []
    buf_len = 0
    max_para_group = 400

    for para in paragraphs:
        sec_match = _SECTION_RE.match(para)
        sec = sec_match.group(1) if sec_match else section

        if buf_len + len(para) > max_para_group and buf:
            blocks.append(ParsedBlock(text="\n".join(buf), page=page, section=section))
            buf, buf_len = [], 0

        if sec_match and len(para) < 80:
            section = sec[:40]
        buf.append(para)
        buf_len += len(para)

    if buf:
        blocks.append(ParsedBlock(text="\n".join(buf), page=page, section=section))
    return blocks


def _guess_category(filename: str) -> str:
    name = filename.lower()
    if any(k in name for k in ("合同", "contract", "协议")):
        return "contract"
    if any(k in name for k in ("手册", "制度", "policy", "员工")):
        return "policy"
    return "other"
