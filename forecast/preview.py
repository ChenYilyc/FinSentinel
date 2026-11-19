"""Build a single-file demo from the same React bundle and API serialization."""
import base64
import json
from pathlib import Path
import re

from backend.main import ROOT, forecast, forecast_history


def export(output: Path):
    dist = ROOT / "frontend" / "dist"
    template = (dist / "index.html").read_text(encoding="utf-8")
    js_entry = re.search(r'<script[^>]* src="(/assets/[^"]+)"[^>]*></script>', template)
    css_entry = re.search(r'<link[^>]* href="(/assets/[^"]+\.css)"[^>]*>', template)
    if not js_entry or not css_entry:
        raise ValueError("Build the Vite dashboard before exporting the offline report.")
    script = (dist / js_entry[1].lstrip("/")).read_text(encoding="utf-8")
    style = (dist / css_entry[1].lstrip("/")).read_text(encoding="utf-8")
    csv_content = base64.b64encode(forecast_history().body).decode("ascii")
    payload = json.dumps({"snapshot": forecast(), "csvUrl": "data:text/csv;base64," + csv_content})
    template = template.replace(js_entry[0], "").replace(css_entry[0], "<style>" + style + "</style>")
    template = re.sub(r"<title>.*?</title>", "<title>FinSentinel | SPY five-session outlook</title>", template)
    payload = payload.replace("<", "\\u003c")
    script = script.replace("</script", "<\\/script")
    embedded = f'<script type="application/json" id="forecast-snapshot">{payload}</script>'
    template = template.replace("</body>", embedded + '<script type="module">' + script + "</script></body>")
    output.write_text(template, encoding="utf-8")


if __name__ == "__main__":
    export(ROOT / "FinSentinel-SPY-PoC.html")
