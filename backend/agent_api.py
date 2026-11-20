"""HTTP boundary for the filing and portfolio analysis workbench."""
from datetime import date
import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .agent_lab import model_config, replay, resume_agent, run_agent
from .agent_tools import DEFAULT_INDUSTRY_DECLINE, IndustryDecline
from .pdf_evidence import ResearchFiling
from .market_contract import MarketSnapshot
from .risk import SNAPSHOT_DATE, parse_holdings
from .run_checkpoints import CheckpointBusy, CheckpointGone, Checkpoints, ProviderConfigChanged

router = APIRouter(prefix="/api/agent")
checkpoints = Checkpoints()


class PortfolioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv_text: str = Field(min_length=1, max_length=65536)
    filing: ResearchFiling | None = None
    market_snapshot: MarketSnapshot | None = None
    industry_decline_pct: IndustryDecline = DEFAULT_INDUSTRY_DECLINE

    @field_validator("market_snapshot", mode="before")
    @classmethod
    def parse_snapshot(cls, value):
        # FastAPI decodes JSON first. Keep strict JSON date and number validation.
        if isinstance(value, dict):
            return MarketSnapshot.model_validate_json(json.dumps(value))
        return value


class ResearchRequest(PortfolioInput):
    contains: str | None = Field(default=None, min_length=1, max_length=100)
    ticker: str = Field(min_length=1, max_length=12)
    quarter: str = Field(pattern=r"^\d{4}-Q[1-4]$")
    through_date: date


class QuestionRequest(PortfolioInput):
    scope: Literal["filings_only", "filings_and_holdings"] = "filings_and_holdings"
    csv_text: str | None = Field(default=None, min_length=1, max_length=65536)
    question: str = Field(min_length=1, max_length=1200, pattern=r"\S")

    @model_validator(mode="after")
    def check_scope_inputs(self):
        if self.scope == "filings_and_holdings" and self.csv_text is None:
            raise ValueError("Combined research requires a holdings CSV.")
        if self.scope == "filings_only" and (self.csv_text is not None or self.market_snapshot is not None
                                            or "industry_decline_pct" in self.model_fields_set):
            raise ValueError("Filing-only research accepts no portfolio inputs.")
        return self


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
                  request.quarter, holdings=request.csv_text, filing=request.filing, contains=request.contains,
                  market_snapshot=request.market_snapshot, industry_decline_pct=request.industry_decline_pct)


@router.post("/ask")
def ask(request: QuestionRequest):
    if request.csv_text is not None:
        check_holdings(request.csv_text)
    if not model_config()[2]:
        raise HTTPException(status_code=503, detail="Live model access is not configured.")
    try:
        return run_agent(request.question, holdings=request.csv_text, filing=request.filing,
                         market_snapshot=request.market_snapshot, scope=request.scope,
                         save_checkpoint=checkpoints.save, industry_decline_pct=request.industry_decline_pct)
    except (RuntimeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Model request failed. Check the provider connection or model settings.") from exc


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


@router.post("/resume")
def resume(request: ResumeRequest):
    try:
        return checkpoints.resume(request.token, lambda state: resume_agent(state, checkpoints.save))
    except CheckpointGone as exc:
        raise HTTPException(410, "This checkpoint is unavailable. Start a new analysis.") from exc
    except CheckpointBusy as exc:
        raise HTTPException(409, "This run is already resuming. Retry shortly.") from exc
    except ProviderConfigChanged as exc:
        raise HTTPException(409, "Restore the original model configuration or start a new analysis.") from exc
    except (RuntimeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(502, "Invalid model response. Start a new analysis.") from exc
