"""Extract page text from a PDF while retaining page locations."""

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Literal

from pypdf import PasswordType, PdfReader
from pypdf.constants import UserAccessPermissions
from pypdf.errors import DependencyError, PdfReadError


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

    def passages(
        self, *, ticker: str, quarter: str, published: date
    ) -> Iterator[dict[str, str | int]]:
        """Yield citable single-line excerpts in extracted page order."""
        published_on = published.isoformat()
        for page in self.pages:
            if page.status != "ok" or page.text is None:
                continue

            lines = (line.strip() for line in page.text.splitlines())
            excerpts = (line for line in lines if line)
            for number, excerpt in enumerate(excerpts, start=1):
                yield {
                    "ticker": ticker,
                    "quarter": quarter,
                    "published": published_on,
                    "excerpt": excerpt,
                    "url": f"#filing-{self.version}-P{page.page}-S{number}",
                    "source": "uploaded_pdf",
                    "page": page.page,
                    "document_version": self.version,
                }


def parse_pdf(raw: bytes) -> PdfDocument:
    """Return a SHA-256 file version and one result per physical page."""
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            if reader.decrypt("") == PasswordType.NOT_DECRYPTED:
                raise ValueError("This PDF requires a password.")
            permissions = reader.user_access_permissions
            if reader.are_permissions_valid is False or not (
                permissions and permissions & UserAccessPermissions.EXTRACT
            ):
                raise ValueError("This PDF does not permit text extraction.")
        page_count = len(reader.pages)
    except DependencyError as exc:
        raise ValueError("This PDF uses unsupported encryption.") from exc
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
