"""Shared job schema and small value objects used across the pipeline."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from jobagg.normalize import normalize_company, normalize_title


class RemoteType(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class Language(StrEnum):
    CS = "cs"
    EN = "en"
    DE = "de"
    OTHER = "other"


class SalaryPeriod(StrEnum):
    YEAR = "year"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
    HOUR = "hour"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def make_job_id(company: str, title: str) -> str:
    """Stable dedup id derived from the normalized company and title.

    Exact matches collapse to the same id. Fuzzy matches are handled by
    ``jobagg.dedupe``, which re-assigns the id of an existing near-duplicate.
    """
    key = f"{normalize_company(company)}|{normalize_title(title)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class SourceRef(BaseModel):
    """One place a job was seen. A canonical job can carry several."""

    source: str
    url: str
    source_id: str | None = None

    def __hash__(self) -> int:
        return hash((self.source, self.url))


class Job(BaseModel):
    """One job listing, normalized to the shared schema.

    ``source``/``source_url`` describe the primary (richest) listing;
    ``extra_sources`` holds every other portal the same job was found on.
    """

    id: str = ""
    source: str
    source_url: str
    source_id: str | None = None
    title: str
    company: str
    location: str | None = None
    remote_type: RemoteType = RemoteType.UNKNOWN
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None
    description: str = ""
    tech_tags: list[str] = Field(default_factory=list)
    language: Language = Language.OTHER
    posted_at: date | None = None
    scraped_at: datetime = Field(default_factory=utcnow)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    extra_sources: list[SourceRef] = Field(default_factory=list)
    score: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fill_id(self) -> Job:
        self.title = " ".join(self.title.split())
        self.company = " ".join(self.company.split())
        if not self.id:
            self.id = make_job_id(self.company, self.title)
        return self

    @property
    def company_norm(self) -> str:
        return normalize_company(self.company)

    @property
    def title_norm(self) -> str:
        return normalize_title(self.title)

    @property
    def primary_source(self) -> SourceRef:
        return SourceRef(source=self.source, url=self.source_url, source_id=self.source_id)

    @property
    def all_sources(self) -> list[SourceRef]:
        seen: set[tuple[str, str]] = set()
        out: list[SourceRef] = []
        for ref in [self.primary_source, *self.extra_sources]:
            key = (ref.source, ref.url)
            if key not in seen:
                seen.add(key)
                out.append(ref)
        return out

    @property
    def has_salary(self) -> bool:
        return self.salary_min is not None or self.salary_max is not None

    def salary_text(self) -> str:
        if not self.has_salary:
            return ""
        lo = f"{self.salary_min:,.0f}" if self.salary_min is not None else "?"
        hi = f"{self.salary_max:,.0f}" if self.salary_max is not None else "?"
        rng = lo if lo == hi else f"{lo}-{hi}"
        cur = self.salary_currency or ""
        per = f"/{self.salary_period.value}" if self.salary_period else ""
        return f"{rng} {cur}{per}".strip()


class SearchQuery(BaseModel):
    """What to ask a source for. Adapters map this onto their own parameters."""

    term: str
    location: str | None = None
    remote: bool = False
    max_age_days: int = 14

    def label(self) -> str:
        loc = self.location or "anywhere"
        return f"'{self.term}' @ {loc}{' (remote)' if self.remote else ''}"
