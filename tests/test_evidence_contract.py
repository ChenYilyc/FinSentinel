import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.agent_tools import FilingArgs, search_filings
from backend.filing_citations import check_filing_quotes
from backend.filing_text import FilingText
from backend.market_contract import MarketSnapshot


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def example(name):
    return json.loads((EXAMPLES / "contracts" / name).read_text(encoding="utf-8"))


class EvidenceContractTests(unittest.TestCase):
    def test_text_producer_and_citation_consumer_share_fixture(self):
        filing = FilingText(ticker="NVDA", quarter="2025-Q3", published="2025-11-12",
                            text=(EXAMPLES / "filing-demo.txt").read_text(encoding="utf-8"))
        args = FilingArgs(ticker="NVDA", quarter="2025-Q3", through_date="2025-11-12", contains="125")
        expected = example("filing-evidence.json")
        result = search_filings(args, filing)
        self.assertEqual(result, expected)
        doc = expected["documents"][0]
        line = "FILING | " + " | ".join(doc[k] for k in ("ticker", "quarter", "published", "url", "excerpt"))
        _, checked = check_filing_quotes(line, [{"tool": "search_filings", "result": result}])
        self.assertEqual(checked, {"matched": [doc], "issues": []})

    def test_missing_quote_is_explicit(self):
        snapshot = MarketSnapshot.model_validate_json(json.dumps(example("market-snapshot.json")))
        prices = {row.ticker: row.close for row in snapshot.quotes}
        self.assertEqual(prices, {"AMD": 120, "NVDA": None})

    def test_status_and_price_agree(self):
        for status, price in [("missing", 0), ("missing", 150), ("available", None),
                              ("available", 0), ("available", -1), ("available", True)]:
            with self.subTest(status=status, price=price), self.assertRaises(ValidationError):
                snapshot = example("market-snapshot.json")
                snapshot["quotes"][1].update(status=status, close=price)
                MarketSnapshot.model_validate_json(json.dumps(snapshot))

    def test_snapshot_is_unambiguous(self):
        for change in [{"as_of": "2026-10-30T20:15:00"}, {"currency": "EUR"},
                       {"quotes": [{"ticker": "AMD", "status": "missing", "close": None}] * 2}]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                MarketSnapshot.model_validate_json(json.dumps(example("market-snapshot.json") | change))
