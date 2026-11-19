import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from backend.market_data.snapshots import read_daily_close_csv
from backend.risk import DEMO, analyze, parse_holdings, synthetic_snapshot


EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "market_data"
TRADING_DATE = date(2026, 10, 30)
AS_OF = datetime(2026, 10, 30, 20, 15, tzinfo=timezone.utc)
HOLDINGS = "ticker,quantity,currency\nAMD,100,USD\nNVDA,200,USD\nCASH,12000,USD"


def read_snapshot(path=EXAMPLES / "synthetic_daily_closes.csv", tickers=("AMD", "NVDA", "SPY"), **changes):
    options = {"trading_date": TRADING_DATE, "as_of": AS_OF, "source": "synthetic-test-csv"} | changes
    return read_daily_close_csv(path, tickers, **options)


class MarketSnapshotReaderTests(unittest.TestCase):
    def test_csv_selects_one_date_and_keeps_absent_or_blank_quotes_missing(self):
        snapshot = read_snapshot(tickers=("AMD", "NVDA", "SPY", "XOM"))
        self.assertEqual(snapshot.trading_date, TRADING_DATE)
        self.assertEqual(snapshot.as_of, AS_OF)
        self.assertEqual(snapshot.source, "synthetic-test-csv")
        self.assertEqual(snapshot.currency, "USD")
        self.assertEqual(
            [(q.ticker, q.status, q.close) for q in snapshot.quotes],
            [("AMD", "available", 125.25), ("NVDA", "available", 175),
             ("SPY", "missing", None), ("XOM", "missing", None)],
        )

    def test_invalid_rows_cannot_be_silently_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "quotes.csv"
            for rows in (
                "AMD,2026-10-30,USD,0",
                "AMD,2026-10-30,USD,NaN",
                "AMD,2026-10-30,EUR,125.25",
                "AMD,2026-10-30,USD",
                "AMD,2026-10-30,USD,125.25\namd,2026-10-30,USD,126",
            ):
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    source.write_text("ticker,trading_date,currency,close\n" + rows, encoding="utf-8")
                    read_snapshot(source)

    def test_availability_must_be_a_timestamp_on_or_after_the_trading_date(self):
        for as_of in (datetime(2026, 10, 30, 20, 15), datetime(2026, 10, 29, 20, tzinfo=timezone.utc)):
            with self.subTest(as_of=as_of), self.assertRaises(ValueError):
                read_snapshot(as_of=as_of)

    def test_injected_snapshot_drives_valuation_without_synthetic_history(self):
        snapshot = read_snapshot(tickers=("AMD", "NVDA"))
        result = analyze(HOLDINGS, 35, "Semiconductors", 8, snapshot=snapshot)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["price_source"], snapshot.source)
        self.assertEqual(result["price_as_of"], AS_OF.isoformat())
        self.assertEqual(result["valuation_date"], "2026-10-30")
        self.assertEqual(result["total"], 59525)
        self.assertEqual(result["loss"], 3802)
        self.assertAlmostEqual(result["groups"][0]["weight"], 47525 / 59525 * 100)
        self.assertIsNone(result["history"])

    def test_missing_held_quote_pauses_portfolio_metrics_and_keeps_known_values(self):
        snapshot = read_snapshot(tickers=("AMD",))
        result = analyze(HOLDINGS, 35, "Semiconductors", 8, snapshot=snapshot)
        self.assertEqual(result["status"], "missing_prices")
        self.assertEqual(result["missing_tickers"], ["NVDA"])
        self.assertIsNone(result["total"])
        self.assertIsNone(result["loss"])
        self.assertIsNone(result["loss_pct"])
        self.assertIsNone(result["groups"])
        self.assertIsNone(result["history"])
        positions = {p["ticker"]: p for p in result["positions"]}
        self.assertEqual(positions["AMD"]["value"], 12525)
        self.assertEqual(positions["CASH"]["value"], 12000)
        self.assertIsNone(positions["AMD"]["weight"])
        self.assertIsNone(positions["NVDA"]["price"])
        self.assertIsNone(positions["NVDA"]["value"])

    def test_fixed_snapshot_preserves_existing_demo_numbers(self):
        snapshot = synthetic_snapshot(parse_holdings(DEMO))
        result = analyze(DEMO, 35, "Semiconductors", 8, snapshot=snapshot)
        self.assertEqual(result["price_source"], "synthetic")
        self.assertEqual(result["total"], 100000)
        self.assertEqual(result["groups"][0]["weight"], 42)
        self.assertEqual(result["loss"], 3360)
