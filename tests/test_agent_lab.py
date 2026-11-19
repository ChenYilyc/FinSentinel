import json
import unittest

from backend.agent_lab import replay, run_agent
from backend.agent_tools import ExposureArgs, execute, get_portfolio_exposure


class AgentLessonTests(unittest.TestCase):
    def test_replay_tools_and_dates(self):
        trace = replay()["trace"]
        self.assertEqual(trace[0]["result"]["documents"][0]["published"], "2025-11-04")
        result = trace[1]["result"]
        self.assertEqual((result["direct_weight_pct"], result["industry_weight_pct"]), (12, 42))
        self.assertEqual(result["other_industry_tickers"], ["NVDA"])
        self.assertEqual(result["other_industry_weight_pct"], 30)
        self.assertEqual(result["valuation_date"], "2026-10-30")

    def test_quarter_end_does_not_imply_publication(self):
        args = {"ticker": "AMD", "through_date": "2025-10-31", "quarter": "2025-Q3"}
        self.assertEqual(execute("search_filings", json.dumps(args))["status"], "no_matching_evidence")

    def test_industry_exposure_when_company_absent(self):
        result = get_portfolio_exposure(ExposureArgs(ticker="AMD"), "ticker,quantity,currency\nNVDA,1,USD")
        self.assertEqual((result["direct_weight_pct"], result["industry_weight_pct"]), (0, 100))

    def test_single_company_is_the_entire_industry(self):
        result = get_portfolio_exposure(ExposureArgs(ticker="AMD"), "ticker,quantity,currency\nAMD,1,USD")
        self.assertEqual(result["industry_weight_pct"], 100)
        self.assertEqual(result["direct_weight_pct"], 100)
        self.assertEqual(result["other_industry_weight_pct"], 0)
        self.assertEqual(result["other_industry_tickers"], [])
        self.assertIn("Semiconductors total: 100.00% of the portfolio, including AMD at 100.00%",
                      result["exposure_statement"])

    def test_execution_boundary(self):
        self.assertEqual(execute("other", "{}")["status"], "unknown_tool")
        self.assertEqual(execute("get_portfolio_exposure", '{"ticker":"AMD","portfolio_id":"other"}')["status"],
                         "invalid_arguments")
        self.assertEqual(execute("get_portfolio_exposure", "{")["status"], "invalid_arguments")
        self.assertEqual(execute("get_portfolio_exposure", '{"ticker":"XYZ"}')["status"], "unsupported_ticker")

    def test_loop_round_trip(self):
        def respond(history):
            if history[-1]["role"] == "tool":
                self.assertEqual(history[-1]["tool_call_id"], "call-1")
                self.assertEqual(json.loads(history[-1]["content"])["direct_weight_pct"], 12)
                return {"content": "AMD direct weight is 12%."}
            return {"tool_calls": [{"id": "call-1", "type": "function", "function": {
                "name": "get_portfolio_exposure", "arguments": '{"ticker":"AMD"}'}}]}
        run = run_agent("How much AMD do I hold?", respond)
        self.assertEqual(run["status"], "draft")
        self.assertEqual(len(run["trace"]), 1)

    def test_loop_stops_on_repeated_calls(self):
        def repeat(history):
            return {"tool_calls": [{"id": str(len(history)), "type": "function", "function": {
                "name": "get_portfolio_exposure", "arguments": '{"ticker":"AMD"}'}}]}
        run = run_agent("Repeated requests", repeat)
        self.assertEqual((run["status"], len(run["trace"])), ("budget_exhausted", 4))
