"""A bounded, request-local source for short UTF-8 filing extracts."""
import hashlib
import unicodedata
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FilingText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,11}$")
    quarter: str = Field(pattern=r"^[0-9]{4}-Q[1-4]$")
    published: date
    text: str = Field(min_length=1, max_length=49152)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value):
        if len(value.encode("utf-8")) > 49152:
            raise ValueError("Use a UTF-8 extract of at most 48 KiB.")
        value = value.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        if not value.strip() or any(unicodedata.category(c) in {"Cc", "Zl", "Zp"}
                                    and c not in "\n\t" for c in value):
            raise ValueError("Provide readable plain text.")
        lines = value.split("\n")
        if len(lines) > 1000 or any(len(line) > 1200 for line in lines):
            raise ValueError("Use up to 1000 lines of at most 1200 characters each.")
        return value

    def passages(self):
        version = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        for number, line in enumerate(self.text.split("\n"), start=1):
            if line.strip():
                yield {"ticker": self.ticker, "quarter": self.quarter, "published": self.published.isoformat(),
                       "excerpt": line.strip(), "url": f"#filing-{version}-L{number}",
                       "line": number, "source": "uploaded_text"}
