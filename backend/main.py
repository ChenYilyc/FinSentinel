import csv
import io
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .risk import DEMO, INDUSTRIES, SNAPSHOT_DATE, UNIVERSE, analyze
from .agent_api import router as agent_router

app = FastAPI(title="FinSentinel", version="0.1.0")
app.include_router(agent_router)


class AnalysisRequest(BaseModel):
    csv_text: str = Field(min_length=1, max_length=65536)
    threshold: int = Field(default=35, ge=1, le=100)
    industry: str = "Semiconductors"
    decline: int = Field(default=8, ge=0, le=100)


@app.get("/api/demo")
def demo():
    return dict(csv_text=DEMO, industries=INDUSTRIES, tickers=sorted(UNIVERSE),
                snapshot=SNAPSHOT_DATE, report=analyze(DEMO, 35, "Semiconductors", 8))


@app.get("/api/template.csv", response_class=PlainTextResponse)
def template():
    return PlainTextResponse(DEMO, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="portfolio.csv"'})


@app.post("/api/analyze")
def analyze_portfolio(request: AnalysisRequest):
    try:
        return analyze(request.csv_text, request.threshold, request.industry, request.decline)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


ROOT = Path(__file__).resolve().parents[1]


def forecast_snapshot():
    try:
        with (ROOT / "forecast" / "result.json").open(encoding="utf-8") as source:
            return json.load(source)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Train the SPY forecast snapshot first.") from exc


@app.get("/api/forecast")
def forecast():
    result = forecast_snapshot()
    return {key: value for key, value in result.items() if key not in {"daily", "final_model"}}


@app.get("/api/forecast/history.csv", response_class=PlainTextResponse)
def forecast_history():
    records = forecast_snapshot()["daily"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["date", "maturity", "fold", "model", "baseline", "realized", "up"])
    writer.writeheader()
    writer.writerows(records)
    return PlainTextResponse(output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="spy-five-session-backtest.csv"'
    })


dist = ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
