"""Consume page-level evidence from one parsed PDF per research request."""
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .filing_text import FilingText


class PdfPassage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,11}$")
    quarter: str = Field(pattern=r"^[0-9]{4}-Q[1-4]$")
    published: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    excerpt: str = Field(min_length=1, max_length=1200)
    url: str = Field(max_length=120)
    source: Literal["uploaded_pdf"]
    page: int = Field(strict=True, ge=1)
    document_version: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("published")
    @classmethod
    def calendar_date(cls, value):
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def check_passage(self):
        if not self.excerpt.strip() or self.excerpt != self.excerpt.strip() or self.excerpt.splitlines() != [self.excerpt]:
            raise ValueError("Provide a trimmed, single-line PDF passage.")
        if not re.fullmatch(rf"#filing-{self.document_version}-P{self.page}-S[1-9][0-9]*", self.url):
            raise ValueError("PDF locator must identify this document version, physical page and passage.")
        return self


class PdfFiling(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[PdfPassage] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def check_document(self):
        versions = {(d.document_version, d.ticker, d.quarter, d.published) for d in self.documents}
        if len(versions) != 1:
            raise ValueError("Import passages from one version of one filing.")
        if len({d.url for d in self.documents}) != len(self.documents):
            raise ValueError("Each PDF passage needs a unique locator.")
        return self

    def passages(self):
        for doc in self.documents:
            yield doc.model_dump()


ResearchFiling = FilingText | PdfFiling
