import json
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from backend.agent_api import QuestionRequest, ResearchRequest, ask, report
from backend.agent_lab import run_agent
from backend.risk import DEMO


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SNAPSHOT = json.loads((EXAMPLES / "contracts/market-snapshot.json").read_text(encoding="utf-8"))
FIRST = "Revenue for the quarter was USD 125 million."
SECOND = "Revenue for the quarter was USD 100 million."


def filing(text):
    return {"ticker": "AMD", "quarter": "2025-Q3", "published": "2025-11-04", "text": text}


def evaluate(holdings=DEMO, **options):
    fields = {"csv_text": holdings, "ticker": "AMD", "quarter": "2025-Q3", "through_date": "2025-11-04"}
    return report(ResearchRequest.model_validate(fields | options))


class ReportEvals(unittest.TestCase):
    def test_related_filing_and_weights(self):
        run = evaluate()
        self.assertIs(run["assessments"][0]["held"], True)
        evidence, exposure = [step["result"] for step in run["trace"]]
        self.assertEqual(evidence["documents"][0]["published"], "2025-11-04")
        self.assertEqual(exposure["direct_value_usd"], 12000)
        self.assertAlmostEqual(exposure["direct_share_of_industry_pct"], 12000 / 42000 * 100)

    def test_no_direct_holding_and_no_evidence_are_different(self):
        run = evaluate("ticker,quantity,currency\nNVDA,2,USD")
        self.assertIs(run["assessments"][0]["held"], False)
        self.assertEqual(run["trace"][1]["result"]["direct_share_of_industry_pct"], 0)
        self.assertEqual(evaluate(through_date="2025-11-03")["assessments"], [])

    def test_conflicting_values_retain_both_retrieved_locations(self):
        run = evaluate(filing=filing((EXAMPLES / "filing-conflict.txt").read_text(encoding="utf-8")),
                       contains="Revenue")
        docs = run["trace"][0]["result"]["documents"]
        self.assertEqual([d["line"] for d in docs], [2, 3])
        self.assertEqual(run["assessments"][0]["conflicting_revenue_sources"], [d["url"] for d in docs])

    def test_equivalent_units_and_comparison_period(self):
        for text in ["Revenue for the quarter was USD 0.125 billion.",
                     "Revenue in the comparison quarter was USD 100 million."]:
            with self.subTest(text=text):
                run = evaluate(filing=filing(FIRST + "\n" + text))
                self.assertEqual(run["assessments"][0]["conflicting_revenue_sources"], [])

    def test_missing_peer_keeps_direct_value_and_cash_at_par(self):
        holdings = "ticker,quantity,currency\nAMD,100,USD\nNVDA,200,USD\nCASH,1000,USD"
        run = evaluate(holdings, market_snapshot=SNAPSHOT)
        values = run["trace"][1]["result"]
        self.assertEqual(values["price_source"], SNAPSHOT["source"])
        self.assertEqual(values["missing_prices"], ["NVDA"])
        self.assertEqual(values["direct_value_usd"], 12000)
        self.assertIsNone(values["industry_scenario"]["loss_usd"])
        self.assertIsNone(values["industry_scenario"]["loss_pct_of_portfolio"])
        for field in ["industry_value_usd", "portfolio_total_usd", "direct_weight_pct", "direct_share_of_industry_pct"]:
            self.assertIsNone(values[field])
        complete = evaluate(holdings.replace("NVDA,200,USD\n", ""), market_snapshot=SNAPSHOT)["trace"][1]["result"]
        self.assertEqual((complete["portfolio_total_usd"], complete["direct_share_of_industry_pct"]), (13000, 100))

    def test_missing_outside_sector_only_blocks_portfolio_denominator(self):
        values = evaluate("ticker,quantity,currency\nAMD,2,USD\nJPM,1,USD",
                          market_snapshot=SNAPSHOT)["trace"][1]["result"]
        self.assertEqual(values["missing_prices"], ["JPM"])
        self.assertEqual(values["industry_value_usd"], 240)
        self.assertEqual(values["direct_share_of_industry_pct"], 100)
        self.assertIsNone(values["industry_weight_pct"])
        self.assertAlmostEqual(values["industry_scenario"]["loss_usd"], 19.2)
        self.assertIsNone(values["industry_scenario"]["loss_pct_of_portfolio"])

    def test_demo_stress_and_independent_repricing(self):
        scenario = evaluate()["trace"][1]["result"]["industry_scenario"]
        self.assertEqual((scenario["decline_pct"], scenario["loss_usd"], scenario["loss_pct_of_portfolio"]),
                         (8, 3360, 3.36))
        # AMD 2.5 @ $80, NVDA 1 @ $150 and $50 cash. Revalue both equities at 75%.
        quotes = [{"ticker": code, "close": price, "status": "available"}
                  for code, price in [("AMD", 80), ("NVDA", 150)]]
        values = evaluate("ticker,quantity,currency\nAMD,2.5,USD\nNVDA,1,USD\nCASH,50,USD",
                          market_snapshot=SNAPSHOT | {"quotes": quotes},
                          industry_decline_pct=25)["trace"][1]["result"]
        before, after = 400, 2.5 * 60 + 112.5 + 50
        self.assertEqual(values["portfolio_total_usd"], before)
        self.assertEqual(values["industry_scenario"]["loss_usd"], before - after)
        self.assertEqual(values["industry_scenario"]["loss_pct_of_portfolio"], (before - after) / before * 100)

    def test_stress_boundaries(self):
        no_shock = evaluate(industry_decline_pct=0, market_snapshot=SNAPSHOT)["trace"][1]["result"]
        self.assertEqual(no_shock["industry_scenario"]["loss_usd"], 0)
        self.assertIsNone(no_shock["industry_scenario"]["loss_pct_of_portfolio"])
        cash = "ticker,quantity,currency\nCASH,1000,USD"
        empty_sector = evaluate(cash, industry_decline_pct=100)["trace"][1]["result"]["industry_scenario"]
        self.assertEqual((empty_sector["loss_usd"], empty_sector["loss_pct_of_portfolio"]), (0, 0))
        self.assertIsNone(evaluate(cash, ticker="CASH")["trace"][1]["result"]["industry_scenario"])
        peer = evaluate("ticker,quantity,currency\nNVDA,2,USD", industry_decline_pct=100)["trace"][1]["result"]
        self.assertFalse(peer["held"])
        self.assertEqual(peer["industry_scenario"]["loss_pct_of_portfolio"], 100)

    def test_stress_input_and_scope(self):
        for invalid in [-1, 101, True, 1.5, "8"]:
            with self.subTest(decline=invalid), self.assertRaises(ValidationError):
                evaluate(industry_decline_pct=invalid)
        with self.assertRaises(ValidationError):
            QuestionRequest(scope="filings_only", question="Find a filing", industry_decline_pct=8)

    def test_live_route_withholds_overconfident_draft(self):
        def respond(messages):
            if messages[-1]["role"] == "tool":
                docs = json.loads(messages[-2]["content"])["documents"]
                quotes = ["FILING | " + " | ".join(doc[k] for k in ("ticker", "quarter", "published", "url", "excerpt"))
                          for doc in docs]
                return {"content": "\n".join(["This is a definitive answer.", *quotes])}
            calls = [("search_filings", {"ticker": "AMD", "through_date": "2025-11-04"}),
                     ("get_portfolio_exposure", {"ticker": "AMD"})]
            return {"tool_calls": [{"id": name, "type": "function", "function": {
                "name": name, "arguments": json.dumps(args)}} for name, args in calls]}

        def simulate(question, **context):
            return run_agent(question, respond, **context)

        for options in [{"filing": filing(FIRST + "\n" + SECOND)}, {"market_snapshot": SNAPSHOT}]:
            with self.subTest(keys=options.keys()), patch("backend.agent_api.model_config", return_value=("test", "test", "test")), patch(
                    "backend.agent_api.run_agent", simulate):
                run = ask(QuestionRequest(csv_text=DEMO, question="Report?", **options))
                self.assertEqual(run["status"], "needs_review")
                self.assertEqual(run["filing_citations"]["issues"], [])
                self.assertIsNone(run["answer"])
                self.assertEqual(len(run["trace"]), 2)
