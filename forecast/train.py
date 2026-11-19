"""Run from the repository root with python -m forecast.train."""
import argparse
import base64
from hashlib import sha256
from importlib.metadata import version
import io
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import CHECKSUM, FEATURES, FIRST, HORIZON, LAST, ROOT, SOURCE, load_prices, samples, sessions

FOLDS, WINDOW = 3, 252
OUTPUT = ROOT / "forecast" / "result.json"


def fit(train):
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, tol=1e-8))
    model.fit(train[FEATURES], train["up"].astype(int))
    return model


def scores(rows):
    actual = rows["up"].to_numpy(dtype=int)
    result = {"n": len(rows), "up_rate": float(actual.mean())}
    for column in ("model", "baseline"):
        p = rows[column].to_numpy()
        result[column + "_accuracy"] = float(((p >= .5) == actual).mean())
        result[column + "_brier"] = float(np.mean((p - actual) ** 2))
    result["delta_brier"] = result["model_brier"] - result["baseline_brier"]
    return result


def iso(stamp):
    return stamp.date().isoformat()


def backtest(frame):
    labeled = frame.dropna(subset=["up"])
    predictions, windows = [], []
    for fold in range(FOLDS):
        start = len(labeled) - (FOLDS - fold) * WINDOW
        test = labeled.iloc[start:start + WINDOW].copy()
        train = labeled[labeled.maturity < test.index[0]]
        if len(test) != WINDOW or train.empty or train.maturity.max() >= test.index[0]:
            raise ValueError("Insufficient history or overlapping training labels")
        model = fit(train)
        test["model"] = model.predict_proba(test[FEATURES])[:, 1]
        test["baseline"] = float(train.up.mean())
        test["fold"] = fold + 1
        predictions.append(test)
        windows.append(dict(fold=fold + 1, start=iso(test.index[0]), end=iso(test.index[-1]),
                            train_n=len(train), last_train_label=iso(train.maturity.max()), **scores(test)))
    return pd.concat(predictions), windows


def calibration(rows):
    from matplotlib.figure import Figure
    fig = Figure(figsize=(5.6, 3.9), dpi=125, layout="constrained")
    ax = fig.subplots()
    ax.plot([0, 1], [0, 1], "--", color="0.65", label="Perfect calibration")
    bins = []
    for column, color in (("model", "#175f55"), ("baseline", "#b36632")):
        idx = np.minimum((rows[column] * 10).astype(int), 9)
        series = []
        for bin_id, group in rows.groupby(idx):
            point = dict(method=column, bin=int(bin_id), count=len(group),
                         predicted=float(group[column].mean()), observed=float(group.up.mean()))
            bins.append(point)
            series.append(point)
        ax.plot([p["predicted"] for p in series], [p["observed"] for p in series],
                "o-", color=color, label=column.title())
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Mean predicted probability", ylabel="Observed up fraction")
    ax.legend(frameon=False)
    image = io.BytesIO()
    fig.savefig(image, format="png")
    return bins, base64.b64encode(image.getvalue()).decode("ascii")


def build_report():
    prices = load_prices()
    frame = samples(prices)
    daily, windows = backtest(frame)
    labeled = frame.dropna(subset=["up"])
    # Snapshot inference occurs after the last close; labels maturing today are observable.
    model = fit(labeled)
    scaler, classifier = model.steps[0][1], model.steps[1][1]
    weights = dict(features=FEATURES, means=scaler.mean_.tolist(), scales=scaler.scale_.tolist(),
                   coefficients=classifier.coef_[0].tolist(), intercept=float(classifier.intercept_[0]))
    model_id = "spy-lr-" + sha256(json.dumps(weights, sort_keys=True).encode()).hexdigest()[:12]
    future = sessions(LAST, (prices.index[-1] + pd.Timedelta(days=14)).strftime("%Y-%m-%d"))
    records = [dict(date=iso(day), maturity=iso(row.maturity), fold=int(row.fold), model=row.model,
                    baseline=row.baseline, realized=row.realized, up=int(row.up))
               for day, row in daily.iterrows()]
    bins, image = calibration(daily)
    return dict(symbol="SPY", horizon=HORIZON, version=model_id, source=SOURCE, sha256=CHECKSUM,
                first=FIRST, cutoff=LAST, rows=len(prices), labeled=len(labeled),
                pending_count=int(frame.up.isna().sum()), windows=windows, overall=scores(daily),
                pending=dict(date=LAST, maturity=iso(future[HORIZON]),
                             model=float(model.predict_proba(frame[FEATURES].tail(1))[0, 1]),
                             baseline=float(labeled.up.mean())),
                settled=records[-1], calibration=bins, calibration_png=image, daily=records,
                final_model=weights, training_versions={k:version(k) for k in
                ("pandas", "numpy", "scikit-learn", "scipy", "matplotlib")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    output = parser.parse_args().output
    result = build_report()
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=output.parent, encoding="utf-8", delete=False) as temp:
        json.dump(result, temp, allow_nan=False, separators=(",", ":"))
    Path(temp.name).replace(output)
    print(result["version"], result["cutoff"], json.dumps(result["overall"]))


if __name__ == "__main__":
    main()
