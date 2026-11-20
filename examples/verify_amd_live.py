"""Run the fixed AMD acceptance case once with the configured model provider."""
import json
import sys
from pathlib import Path

from backend.agent_lab import run_agent


QUESTION = (
    "What revenue did AMD report for Q3 2025? Cite its filing published November 4, 2025. "
    "Using the demo valuation snapshot, list my holdings in AMD's industry. "
    "If the whole industry falls 8% and other prices stay fixed, what is the industry value, "
    "USD loss and loss as a percentage of the portfolio?"
)
SOURCE = "https://ir.amd.com/news-events/press-releases/detail/1265/amd-reports-third-quarter-2025-financial-results"


def evidence_checks(run):
    receipt = run["receipt"]
    citations = run.get("filing_citations") or {}
    exposures = [s["result"] for s in run["trace"] if s["tool"] == "get_portfolio_exposure"
                 and s["result"].get("ticker") == "AMD" and s["result"]["status"] == "ok"]
    return {
        "provider returned a draft": (receipt["engine"] in {"deepseek", "openai"}
                                      and run.get("status") == "draft" and bool(run.get("answer"))),
        "both tools returned evidence": {("search_filings", "found"), ("get_portfolio_exposure", "ok")}
                                       <= {(s["tool"], s["status"]) for s in receipt["steps"]},
        "AMD Q3 quote matched": not citations.get("issues") and any(
            d["ticker"] == "AMD" and d["quarter"] == "2025-Q3" and d["published"] == "2025-11-04"
            and d["url"] == SOURCE and d["excerpt"] == "Third quarter revenue was a record $9.2 billion"
            for d in citations.get("matched", [])),
        "sample holdings and loss reconciled": any(
            e["held"] and e["other_industry_tickers"] == ["NVDA"] and e["price_source"] == "synthetic"
            and e["valuation_date"] == "2026-10-30" and e["portfolio_total_usd"] == 100000
            and e["industry_value_usd"] == 42000 and e["industry_scenario"] == {
                "industry": "Semiconductors", "decline_pct": 8, "loss_usd": 3360, "loss_pct_of_portfolio": 3.36}
            for e in exposures),
    }


def main():
    try:
        run = run_agent(QUESTION, scope="filings_and_holdings", industry_decline_pct=8)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    receipt = run["receipt"]
    path = Path(f"finsentinel-run-{receipt['run_id']}.json")
    with path.open("x", encoding="utf-8") as output:
        json.dump(receipt, output, indent=2)
        output.write("\n")
    print(f"Execution receipt: {path}")
    checks = evidence_checks(run)
    for label, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {label}")
    if run.get("answer"):
        print("\nModel answer for manual comparison:\n", run["answer"], sep="")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
