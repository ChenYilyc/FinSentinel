import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.agent_api import QuestionRequest, ResearchRequest, ask, report
from backend.agent_lab import run_agent
from backend.filing_text import FilingText
from backend.risk import DEMO

SAMPLE = (Path(__file__).resolve().parents[1] / "examples" / "filing-demo.txt").read_text("utf-8")


def upload(text=SAMPLE):
    return FilingText(ticker="NVDA", quarter="2025-Q3", published="2025-11-12", text=text)


def search(filing=None, **changes):
    params = dict(csv_text=DEMO, ticker="NVDA", quarter="2025-Q3", through_date="2025-11-12",
                  contains="REVENUE", filing=filing)
    params.update(changes)
    return report(ResearchRequest(**params))["trace"][0]["result"]


class FilingTextTests(unittest.TestCase):
    def test_local_reference_reaches_exact_physical_line(self):
        rows = search(upload())["documents"]
        self.assertEqual([row["line"] for row in rows], [3, 4])
        for row in rows:
            self.assertEqual(row["excerpt"], SAMPLE.splitlines()[row["line"] - 1])
            self.assertTrue(row["url"].endswith(f"-L{row['line']}"))

    def test_versions_and_normalized_newlines(self):
        base = search(upload())["documents"][0]["url"]
        crlf = "\ufeff" + SAMPLE.replace("\n", "\r\n")
        self.assertEqual(search(upload(crlf))["documents"][0]["url"], base)
        self.assertNotEqual(search(upload(SAMPLE.replace("125", "126")))["documents"][0]["url"], base)

    def test_scope_cutoff_and_no_fallback(self):
        for changes in [{"through_date": "2025-11-11"}, {"ticker": "AMD"}, {"quarter": "2025-Q2"},
                        {"contains": "unlisted"}]:
            with self.subTest(changes=changes):
                self.assertEqual(search(upload(), **changes)["status"], "no_matching_evidence")
        self.assertEqual(search()["documents"], [])
        restored = search(ticker="AMD")["documents"][0]
        self.assertTrue(restored["url"].startswith("https://ir.amd.com/"))

    def test_limits_and_utf8(self):
        for value in ["\t\n", "A\x00B", "A\u2028B", "A" * 1201, "\n" * 1000 + "x",
                      ("中" * 1000 + "\n") * 17]:
            with self.assertRaises(ValidationError):
                upload(value)
        rows = search(upload("\n".join(f"Revenue {i}" for i in range(8))))
        self.assertEqual((rows["total_matches"], len(rows["documents"])), (8, 5))

    def test_live_citation_must_reference_returned_line(self):
        def respond(messages):
            if messages[-1]["role"] == "user":
                return {"tool_calls": [{"id": "q", "type": "function", "function": {
                    "name": "search_filings", "arguments": json.dumps({
                        "ticker": "NVDA", "through_date": "2025-11-12", "contains": "USD 125"})}}]}
            docs = json.loads(messages[-1]["content"])["documents"]
            self.assertEqual(len(docs), 1)
            d = docs[0]
            citation = "FILING | " + " | ".join(d[k] for k in ("ticker", "quarter", "published", "url", "excerpt"))
            return {"content": citation + "\n" + citation.replace("-L3", "-L4")}

        def simulated_run(question, **context):
            return run_agent(question, respond, **context)

        with patch("backend.agent_api.model_config", return_value=("test", "test", True)), patch(
            "backend.agent_api.run_agent", simulated_run
        ):
            result = ask(QuestionRequest(csv_text=DEMO, question="Find the reported revenue", filing=upload()))
        self.assertEqual(result["filing_citations"]["matched"][0]["line"], 3)
        self.assertEqual(result["filing_citations"]["issues"], ["source_not_retrieved"])
