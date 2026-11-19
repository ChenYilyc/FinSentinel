"""HTTP boundary for the filing and portfolio analysis workbench."""
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .agent_lab import model_config, replay, run_agent
from .filing_text import FilingText
from .risk import SNAPSHOT_DATE, parse_holdings

router = APIRouter(prefix="/api/agent")


class PortfolioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv_text: str = Field(min_length=1, max_length=65536)
    filing: FilingText | None = None


class ResearchRequest(PortfolioInput):
    contains: str | None = Field(default=None, min_length=1, max_length=100)
    ticker: str = Field(min_length=1, max_length=12)
    quarter: str = Field(pattern=r"^\d{4}-Q[1-4]$")
    through_date: date


class QuestionRequest(PortfolioInput):
    question: str = Field(min_length=1, max_length=1200, pattern=r"\S")


def check_holdings(raw):
    try:
        parse_holdings(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/settings")
def settings():
    provider, model, key = model_config()
    return {"live_available": bool(key), "provider": provider, "model": model, "snapshot": SNAPSHOT_DATE}


@router.post("/report")
def report(request: ResearchRequest):
    check_holdings(request.csv_text)
    return replay(request.ticker.strip().upper(), request.through_date.isoformat(),
                  request.quarter, holdings=request.csv_text, filing=request.filing, contains=request.contains)


@router.post("/ask")
def ask(request: QuestionRequest):
    check_holdings(request.csv_text)
    if not model_config()[2]:
        raise HTTPException(status_code=503, detail="Live model access is not configured.")
    try:
        return run_agent(request.question, holdings=request.csv_text, filing=request.filing)
    except (RuntimeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Model request failed. Check the provider connection or model settings.") from exc
