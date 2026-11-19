"""Extract page text from a PDF while retaining page locations."""

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class PdfPage:
    page: int
    status: Literal["ok", "needs_review"]
    text: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PdfDocument:
    version: str
    pages: tuple[PdfPage, ...]


def parse_pdf(raw: bytes) -> PdfDocument:
    """Return a SHA-256 file version and one result per physical page."""
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")
        page_count = len(reader.pages)
    except PdfReadError as exc:
        raise ValueError("Could not read the PDF.") from exc

    if page_count == 0:
        raise ValueError("The PDF has no pages.")

    pages = []
    for page_number in range(1, page_count + 1):
        try:
            text = (reader.pages[page_number - 1].extract_text() or "").strip()
        except (PdfReadError, NotImplementedError):
            pages.append(PdfPage(page_number, "needs_review", reason="extraction_failed"))
            continue

        if text:
            pages.append(PdfPage(page_number, "ok", text=text))
        else:
            pages.append(PdfPage(page_number, "needs_review", reason="no_extractable_text"))

    return PdfDocument(hashlib.sha256(raw).hexdigest(), tuple(pages))
