from pathlib import Path

from app.parsers.base import ParsedDocument
from app.parsers.docx_parser import parse_docx
from app.parsers.pdf_parser import parse_pdf
from app.parsers.pptx_parser import parse_pptx
from app.parsers.xlsx_parser import parse_xlsx

PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".pptx": parse_pptx,
    ".xlsx": parse_xlsx,
}


def parse_file(path: Path) -> ParsedDocument:
    ext = path.suffix.lower()
    parser = PARSERS.get(ext)
    if not parser:
        raise ValueError(f"不支持的文件格式: {ext}")
    return parser(path)
