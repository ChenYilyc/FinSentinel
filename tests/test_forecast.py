import csv
import json
import unittest

import numpy as np
import pandas as pd

from backend.main import forecast, forecast_history
from forecast.data import FEATURES, PRICES, load_prices, samples, validate
from forecast.train import OUTPUT, backtest


class ForecastChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prices = load_prices()
        cls.frame = samples(cls.prices)

    def test_hand_checked_trading_dates_and_returns(self):
        # Explicitly cross two special closures and a year-end with an open Friday.
        for start, end, entry, exit_price in [
            ("2018-12-03", "2018-12-11", 248.405517578125, 234.91357421875),
            ("2021-12-27", "2022-01-03", 449.06304931640625, 449.4864196777344),
            ("2025-01-06", "2025-01-14", 585.339111328125, 572.390869140625),
        ]:
            with self.subTest(start=start):
                row = self.frame.loc[start]
                self.assertEqual(str(row.maturity.date()), end)
                self.assertAlmostEqual(row.realized, exit_price / entry - 1)
                self.assertEqual(row.up, int(exit_price > entry))

    def test_incomplete_or_invalid_prices_rejected(self):
        raw = pd.read_csv(PRICES)
        for changed in (raw.drop(20), pd.concat([raw, raw.tail(1)]), raw.iloc[::-1],
                        raw.assign(**{"Adj Close": np.inf})):
            with self.assertRaises(ValueError):
                validate(changed)

    def test_features_do_not_depend_on_future_and_final_labels_unknown(self):
        cut = 500
        prefix = samples(self.prices.iloc[:cut])
        pd.testing.assert_frame_equal(prefix[FEATURES], self.frame.loc[prefix.index, FEATURES])
        self.assertTrue(self.frame.tail(5).up.isna().all())
        self.assertEqual(self.frame.up.isna().sum(), 5)

    def test_expanding_windows_and_inference_receipt(self):
        daily, windows = backtest(self.frame)
        self.assertEqual(len(daily), 756)
        self.assertTrue(daily.index.is_unique)
        for window in windows:
            self.assertLess(window["last_train_label"], window["start"])
            train = self.frame[self.frame.maturity < window["start"]]
            evaluated = daily[daily.fold == window["fold"]]
            self.assertAlmostEqual(evaluated.baseline.iloc[0], train.up.mean())
        snapshot = json.loads(OUTPUT.read_text(encoding="utf-8"))
        weights = snapshot["final_model"]
        x = self.frame[weights["features"]].iloc[-1].to_numpy()
        z = (x - weights["means"]) / weights["scales"]
        odds = np.exp(z @ weights["coefficients"] + weights["intercept"])
        self.assertAlmostEqual(odds / (1 + odds), snapshot["pending"]["model"])

    def test_served_snapshot_and_csv_agree(self):
        receipt = forecast()
        rows = list(csv.DictReader(forecast_history().body.decode().splitlines()))
        self.assertEqual(len(rows), receipt["overall"]["n"])
        self.assertNotIn("daily", receipt)
        self.assertEqual(rows[-1]["maturity"], receipt["cutoff"])
        self.assertEqual(rows[-1]["model"], str(receipt["settled"]["model"]))
        self.assertEqual(sum(b["count"] for b in receipt["calibration"] if b["method"] == "model"), len(rows))
