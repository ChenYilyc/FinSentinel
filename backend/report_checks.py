"""Link retrieved filings to observed exposure and flag comparable revenue claims."""
import re
from decimal import Decimal


# Full-line matching keeps comparison-quarter, segment and forecast figures separate.
REVENUE = re.compile(r"Revenue for the quarter was USD (\d+(?:\.\d+)?) (million|billion)\.?", re.I)


def filing_assessments(trace):
    holdings = {}
    groups = {}
    for step in trace:
        result = step["result"]
        if step["tool"] == "get_portfolio_exposure" and result["status"] == "ok":
            holdings[result["ticker"]] = result["held"]
        if step["tool"] == "search_filings":
            for doc in result.get("documents", []):
                groups.setdefault((doc["ticker"], doc["quarter"]), {})[doc["url"]] = doc

    assessments = []
    for (ticker, quarter), documents in groups.items():
        values = {}
        for doc in documents.values():
            match = REVENUE.fullmatch(doc["excerpt"])
            if match:
                amount, unit = match.groups()
                millions = Decimal(amount) * (1000 if unit.lower() == "billion" else 1)
                values.setdefault(millions, []).append(doc["url"])
        conflicts = [url for urls in values.values() for url in urls] if len(values) > 1 else []
        assessments.append({"ticker": ticker, "quarter": quarter, "held": holdings.get(ticker),
                            "conflicting_revenue_sources": conflicts})
    return assessments
