"""Read-only tools for the local, single-demo-portfolio Agent lesson."""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from .risk import DEMO, SNAPSHOT_DATE, UNIVERSE, analyze

# Small reviewed excerpts. Dates are publication dates, not fiscal quarter ends.
FILINGS = (
    {"ticker": "AMD", "quarter": "2025-Q2", "published": "2025-08-05",
     "excerpt": "Second quarter revenue was a record $7.7 billion",
     "url": "https://ir.amd.com/financial-information/sec-filings/content/0000002488-25-000106/q22025991.htm"},
    {"ticker": "AMD", "quarter": "2025-Q3", "published": "2025-11-04",
     "excerpt": "Third quarter revenue was a record $9.2 billion",
     "url": "https://ir.amd.com/news-events/press-releases/detail/1265/amd-reports-third-quarter-2025-financial-results"},
)


class ExposureArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(min_length=1, max_length=12, description="Company stock ticker, e.g. AMD")


class FilingArgs(ExposureArgs):
    contains: str | None = Field(default=None, min_length=1, max_length=100,
        description="Optional case-insensitive literal substring in the source language, e.g. revenue.")
    through_date: date = Field(description="Include announcements published by the end of this calendar date")
    quarter: str | None = Field(default=None, pattern=r"^\d{4}-Q[1-4]$", description="Optional fiscal period, e.g. 2025-Q3")


def search_filings(args: FilingArgs, filing=None):
    source = filing.passages() if filing is not None else FILINGS
    term = (args.contains or "").strip().casefold()
    hits = [doc for doc in source if doc["ticker"] == args.ticker.strip().upper()
            and doc["published"] <= args.through_date.isoformat()
            and (args.quarter is None or doc["quarter"] == args.quarter)
            and term in doc["excerpt"].casefold()]
    return {"status": "found" if hits else "no_matching_evidence",
            "corpus": "User-provided text and metadata" if filing else "Two reviewed AMD earnings excerpts (2025 Q2 and Q3)",
            "total_matches": len(hits),
            "documents": sorted(hits, key=lambda doc: doc["published"], reverse=True)[:5]}


def get_portfolio_exposure(args: ExposureArgs, holdings: str = DEMO):
    ticker = args.ticker.strip().upper()
    if ticker not in UNIVERSE:
        return {"status": "unsupported_ticker", "ticker": ticker}
    # Resolve the portfolio in trusted application code; the model only supplies a ticker.
    report = analyze(holdings, 35, "Semiconductors", 8)
    industry = UNIVERSE[ticker]["industry"]
    position = next((p for p in report["positions"] if p["ticker"] == ticker), None)
    group = next((g for g in report["groups"] if g["name"] == industry), None)
    direct_weight = position["weight"] if position else 0
    industry_weight = group["weight"] if group else 0
    direct_value = position["value"] if position else 0
    industry_value = group["value"] if group else 0
    industry_share = direct_value / industry_value * 100 if industry_value else None
    peers = [p for p in report["positions"] if p["industry"] == industry and p["ticker"] != ticker]
    peer_weight = sum(p["weight"] for p in peers)
    return {"status": "ok", "ticker": ticker, "industry": industry, "valuation_date": SNAPSHOT_DATE,
            "price_source": "synthetic", "portfolio_total_usd": report["total"],
            "direct_value_usd": direct_value,
            "direct_weight_pct": direct_weight,
            "industry_value_usd": industry_value,
            "industry_weight_pct": industry_weight,
            "direct_share_of_industry_pct": industry_share,
            "other_industry_tickers": [p["ticker"] for p in peers],
            "other_industry_weight_pct": peer_weight,
            "exposure_statement": (
                f"{industry} total: {industry_weight:.2f}% of the portfolio, "
                f"including {ticker} at {direct_weight:.2f}% and other holdings "
                f"in the same industry at {peer_weight:.2f}%."
            )}


TOOLS = {
    "search_filings": (FilingArgs, "Find cited financial results in the local corpus by ticker, fiscal quarter and publication cutoff.", search_filings),
    "get_portfolio_exposure": (ExposureArgs, "Read synthetic exposures for the current portfolio. Weight fields use the whole portfolio. direct_share_of_industry_pct uses only the industry's total, and is null when it is zero.", get_portfolio_exposure),
}


def definitions():
    return [{"type": "function", "function": {"name": name, "description": description,
             "parameters": schema.model_json_schema()}} for name, (schema, description, _) in TOOLS.items()]


def execute(name, arguments, *, holdings=DEMO, filing=None):
    if name not in TOOLS:
        return {"status": "unknown_tool"}
    schema, _, function = TOOLS[name]
    try:
        args = schema.model_validate_json(arguments)
    except ValueError:
        return {"status": "invalid_arguments", "expected": schema.model_json_schema()["properties"]}
    if name == "get_portfolio_exposure":
        return function(args, holdings=holdings)
    return function(args, filing=filing)
