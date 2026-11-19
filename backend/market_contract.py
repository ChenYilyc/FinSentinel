"""Wire format shared by the future daily-close reader and the report consumer."""
from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ticker: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,11}$")


class AvailableQuote(Quote):
    status: Literal["available"]
    close: float = Field(gt=0, allow_inf_nan=False)


class MissingQuote(Quote):
    status: Literal["missing"]
    close: None


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = Field(pattern=r"\S")
    trading_date: date
    as_of: AwareDatetime
    currency: Literal["USD"]
    quotes: list[Annotated[AvailableQuote | MissingQuote, Field(discriminator="status")]] = Field(min_length=1)

    @field_validator("quotes")
    @classmethod
    def unique_tickers(cls, quotes):
        if len({quote.ticker for quote in quotes}) != len(quotes):
            raise ValueError("Each ticker may appear only once per snapshot.")
        return quotes
