import io
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from urllib.error import URLError

from fastapi import HTTPException
from pydantic import ValidationError

from backend import agent_api as api
from backend.agent_tools import execute
from backend.run_checkpoints import CheckpointBusy, CheckpointGone, Checkpoints


def call(name, args, call_id):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


SEARCH = call("search_filings", {"ticker": "AMD", "through_date": "2025-11-04", "quarter": "2025-Q3"}, "search-1")
HOLDINGS = call("get_portfolio_exposure", {"ticker": "AMD"}, "holdings-1")


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.store = Checkpoints()
        self.enterContext(patch.object(api, "checkpoints", self.store))
        self.config = ("deepseek", "fixture-model", "test-key")
        self.enterContext(patch.object(api, "model_config", return_value=self.config))
        self.model_config = self.enterContext(patch("backend.agent_lab.model_config", return_value=self.config))
        self.requests = []
        self.dispatch = self.enterContext(patch("backend.agent_lab.execute", wraps=execute))

    def transport(self, replies):
        sequence = iter(replies)

        def send(req, **kwargs):
            self.requests.append(json.loads(req.data))
            message = next(sequence)
            if isinstance(message, Exception):
                raise message
            return io.BytesIO(json.dumps({"choices": [{"message": message}]}).encode())

        self.enterContext(patch("backend.agent_lab.urlopen", side_effect=send))

    def interrupt(self):
        return api.ask(api.QuestionRequest(scope="filings_only", question="Find the AMD Q3 filing."))

    def test_resume_reuses_history_and_receipt_and_is_idempotent(self):
        self.transport([{"tool_calls": [SEARCH]}, URLError("offline"), {"content": "Done"}])
        partial = self.interrupt()
        token = partial["resume_token"]
        self.assertNotIn(token, json.dumps(partial["receipt"]))
        request = api.ResumeRequest(token=token)
        done = api.resume(request)
        self.assertEqual(self.requests[2], self.requests[1])
        self.assertEqual(self.requests[2]["messages"][-1]["tool_call_id"], "search-1")
        self.assertEqual(done["receipt"]["run_id"], partial["receipt"]["run_id"])
        self.assertEqual((done["receipt"]["resumptions"], done["receipt"]["model_rounds"]), (1, 3))
        self.assertEqual(done["trace"], partial["trace"])
        self.assertEqual(done["receipt"]["outcome"], "needs_review")
        self.assertIsNone(done["answer"])
        self.assertEqual(done["filing_citations"]["issues"], ["missing_quote"])
        self.assertEqual(api.resume(request), done)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(self.dispatch.call_count, 1)

    def test_resume_rechecks_tool_scope(self):
        self.transport([{"tool_calls": [SEARCH]}, URLError("offline"), {"tool_calls": [HOLDINGS]}, {"content": "Done"}])
        partial = self.interrupt()
        done = api.resume(api.ResumeRequest(token=partial["resume_token"]))
        self.assertEqual(done["trace"][-1]["result"], {"status": "permission_denied"})
        self.assertEqual(done["receipt"]["outcome"], "needs_review")
        self.assertEqual(self.requests[-1]["tools"], self.requests[0]["tools"])
        self.assertEqual(len(partial["trace"]), 1)

    def test_resumed_holdings_tool_uses_original_scenario(self):
        self.transport([{"tool_calls": [SEARCH]}, URLError("offline"), {"tool_calls": [HOLDINGS]}, {"content": "Done"}])
        partial = api.ask(api.QuestionRequest(csv_text="ticker,quantity,currency\nAMD,1,USD\nCASH,80,USD",
                          question="Assess this industry scenario.", industry_decline_pct=25,
                          market_snapshot={"source": "fixture", "trading_date": "2026-10-30",
                                           "as_of": "2026-10-30T20:15:00Z", "currency": "USD",
                                           "quotes": [{"ticker": "AMD", "status": "available", "close": 80}]}))
        done = api.resume(api.ResumeRequest(token=partial["resume_token"]))
        result = done["trace"][-1]["result"]
        self.assertEqual(result["industry_scenario"],
                         {"industry": result["industry"], "decline_pct": 25, "loss_usd": 20,
                          "loss_pct_of_portfolio": 12.5})

    def test_repeated_disconnects_use_original_round_budget(self):
        self.transport([{"tool_calls": [SEARCH]}] + [URLError("offline")] * 3)
        first = self.interrupt()
        first_request = api.ResumeRequest(token=first["resume_token"])
        second = api.resume(first_request)
        self.assertNotEqual(first["resume_token"], second["resume_token"])
        self.assertEqual(api.resume(first_request), second)
        end = api.resume(api.ResumeRequest(token=second["resume_token"]))
        self.assertEqual(end["status"], "budget_exhausted")
        self.assertEqual((end["receipt"]["model_rounds"], end["receipt"]["resumptions"]), (4, 2))
        self.assertNotIn("resume_token", end)

    def test_six_tool_limit_includes_before_interruption(self):
        calls = [call("search_filings", {"ticker": "AMD", "through_date": "2025-11-04"}, str(i)) for i in range(5)]
        self.transport([{"tool_calls": calls}, URLError("offline"), {"tool_calls": [HOLDINGS, SEARCH]}])
        done = api.resume(api.ResumeRequest(token=self.interrupt()["resume_token"]))
        self.assertEqual(done["status"], "budget_exhausted")
        self.assertEqual(self.dispatch.call_count, 5)

    def test_model_change_and_client_overrides(self):
        from backend.agent_tools import FILINGS
        quote = " | ".join(FILINGS[1][key] for key in ("ticker", "quarter", "published", "url", "excerpt"))
        self.transport([{"tool_calls": [SEARCH]}, URLError("offline"), {"content": "Reported revenue.\nFILING | " + quote}])
        token = self.interrupt()["resume_token"]
        with self.assertRaises(ValidationError):
            api.ResumeRequest(token=token, scope="filings_and_holdings")
        self.model_config.return_value = ("openai", "another-model", "another-test-key")
        with self.assertRaises(HTTPException) as err:
            api.resume(api.ResumeRequest(token=token))
        self.assertEqual(err.exception.status_code, 409)
        self.assertEqual(len(self.requests), 2)
        self.model_config.return_value = self.config
        self.assertEqual(api.resume(api.ResumeRequest(token=token))["status"], "draft")

    def test_duplicate_in_flight_and_expiration(self):
        token = self.store.save(object())
        entered, release = Event(), Event()

        def slow(_):
            entered.set()
            if not release.wait(3):
                raise TimeoutError()
            return {"status": "done"}

        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.store.resume, token, slow)
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(CheckpointBusy):
                    self.store.resume(token, slow)
            finally:
                release.set()
            self.assertEqual(first.result(), {"status": "done"})
        with patch("backend.run_checkpoints.monotonic", return_value=float("inf")):
            with self.assertRaises(CheckpointGone):
                self.store.resume(token, slow)
