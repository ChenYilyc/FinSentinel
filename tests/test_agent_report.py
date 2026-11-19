import json
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.agent_api import QuestionRequest, ResearchRequest, ask, report
from backend.risk import DEMO


def research(holdings=DEMO, cutoff="2026-10-30", ticker="AMD"):
    return report(ResearchRequest(csv_text=holdings, ticker=ticker, quarter="2025-Q3", through_date=cutoff))


class AgentReportTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}))

    def test_report_contract(self):
        evidence, exposure = research()["trace"]
        self.assertEqual(evidence["result"]["documents"][0]["published"], "2025-11-04")
        values = exposure["result"]
        self.assertEqual((values["direct_weight_pct"], values["industry_weight_pct"]), (12, 42))
        self.assertAlmostEqual(values["direct_share_of_industry_pct"], 12000 / 42000 * 100)
        self.assertEqual(values["valuation_date"], "2026-10-30")

    def test_current_csv_and_independent_dates(self):
        evidence, exposure = research("ticker,quantity,currency\nAMD,1,USD", "2025-10-31")["trace"]
        self.assertEqual(evidence["result"]["status"], "no_matching_evidence")
        self.assertEqual(exposure["result"]["direct_share_of_industry_pct"], 100)
        self.assertEqual(exposure["result"]["valuation_date"], "2026-10-30")

    def test_zero_and_undefined_are_distinct(self):
        for asset, expected in (("NVDA", 0), ("JPM", None)):
            with self.subTest(asset=asset):
                values = research("ticker,quantity,currency\n" + asset + ",1,USD")["trace"][1]["result"]
                self.assertEqual(values["direct_share_of_industry_pct"], expected)

    def test_invalid_csv_rejected_before_any_model_request(self):
        with patch("backend.agent_api.run_agent") as model, self.assertRaises(HTTPException) as failure:
            ask(QuestionRequest(csv_text="invalid", question="Holdings?"))
        self.assertEqual(failure.exception.status_code, 422)
        model.assert_not_called()

    def test_live_configuration_error(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), self.assertRaises(HTTPException) as failure:
            ask(QuestionRequest(csv_text=DEMO, question="Holdings?"))
        self.assertEqual(failure.exception.status_code, 503)

    def test_live_dispatch_uses_request_portfolio(self):
        from backend.agent_lab import run_agent
        def simulated_model(messages):
            if messages[-1]["role"] == "tool":
                self.assertEqual(json.loads(messages[-1]["content"])["direct_share_of_industry_pct"], 100)
                return {"content": "AMD accounts for all industry holdings."}
            return {"tool_calls": [{"id": "call1", "type": "function", "function": {
                "name": "get_portfolio_exposure", "arguments": '{"ticker":"AMD"}'}}]}
        def simulated_run(question, *, holdings, filing):
            return run_agent(question, simulated_model, holdings=holdings, filing=filing)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("backend.agent_api.run_agent", simulated_run):
            result = ask(QuestionRequest(csv_text="ticker,quantity,currency\nAMD,1,USD", question="Industry share?"))
        self.assertEqual(result["status"], "draft")
        self.assertEqual([step["tool"] for step in result["trace"]], ["get_portfolio_exposure"])

    def test_provider_failure_is_reported(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("backend.agent_api.run_agent", side_effect=RuntimeError), self.assertRaises(HTTPException) as failure:
            ask(QuestionRequest(csv_text=DEMO, question="Holdings?"))
        self.assertEqual(failure.exception.status_code, 502)
