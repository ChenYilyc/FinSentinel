"""Validate the fixed research snapshot before building session-based labels."""
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay, USMartinLutherKingJr,
    USMemorialDay, USPresidentsDay, USThanksgivingDay, nearest_workday, sunday_to_monday,
)

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "examples" / "spy_adjusted_close.csv"
FIRST, LAST = "2016-07-25", "2026-07-23"
CHECKSUM = "3dbffd8e15a2beae9aedde1e09ecb70510074c03bf8b40f74e042dbaadcbf2eb"
SOURCE = "https://github.com/Setooooo/etf-insight/blob/master/data/SOURCE.md"
FEATURES = ["return_1", "return_5", "return_20", "volatility_5", "volatility_20", "ma_gap_20"]
HORIZON = 5


class SnapshotHolidays(AbstractHolidayCalendar):
    """NYSE full-day closures for the frozen period; early closes are sessions."""
    rules = [
        Holiday("New Year", month=1, day=1, observance=sunday_to_monday),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
        Holiday("Bush funeral", year=2018, month=12, day=5),
        Holiday("Carter funeral", year=2025, month=1, day=9),
    ]


def sessions(start: str, end: str) -> pd.DatetimeIndex:
    weekdays = pd.bdate_range(start, end)
    return weekdays.difference(SnapshotHolidays().holidays(start, end))


def validate(raw: pd.DataFrame) -> pd.Series:
    dates = pd.DatetimeIndex(pd.to_datetime(raw["Date"], format="%Y-%m-%d", errors="raise"))
    expected = sessions(FIRST, LAST)
    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("Duplicate or unordered trading date")
    if not dates.equals(expected):
        missing = expected.difference(dates).strftime("%Y-%m-%d").tolist()
        extra = dates.difference(expected).strftime("%Y-%m-%d").tolist()
        raise ValueError(f"Unexpected session calendar: missing={missing[:8]}, extra={extra[:8]}")
    prices = pd.to_numeric(raw["Adj Close"], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Adjusted closes must be finite and positive")
    return pd.Series(prices, index=dates, name="price")


def load_prices() -> pd.Series:
    canonical = PRICES.read_bytes().replace(b"\r\n", b"\n")
    if sha256(canonical).hexdigest() != CHECKSUM:
        raise ValueError("Unexpected snapshot checksum. Restore the frozen SPY input.")
    return validate(pd.read_csv(PRICES))


def samples(prices: pd.Series) -> pd.DataFrame:
    frame = prices.to_frame("price")
    daily = prices.pct_change(fill_method=None)
    for window in (1, 5, 20):
        frame[f"return_{window}"] = prices.pct_change(window, fill_method=None)
    for window in (5, 20):
        frame[f"volatility_{window}"] = daily.rolling(window).std()
    frame["ma_gap_20"] = prices / prices.rolling(20).mean() - 1
    frame["maturity"] = prices.index.to_series().shift(-HORIZON)
    frame["realized"] = prices.shift(-HORIZON) / prices - 1
    frame["up"] = frame["realized"].gt(0).where(frame["maturity"].notna()).astype("Int64")
    return frame.dropna(subset=FEATURES)
