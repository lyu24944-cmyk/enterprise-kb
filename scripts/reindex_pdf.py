"""删除并重新入库员工手册 PDF（应用新分块策略后运行）。"""
from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPTS))

PDF_NAME = "员工手册2024.pdf"


async def main() -> None:
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.models.database import Document
    from app.services.db_service import SessionLocal, delete_document, ingest_document, init_db
    from seed_demo_docs import create_handbook_pdf

    await init_db()
    demo_pdf = ROOT / "data" / "demo" / PDF_NAME
    create_handbook_pdf(demo_pdf)

    async with SessionLocal() as session:
        result = await session.execute(select(Document).where(Document.filename == PDF_NAME))
        old = result.scalar_one_or_none()
        if old:
            await delete_document(session, old.id)
            print(f"已删除旧索引: {PDF_NAME}")

        settings = get_settings()
        target = settings.upload_path / f"{uuid.uuid4().hex}_{PDF_NAME}"
        shutil.copy(demo_pdf, target)
        doc = await ingest_document(session, target, PDF_NAME)
        print(f"重新入库: {doc.filename} -> {doc.chunk_count} chunks")


if __name__ == "__main__":
    asyncio.run(main())
