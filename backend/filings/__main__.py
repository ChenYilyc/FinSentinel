"""Export a PDF as bounded evidence JSON files for the research panel."""

import argparse
from collections.abc import Iterator
from datetime import date
import json
from pathlib import Path

from ..pdf_evidence import PdfPassage
from .pdf import PdfDocument, parse_pdf


MAX_BUNDLE_BYTES = 512 * 1024
MAX_DOCUMENTS = 1000
PREFIX = b'{"documents":['
SUFFIX = b']}'


def evidence_bundles(
    document: PdfDocument, *, ticker: str, quarter: str, published: date
) -> Iterator[bytes]:
    """Yield importable batches without dropping passages or changing locators."""
    rows: list[bytes] = []
    size = len(PREFIX) + len(SUFFIX)
    for passage in document.passages(ticker=ticker, quarter=quarter, published=published):
        encoded = PdfPassage.model_validate(passage).model_dump_json().encode("utf-8")
        if rows and (len(rows) == MAX_DOCUMENTS or size + 1 + len(encoded) > MAX_BUNDLE_BYTES):
            yield PREFIX + b",".join(rows) + SUFFIX
            rows.clear()
            size = len(PREFIX) + len(SUFFIX)
        size += bool(rows) + len(encoded)
        rows.append(encoded)
    if rows:
        yield PREFIX + b",".join(rows) + SUFFIX


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--quarter", required=True)
    parser.add_argument("--published", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="Create a new output directory.")
    args = parser.parse_args()
    try:
        document = parse_pdf(args.pdf.read_bytes())
        bundles = list(evidence_bundles(
            document, ticker=args.ticker.strip().upper(), quarter=args.quarter.strip().upper(),
            published=args.published,
        ))
        status = {
            "document_version": document.version,
            "pages": [{"page": p.page, "status": p.status, "reason": p.reason} for p in document.pages],
        }
        args.output_dir.mkdir(parents=True)
        for index, bundle in enumerate(bundles, start=1):
            (args.output_dir / f"evidence-{index:03}.json").write_bytes(bundle)
        (args.output_dir / "page-status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Exported {len(bundles)} evidence file(s) and page-status.json.")


if __name__ == "__main__":
    main()
