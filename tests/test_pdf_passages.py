import hashlib
from datetime import date
from io import BytesIO
from pathlib import Path
import unittest

from pypdf import PdfWriter
from pypdf.constants import UserAccessPermissions

from backend.filings.pdf import parse_pdf


SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples" / "filings" / "pdf-page-demo.pdf"
)


class PdfPassagesTests(unittest.TestCase):
    def test_text_and_image_pages_keep_their_page_numbers(self):
        raw = SAMPLE.read_bytes()
        result = parse_pdf(raw)

        self.assertEqual(result.version, hashlib.sha256(raw).hexdigest())
        self.assertEqual([page.page for page in result.pages], [1, 2])

        readable, scan = result.pages
        self.assertEqual(readable.status, "ok")
        self.assertIn("Quarterly revenue was USD 125 million.", readable.text)

        self.assertEqual(scan.status, "needs_review")
        self.assertIsNone(scan.text)
        self.assertEqual(scan.reason, "no_extractable_text")

    def test_only_readable_lines_become_citable_passages(self):
        document = parse_pdf(SAMPLE.read_bytes())

        first, second = document.passages(
            ticker="NVDA", quarter="2025-Q3", published=date(2025, 11, 12)
        )

        locator = f"#filing-{document.version}-P1"
        self.assertEqual(first, {
            "ticker": "NVDA",
            "quarter": "2025-Q3",
            "published": "2025-11-12",
            "excerpt": "FinSentinel - Synthetic Filing",
            "url": f"{locator}-S1",
            "source": "uploaded_pdf",
            "page": 1,
            "document_version": document.version,
        })
        self.assertEqual(second["excerpt"], "Quarterly revenue was USD 125 million.")
        self.assertEqual(second["url"], f"{locator}-S2")
        self.assertEqual(second["page"], 1)

    def test_copy_permitted_document_opens_without_a_password(self):
        raw = self._secured_sample("", UserAccessPermissions.EXTRACT)
        result = parse_pdf(raw)
        self.assertEqual([page.status for page in result.pages], ["ok", "needs_review"])
        self.assertIn("Quarterly revenue was USD 125 million.", result.pages[0].text)

    def test_document_requiring_a_password_is_rejected(self):
        raw = self._secured_sample("reader-test-password", UserAccessPermissions.EXTRACT)
        with self.assertRaisesRegex(ValueError, "password"):
            parse_pdf(raw)

    def test_document_disallowing_text_extraction_is_rejected(self):
        raw = self._secured_sample("", UserAccessPermissions.PRINT)
        with self.assertRaisesRegex(ValueError, "does not permit text extraction"):
            parse_pdf(raw)

    @staticmethod
    def _secured_sample(password, permissions):
        writer = PdfWriter(clone_from=BytesIO(SAMPLE.read_bytes()))
        writer.encrypt(password, owner_password="owner-test-password", permissions_flag=permissions)
        output = BytesIO()
        writer.write(output)
        return output.getvalue()
