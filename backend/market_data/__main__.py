"""Export a market snapshot JSON file for the research panel."""

import argparse
from datetime import date, datetime
from pathlib import Path

from ..risk import synthetic_snapshot
from .snapshots import read_daily_close_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", required=True, help="Comma-separated ticker symbols.")
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic", action="store_true", help="Use the fixed demo prices.")
    mode.add_argument("--csv", type=Path, help="Read a normalized USD closing-price CSV.")
    parser.add_argument("--trading-date", type=date.fromisoformat)
    parser.add_argument("--as-of", type=datetime.fromisoformat, help="ISO timestamp with a timezone.")
    parser.add_argument("--source")
    args = parser.parse_args()
    tickers = args.tickers.split(",")
    metadata = (args.trading_date, args.as_of, args.source)
    if args.csv is not None and not all(metadata):
        parser.error("--csv requires --trading-date, --as-of, and --source.")
    if args.synthetic and any(value is not None for value in metadata):
        parser.error("--synthetic uses fixed date, timestamp, and source metadata.")
    try:
        if args.synthetic:
            snapshot = synthetic_snapshot(tickers)
        else:
            snapshot = read_daily_close_csv(
                args.csv, tickers, trading_date=args.trading_date, as_of=args.as_of, source=args.source
            )
        args.output.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Exported {len(snapshot.quotes)} quote(s) to {args.output}.")


if __name__ == "__main__":
    main()
