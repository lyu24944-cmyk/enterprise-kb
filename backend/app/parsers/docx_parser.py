from pathlib import Path

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.base import ParsedBlock, ParsedDocument
from app.parsers.pdf_parser import _guess_category


def parse_docx(path: Path) -> ParsedDocument:
    doc = DocxDocument(path)
    blocks: list[ParsedBlock] = []
    current_section = "正文"

    for element in doc.element.body:
        tag = element.tag.split("}")[-1]
        if tag == "p":
            para = Paragraph(element, doc)
            text = para.text.strip()
            if not text:
                continue
            style = para.style.name if para.style else ""
            if style.startswith("Heading"):
                current_section = text
            blocks.append(ParsedBlock(text=text, section=current_section))
        elif tag == "tbl":
            table = Table(element, doc)
            rows = []
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                rows.append(" | ".join(cells))
            if rows:
                md = "\n".join(rows)
                blocks.append(ParsedBlock(text=md, section=current_section, metadata={"type": "table"}))

    return ParsedDocument(blocks=blocks, doc_type="docx", category=_guess_category(path.name))
