"""Local USD long-only portfolio valuation and historical risk."""
import csv
import io
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import stdev

from .market_contract import MarketSnapshot
from .market_data.snapshots import build_snapshot

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
DEMO = (EXAMPLES / "portfolio.csv").read_text(encoding="utf-8")
with (EXAMPLES / "universe.csv").open(encoding="utf-8", newline="") as source:
    UNIVERSE = {item["ticker"]: item for item in csv.DictReader(source)}
SYNTHETIC_AS_OF = datetime(2026, 10, 30, 20, 15, tzinfo=timezone.utc)
SNAPSHOT_DATE = SYNTHETIC_AS_OF.date().isoformat()
with (EXAMPLES / "prior_closes.csv").open(encoding="utf-8", newline="") as source:
    PRICE_HISTORY = [
        (row["date"], {ticker: Decimal(row[ticker]) for ticker in UNIVERSE})
        for row in csv.DictReader(source)
    ]
PRICE_HISTORY.append((SNAPSHOT_DATE, {ticker: Decimal(asset["price"]) for ticker, asset in UNIVERSE.items()}))
INDUSTRIES = sorted({item["industry"] for item in UNIVERSE.values()} - {"Cash"})
HEADERS = ["ticker", "quantity", "currency"]
QTY = re.compile(r"[0-9]{1,10}(?:\.[0-9]{1,6})?\Z")


def parse_holdings(raw: str) -> dict[str, Decimal]:
    reader = csv.reader(io.StringIO(raw.removeprefix("\ufeff"), newline=""), strict=True)
    totals: dict[str, Decimal] = defaultdict(Decimal)
    try:
        header = [cell.strip().lower() for cell in next(reader, [])]
        if sorted(header) != sorted(HEADERS):
            raise ValueError("Expected CSV columns: ticker, quantity, currency.")
        for cells in reader:
            if not cells or not any(cell.strip() for cell in cells):
                continue
            if len(cells) != len(HEADERS):
                raise ValueError(f"Line {reader.line_num}: expected three fields.")
            row = dict(zip(header, (cell.strip() for cell in cells)))
            ticker = row["ticker"].upper()
            if ticker not in UNIVERSE:
                raise ValueError(f"Line {reader.line_num}: unsupported ticker {ticker[:24]!r}.")
            if row["currency"].upper() != "USD":
                raise ValueError(f"Line {reader.line_num}: only USD is supported.")
            if not QTY.fullmatch(row["quantity"]) or Decimal(row["quantity"]) <= 0:
                raise ValueError(f"Line {reader.line_num}: enter a positive quantity (up to 10 integer and 6 decimal digits).")
            totals[ticker] += Decimal(row["quantity"])
    except csv.Error as exc:
        raise ValueError(f"Line {reader.line_num}: malformed CSV.") from exc
    if not totals:
        raise ValueError("Include at least one holding.")
    return dict(totals)


def historical_risk(holdings: dict[str, Decimal]) -> dict:
    """Revalue the same quantities at each synthetic close, including cash."""
    values = [
        (date, sum(prices[ticker] * quantity for ticker, quantity in holdings.items()))
        for date, prices in PRICE_HISTORY
    ]
    returns = [current / previous - 1 for (_, previous), (_, current) in zip(values, values[1:])]
    opening_value = peak = values[0][1]
    max_drawdown = Decimal(0)
    for _, value in values:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)
    return {
        "series": [{"date": date, "value": float(value)} for date, value in values],
        "return_pct": float((values[-1][1] / opening_value - 1) * 100),
        "daily_volatility_pct": float(stdev(returns) * 100),
        "max_drawdown_pct": float(max_drawdown * 100),
    }


def synthetic_snapshot(tickers: Iterable[str]) -> MarketSnapshot:
    """Read the fixed demo close with its original snapshot date."""
    return build_snapshot(
        tickers, PRICE_HISTORY[-1][1], trading_date=date.fromisoformat(SNAPSHOT_DATE),
        as_of=SYNTHETIC_AS_OF, source="synthetic",
    )


def analyze(
    raw: str,
    threshold: int,
    industry: str,
    decline: int,
    *,
    snapshot: MarketSnapshot | None = None,
) -> dict:
    if industry not in INDUSTRIES:
        raise ValueError("Choose a supported industry.")
    positions = []
    exposures: dict[str, Decimal] = defaultdict(Decimal)
    holdings = parse_holdings(raw)
    snapshot_metadata = {}
    missing: list[str] = []
    if snapshot is None:
        prices = PRICE_HISTORY[-1][1]
    else:
        prices = {quote.ticker: Decimal(str(quote.close))
                  for quote in snapshot.quotes if quote.status == "available"}
        prices["CASH"] = Decimal(1)
        missing = sorted(set(holdings) - prices.keys())
        snapshot_metadata = {
            "status": "missing_prices" if missing else "ok",
            "valuation_date": snapshot.trading_date.isoformat(),
            "price_as_of": snapshot.as_of.isoformat(),
            "price_source": snapshot.source,
            "missing_tickers": missing,
        }

    for ticker, quantity in holdings.items():
        asset = UNIVERSE[ticker]
        price = prices.get(ticker)
        value = None if price is None else price * quantity
        if value is not None:
            exposures[asset["industry"]] += value
        positions.append(dict(ticker=ticker, name=asset["name"], industry=asset["industry"],
                              quantity=quantity, price=price, value=value))

    loss = exposures.get(industry, Decimal(0)) * decline / 100
    if missing:
        sector_incomplete = any(UNIVERSE[ticker]["industry"] == industry for ticker in missing)
        for position in positions:
            position["weight"] = None
            for key in ("value", "quantity", "price"):
                if position[key] is not None:
                    position[key] = float(position[key])
        return dict(total=None, groups=None, positions=positions,
                    loss=None if sector_incomplete else float(loss), loss_pct=None,
                    industry=industry, decline=decline, threshold=threshold, history=None, **snapshot_metadata)

    total = sum(exposures.values())
    groups = []
    for name, value in sorted(exposures.items(), key=lambda item: -item[1]):
        weight = value / total * 100
        groups.append(dict(name=name, value=float(value), weight=float(weight),
                           alert=name != "Cash" and weight > threshold))
    for position in positions:
        position["weight"] = float(position["value"] / total * 100)
        for key in ("value", "quantity", "price"):
            position[key] = float(position[key])
    return dict(total=float(total), groups=groups,
                positions=sorted(positions, key=lambda p: -p["value"]),
                loss=float(loss), loss_pct=float(loss / total * 100),
                industry=industry, decline=decline, threshold=threshold,
                history=historical_risk(holdings) if snapshot is None else None, **snapshot_metadata)
