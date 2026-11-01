import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    source: str
    page: int | None = None


def load_document(filename: str, content: bytes) -> list[tuple[str, int | None]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        from io import BytesIO

        pages = PdfReader(BytesIO(content)).pages
        return [
            (text, page_number)
            for page_number, page in enumerate(pages, start=1)
            if (text := page.extract_text())
        ]
    if suffix in {".txt", ".md"}:
        return [(content.decode("utf-8-sig"), None)]
    raise ValueError("Only PDF, TXT, and Markdown documents are supported.")


def chunk_text(
    text: str, source: str, page: int | None, size: int, overlap: int
) -> list[DocumentChunk]:
    text = re.sub(r"(?m)^\s*#{1,6}\s+.*$", " ", text)
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    chunks: list[DocumentChunk] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(DocumentChunk(text=piece, source=source, page=page))
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks
