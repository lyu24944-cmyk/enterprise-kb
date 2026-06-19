from app.parsers.base import ParsedBlock, ParsedDocument


def chunk_document(
    parsed: ParsedDocument,
    doc_id: str,
    filename: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[dict]:
    """将解析块切分为带元数据的 chunk 列表。"""
    chunks: list[dict] = []
    for block in parsed.blocks:
        if len(block.text) <= chunk_size:
            chunks.append(_make_chunk(block, block.text, doc_id, filename, len(chunks)))
            continue
        start = 0
        while start < len(block.text):
            end = start + chunk_size
            piece = block.text[start:end]
            chunks.append(_make_chunk(block, piece, doc_id, filename, len(chunks)))
            if end >= len(block.text):
                break
            start = end - chunk_overlap
    return chunks


def _make_chunk(
    block: ParsedBlock,
    text: str,
    doc_id: str,
    filename: str,
    index: int,
) -> dict:
    return {
        "text": text.strip(),
        "metadata": {
            "doc_id": doc_id,
            "filename": filename,
            "page": block.page,
            "section": block.section,
            "chunk_index": index,
            **block.metadata,
        },
    }
