"""Construct contract snapshots from fixed prices or an authorized CSV export."""

import csv
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..market_contract import AvailableQuote, MarketSnapshot, MissingQuote


CSV_COLUMNS = {"ticker", "trading_date", "currency", "close"}


def build_snapshot(
    tickers: Iterable[str],
    prices: Mapping[str, Decimal],
    *,
    trading_date: date,
    as_of: datetime,
    source: str,
) -> MarketSnapshot:
    if as_of.utcoffset() is None or as_of.astimezone(timezone.utc).date() < trading_date:
        raise ValueError("as_of must be an aware timestamp on or after the trading date.")

    quotes: list[AvailableQuote | MissingQuote] = []
    for symbol in tickers:
        ticker = symbol.strip().upper()
        price = prices.get(ticker)
        if price is None:
            quotes.append(MissingQuote(ticker=ticker, status="missing", close=None))
        else:
            quotes.append(AvailableQuote(ticker=ticker, status="available", close=float(price)))
    return MarketSnapshot(
        source=source, trading_date=trading_date, as_of=as_of, currency="USD", quotes=quotes
    )


def read_daily_close_csv(
    path: Path,
    tickers: Iterable[str],
    *,
    trading_date: date,
    as_of: datetime,
    source: str,
) -> MarketSnapshot:
    """Read one day's unadjusted USD closes from a normalized provider export."""
    prices: dict[str, Decimal] = {}
    seen: set[tuple[date, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        try:
            headers = reader.fieldnames or []
            if len(headers) != len(CSV_COLUMNS) or set(headers) != CSV_COLUMNS:
                raise ValueError("Expected CSV columns: ticker, trading_date, currency, close.")
            for row in reader:
                line = reader.line_num
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Line {line}: expected four fields.")
                ticker = row["ticker"].strip().upper()
                if not ticker or row["currency"].strip().upper() != "USD":
                    raise ValueError(f"Line {line}: expected ticker and USD currency.")
                raw_date = row["trading_date"].strip()
                try:
                    day = date.fromisoformat(raw_date)
                except ValueError as exc:
                    raise ValueError(f"Line {line}: expected trading date in YYYY-MM-DD format.") from exc
                if day.isoformat() != raw_date:
                    raise ValueError(f"Line {line}: expected trading date in YYYY-MM-DD format.")
                key = (day, ticker)
                if key in seen:
                    raise ValueError(f"Line {line}: duplicate ticker and trading date.")
                seen.add(key)
                close = row["close"].strip()
                if not close:
                    continue
                try:
                    price = Decimal(close)
                except InvalidOperation as exc:
                    raise ValueError(f"Line {line}: expected a positive USD closing price.") from exc
                if not price.is_finite() or price <= 0:
                    raise ValueError(f"Line {line}: expected a positive USD closing price.")
                if day == trading_date:
                    prices[ticker] = price
        except csv.Error as exc:
            raise ValueError(f"Line {reader.line_num}: malformed daily-close CSV.") from exc

    return build_snapshot(tickers, prices, trading_date=trading_date, as_of=as_of, source=source)
