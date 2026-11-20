import hashlib
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.agent_api import ResearchRequest, report
from backend.agent_lab import run_agent
from backend.pdf_evidence import PdfFiling


ROOT = Path(__file__).resolve().parents[1] / "examples" / "contracts"


def sample():
    return json.loads((ROOT / "filing-pages-demo.json").read_text("utf-8"))


class PdfEvidenceTests(unittest.TestCase):
    def test_report_uses_pdf_cutoff_and_original_version(self):
        fields = dict(csv_text="ticker,quantity,currency\nNVDA,1,USD", ticker="NVDA", quarter="2025-Q3",
                      through_date="2025-11-12", contains="125", filing=sample())
        doc, = report(ResearchRequest(**fields))["trace"][0]["result"]["documents"]
        version = hashlib.sha256((ROOT / "filing-pages-demo.pdf").read_bytes()).hexdigest()
        self.assertEqual(doc["document_version"], version)
        self.assertEqual((doc["page"], doc["url"]), (2, f"#filing-{version}-P2-S1"))
        for override in [{"through_date": "2025-11-11"}, {"ticker": "AMD"}]:
            result = report(ResearchRequest(**(fields | override)))["trace"][0]["result"]
            self.assertEqual(result["status"], "no_matching_evidence")

    def test_bundle_rejects_inconsistent_coordinates_and_metadata(self):
        for change in [{"page": 1}, {"page": True}, {"url": "https://example.org/"}, {"excerpt": "two\nlines"},
                       {"document_version": "0" * 64}, {"quarter": "2025-Q2"}, {"published": "2025-02-30"}]:
            bundle = sample()
            bundle["documents"][1].update(change)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                PdfFiling(**bundle)
        bundle = sample()
        bundle["documents"].append(bundle["documents"][0])
        with self.assertRaises(ValidationError):
            PdfFiling(**bundle)

    def test_live_checks_exact_page_and_passage_against_retrieval(self):
        bundle = sample()
        doc = bundle["documents"][1]
        for url, outcome in [(doc["url"], "draft"), (doc["url"].replace("P2", "P1"), "needs_review"),
                             (bundle["documents"][2]["url"], "needs_review")]:
            replies = iter([{"tool_calls": [{"id": "find", "type": "function", "function": {
                "name": "search_filings", "arguments": json.dumps({"ticker": "NVDA", "through_date": "2025-11-12",
                                                                  "contains": "125"})}}]},
                {"content": f"Reported revenue.\nFILING | NVDA | 2025-Q3 | 2025-11-12 | {url} | {doc['excerpt']}"}])
            with self.subTest(url=url):
                run = run_agent("What revenue is on page 2?", lambda _: next(replies), filing=PdfFiling(**bundle),
                                scope="filings_only", holdings=None)
                self.assertEqual(run["receipt"]["outcome"], outcome)
                if outcome == "draft":
                    self.assertEqual(run["filing_citations"]["matched"], [doc])
                else:
                    self.assertIsNone(run["answer"])
                    self.assertEqual(run["filing_citations"]["issues"], ["source_not_retrieved"])
