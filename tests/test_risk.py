import unittest
from statistics import stdev

from backend.risk import DEMO, analyze


def report(csv=DEMO, threshold=35, industry="Semiconductors", decline=8):
    return analyze(csv, threshold, industry, decline)


class ReferenceCases(unittest.TestCase):
    def test_hand_calculated_demo(self):
        result = report()
        self.assertEqual(result["total"], 100_000)
        self.assertEqual([g["name"] for g in result["groups"] if g["alert"]], ["Semiconductors"])
        self.assertEqual(result["groups"][0]["weight"], 42)
        self.assertEqual((result["loss"], result["loss_pct"]), (3360, 3.36))

    def test_exact_threshold_is_not_breached(self):
        self.assertFalse(any(group["alert"] for group in report(threshold=42)["groups"]))

    def test_cash_only_and_no_target_exposure(self):
        r = report("ticker,quantity,currency\nCASH,12000,USD")
        self.assertEqual(r["loss"], 0)
        self.assertFalse(r["groups"][0]["alert"])
        for metric in ("return_pct", "daily_volatility_pct", "max_drawdown_pct"):
            self.assertEqual(r["history"][metric], 0)

    def test_peak_to_trough_and_daily_sample_volatility(self):
        r = report("ticker,quantity,currency\nXOM,1,USD")
        history = r["history"]
        closes = [100, 105, 95, 100, 98, 100]
        self.assertEqual([p["value"] for p in history["series"]], closes)
        self.assertEqual(history["return_pct"], 0)
        self.assertAlmostEqual(history["max_drawdown_pct"], 10 / 105 * 100)
        daily = [b / a - 1 for a, b in zip(closes, closes[1:])]
        self.assertAlmostEqual(history["daily_volatility_pct"], stdev(daily) * 100)

    def test_portfolio_daily_values_use_fixed_quantities(self):
        result = report()
        series = result["history"]["series"]
        self.assertEqual(series[0]["value"], 98100)
        self.assertEqual(series[-1]["value"], result["total"])
        self.assertAlmostEqual(result["history"]["return_pct"], (100000 / 98100 - 1) * 100)

    def test_duplicate_fractional_holdings_and_bom(self):
        r = report("\ufeffquantity,currency,ticker\n0.25,USD,nvda\n0.25,USD,NVDA")
        self.assertEqual(len(r["positions"]), 1)
        self.assertEqual(r["total"], 75)

    def test_invalid_input_rejected_in_full(self):
        for row in ["XYZ,1,USD", "AMD,NaN,USD", "AMD,-2,USD", "AMD,0,USD", "AMD,1,SGD", "AMD,1", '"AMD,1,USD']:
            with self.subTest(row=row), self.assertRaises(ValueError):
                report(DEMO + "\n" + row)
