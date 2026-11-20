"""Read-only tools for the local, single-demo-portfolio Agent lesson."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .pdf_evidence import PdfFiling
from .risk import DEMO, SNAPSHOT_DATE, UNIVERSE, parse_holdings

IndustryDecline = Annotated[int, Field(strict=True, ge=0, le=100)]
DEFAULT_INDUSTRY_DECLINE = 8

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
    corpus = "User-provided text and metadata" if filing else "Two reviewed AMD earnings excerpts (2025 Q2 and Q3)"
    if isinstance(filing, PdfFiling):
        corpus = "User-provided PDF passages and page metadata"
    return {"status": "found" if hits else "no_matching_evidence", "corpus": corpus,
            "total_matches": len(hits),
            "documents": sorted(hits, key=lambda doc: doc["published"], reverse=True)[:5]}


def get_portfolio_exposure(args: ExposureArgs, holdings: str = DEMO, market_snapshot=None,
                           industry_decline_pct: IndustryDecline = DEFAULT_INDUSTRY_DECLINE):
    ticker = args.ticker.strip().upper()
    if ticker not in UNIVERSE:
        return {"status": "unsupported_ticker", "ticker": ticker}
    quantities = parse_holdings(holdings)
    if market_snapshot is None:
        prices = {code: Decimal(asset["price"]) for code, asset in UNIVERSE.items()}
        source, day, as_of = "synthetic", SNAPSHOT_DATE, None
    else:
        prices = {row.ticker: Decimal(str(row.close)) for row in market_snapshot.quotes if row.close is not None}
        source = market_snapshot.source
        day = market_snapshot.trading_date.isoformat()
        as_of = market_snapshot.as_of.isoformat()
    prices["CASH"] = Decimal(1)
    industry = UNIVERSE[ticker]["industry"]
    group = [code for code in quantities if UNIVERSE[code]["industry"] == industry]
    peers = [code for code in group if code != ticker]
    missing = sorted(quantities.keys() - prices.keys())

    def value(codes):
        if any(code not in prices for code in codes):
            return None
        return sum((prices[code] * quantities[code] for code in codes), Decimal(0))

    def share(numerator, denominator):
        if numerator is None or not denominator:
            return None
        return float(100 * numerator / denominator)

    total = value(quantities)
    sector = value(group)
    scenario = None
    if ticker != "CASH":
        loss = None if sector is None else sector * industry_decline_pct / 100
        if industry_decline_pct == 0:
            loss = Decimal(0)
        scenario = {"industry": industry, "decline_pct": industry_decline_pct,
                    "loss_usd": float(loss) if loss is not None else None,
                    "loss_pct_of_portfolio": share(loss, total)}
    direct = value([ticker]) if ticker in quantities else Decimal(0)
    direct_weight, industry_weight = share(direct, total), share(sector, total)
    peer_weight = share(value(peers), total)
    if missing:
        statement = "Missing prices for " + ", ".join(missing) + ". Null metrics are unavailable."
    else:
        statement = (f"{industry} total: {industry_weight:.2f}% of the portfolio, "
                     f"including {ticker} at {direct_weight:.2f}% and other holdings "
                     f"in the same industry at {peer_weight:.2f}%.")
    return {"status": "ok", "ticker": ticker, "held": ticker in quantities, "industry": industry,
            "valuation_date": day, "as_of": as_of, "price_source": source, "missing_prices": missing,
            "portfolio_total_usd": float(total) if total is not None else None,
            "direct_value_usd": float(direct) if direct is not None else None,
            "industry_value_usd": float(sector) if sector is not None else None,
            "direct_weight_pct": direct_weight, "industry_weight_pct": industry_weight,
            "direct_share_of_industry_pct": share(direct, sector),
            "other_industry_tickers": peers, "other_industry_weight_pct": peer_weight,
            "exposure_statement": statement, "industry_scenario": scenario}


TOOLS = {
    "search_filings": (FilingArgs, "Find cited financial results in the local corpus by ticker, fiscal quarter and publication cutoff.", search_filings),
    "get_portfolio_exposure": (ExposureArgs, "Read exposure using the active price snapshot. Portfolio weights use the whole portfolio. direct_share_of_industry_pct uses the industry total. Null means missing inputs or an empty denominator.", get_portfolio_exposure),
}

TOOL_SCOPES = {
    "filings_only": ("search_filings",),
    "filings_and_holdings": ("search_filings", "get_portfolio_exposure"),
}


def definitions(scope="filings_and_holdings"):
    result = []
    for name in TOOL_SCOPES[scope]:
        schema, description, _ = TOOLS[name]
        result.append({"type": "function", "function": {"name": name, "description": description,
                       "parameters": schema.model_json_schema()}})
    return result


def execute(name, arguments, *, holdings=DEMO, filing=None, market_snapshot=None, scope="filings_and_holdings",
            industry_decline_pct=DEFAULT_INDUSTRY_DECLINE):
    if name not in TOOLS:
        return {"status": "unknown_tool"}
    if name not in TOOL_SCOPES[scope]:
        return {"status": "permission_denied"}
    schema, _, function = TOOLS[name]
    try:
        args = schema.model_validate_json(arguments)
    except ValueError:
        return {"status": "invalid_arguments", "expected": schema.model_json_schema()["properties"]}
    if name == "get_portfolio_exposure":
        return function(args, holdings=holdings, market_snapshot=market_snapshot, industry_decline_pct=industry_decline_pct)
    return function(args, filing=filing)
