import io
import json
import unittest
from unittest.mock import patch

from backend.agent_api import QuestionRequest, ask
from backend.agent_lab import run_agent
from backend.risk import DEMO


URL = "https://ir.amd.com/news-events/press-releases/detail/1265/amd-reports-third-quarter-2025-financial-results"
QUOTE = "Third quarter revenue was a record $9.2 billion"
LINE = f"FILING | AMD | 2025-Q3 | 2025-11-04 | {URL} | {QUOTE}"


def search(cutoff):
    return {"tool_calls": [{"id": "filing-1", "type": "function", "function": {
        "name": "search_filings", "arguments": json.dumps({
            "ticker": "AMD", "quarter": "2025-Q3", "through_date": cutoff})}}]}


def simulate(content, cutoff="2025-11-04"):
    messages = iter([search(cutoff), {"content": content}])
    return run_agent("AMD Q3 revenue?", lambda _: next(messages))


class FilingCitationTests(unittest.TestCase):
    def test_live_api_quote_round_trip(self):
        responses = [search("2025-11-04"), {"content": "Revenue was $9.2 billion.\n" + LINE}]
        def send(request, **kwargs):
            if len(responses) == 1:
                tool_message = json.loads(request.data)["messages"][-1]
                self.assertEqual(tool_message["tool_call_id"], "filing-1")
                self.assertEqual(json.loads(tool_message["content"])["documents"][0]["excerpt"], QUOTE)
            return io.BytesIO(json.dumps({"choices": [{"message": responses.pop(0)}]}).encode())
        config = ("deepseek", "test-model", "test-only")
        with patch("backend.agent_api.model_config", return_value=config), patch(
            "backend.agent_lab.model_config", return_value=config
        ), patch("backend.agent_lab.urlopen", side_effect=send):
            result = ask(QuestionRequest(csv_text=DEMO, question="AMD Q3 revenue?"))
        self.assertEqual((result["mode"], result["provider"], result["model"]), ("live", *config[:2]))
        self.assertEqual(result["answer"], "Revenue was $9.2 billion.")
        self.assertEqual(result["receipt"]["outcome"], "draft")
        self.assertEqual(result["filing_citations"]["matched"][0]["url"], URL)
        self.assertEqual(result["filing_citations"]["issues"], [])
        self.assertNotIn(config[2], str(result))

    def test_tampered_fields(self):
        for old, new, issue in [
            ("$9.2", "$92", "quote_mismatch"),
            ("billion", "million", "quote_mismatch"),
            ("2025-Q3", "2025-Q2", "source_not_retrieved"),
            ("2025-11-04", "2025-11-03", "source_not_retrieved"),
            (URL, "https://example.org", "source_not_retrieved"),
        ]:
            with self.subTest(new=new):
                self.assertEqual(simulate(LINE.replace(old, new))["filing_citations"],
                                 {"matched": [], "issues": [issue]})

    def test_release_after_cutoff(self):
        result = simulate(LINE, cutoff="2025-11-03")
        self.assertEqual(result["filing_citations"], {"matched": [], "issues": ["source_not_retrieved"]})

    def test_missing_quote_and_partial_success(self):
        self.assertEqual(simulate("Here is the revenue.")["filing_citations"]["issues"], ["missing_quote"])
        result = simulate(LINE + "\nFILING | AMD")["filing_citations"]
        self.assertEqual(result["issues"], ["invalid_format"])
        self.assertEqual(len(result["matched"]), 1)

    def test_no_retrieval(self):
        for content, issues in [(LINE, ["source_not_retrieved"]), ("I need more information.", [])]:
            with self.subTest(issues=issues):
                result = run_agent("Question", lambda _: {"content": content})
                self.assertEqual(result["filing_citations"], {"matched": [], "issues": issues})

    def test_exact_quote_only_stays_visible_as_matched_evidence(self):
        result = simulate(LINE)
        self.assertEqual(result["status"], "draft")
        self.assertEqual(result["filing_citations"]["matched"][0]["excerpt"], QUOTE)

    def test_citation_failure_withholds_text_and_preserves_tool_evidence(self):
        for line, issue in [(LINE.replace("$9.2", "$92"), "quote_mismatch"),
                            (LINE.replace("2025-Q3", "2025-Q2"), "source_not_retrieved"),
                            ("FILING | AMD", "invalid_format"), ("", "missing_quote")]:
            with self.subTest(issue=issue):
                result = simulate("Revenue was $92 billion.\n" + line)
                self.assertEqual(result["status"], "needs_review")
                self.assertEqual(result["receipt"]["outcome"], "needs_review")
                self.assertIsNone(result["answer"])
                self.assertEqual(result["filing_citations"]["issues"], [issue])
                self.assertEqual(result["trace"][0]["result"]["documents"][0]["excerpt"], QUOTE)

    def test_one_valid_quote_cannot_clear_a_failed_quote(self):
        result = simulate("Review these figures.\n" + LINE + "\n" + LINE.replace("$9.2", "$92"))
        self.assertIsNone(result["answer"])
        self.assertEqual(result["filing_citations"]["matched"][0]["url"], URL)
        self.assertEqual(result["filing_citations"]["issues"], ["quote_mismatch"])

    def test_empty_search_allows_explicit_gap_but_withholds_unretrieved_citation(self):
        gap = simulate("No matching filing was found by this date.", cutoff="2025-11-03")
        self.assertEqual(gap["status"], "draft")
        cited = simulate("Revenue was $9.2 billion.\n" + LINE, cutoff="2025-11-03")
        self.assertEqual(cited["status"], "needs_review")
        self.assertIsNone(cited["answer"])
