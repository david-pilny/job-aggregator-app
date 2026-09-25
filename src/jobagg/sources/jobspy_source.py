"""LinkedIn, Indeed and Google Jobs via python-jobspy.

Method: the ``jobspy`` library (guest/public endpoints, no login). One
``scrape_jobs`` call per (site, query) so a failing site never takes the others
down and so we can pause between calls. LinkedIn rate-limits aggressively:
keep ``results_wanted`` small, leave ``linkedin_fetch_description`` off unless
you need full text, and add proxies in config only if you really need them.

Site quirks handled here (verified against jobspy 1.1.82):
- Indeed cannot combine ``hours_old`` with ``is_remote``, and its remote filter
  returns nothing for Czechia anyway, so Indeed always gets the age filter and
  remote-ness comes from Indeed's own flag plus our text heuristics. LinkedIn
  accepts both filters; jobs returned by a remote-filtered LinkedIn query are
  marked remote when nothing in the text says otherwise.
- LinkedIn crashes on job locations in countries jobspy does not know
  ("Invalid country string"), so ``Country.from_string`` is patched to fall back
  to WORLDWIDE. Also, LinkedIn resolves the location "Czech Republic" to the
  Dominican Republic; use "Czechia" or "Prague" in config.
- Google Jobs ignores ``location`` and needs a natural-language search term. From
  many networks Google serves a JavaScript-only page and the scraper finds no
  results ("initial cursor not found"); it is therefore off by default.
- LinkedIn returns no description unless ``linkedin_fetch_description`` is on.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from jobagg.config import AppConfig
from jobagg.models import Job, Language, RemoteType, SalaryPeriod, SearchQuery
from jobagg.normalize import (
    collapse_ws,
    compile_tag_patterns,
    detect_language,
    extract_tech_tags,
    infer_remote_type,
    markdown_to_text,
)
from jobagg.sources.base import Source, polite_sleep

log = logging.getLogger(__name__)


def _patch_jobspy_country_fallback() -> None:
    """Make jobspy tolerate job locations in countries it does not list."""
    from jobspy.model import Country

    if getattr(Country, "_jobagg_patched", False):
        return
    original = Country.from_string.__func__  # type: ignore[attr-defined]

    def safe_from_string(cls: type[Country], value: str) -> Country:
        try:
            return original(cls, value)
        except ValueError:
            return cls.WORLDWIDE

    Country.from_string = classmethod(safe_from_string)  # type: ignore[method-assign]
    Country._jobagg_patched = True  # type: ignore[attr-defined]


_PERIODS = {
    "yearly": SalaryPeriod.YEAR,
    "monthly": SalaryPeriod.MONTH,
    "weekly": SalaryPeriod.WEEK,
    "daily": SalaryPeriod.DAY,
    "hourly": SalaryPeriod.HOUR,
}


class ExtraSearch(BaseModel):
    term: str
    location: str | None = None
    remote: bool = False
    sites: list[str] | None = None


class JobSpySettings(BaseModel):
    sites: list[str] = Field(default_factory=lambda: ["linkedin", "indeed", "google"])
    country_indeed: str = "czech republic"
    results_wanted: int = 20
    hours_old: int | None = None
    linkedin_fetch_description: bool = False
    delay_seconds: tuple[float, float] = (3.0, 6.0)
    proxies: list[str] = Field(default_factory=list)
    extra_searches: list[ExtraSearch] = Field(default_factory=list)


def _clean(value: Any) -> Any:
    """Turn pandas' NaN/NaT/empty into None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    try:  # pandas NaT / numpy NaN
        import pandas as pd

        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _to_date(value: Any) -> date | None:
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def row_to_job(row: Any, tag_patterns: dict[str, Any], scraped_at: datetime | None = None) -> Job:
    """Convert one jobspy DataFrame row (a Series or dict) to the shared schema."""
    get = row.get
    site = str(_clean(get("site")) or "jobspy")
    title = collapse_ws(_clean(get("title")) or "")
    company = collapse_ws(_clean(get("company")) or _clean(get("company_name")) or "")
    location = _clean(get("location"))
    description = markdown_to_text(_clean(get("description")))
    is_remote = _clean(get("is_remote"))
    remote_flag = bool(is_remote) if isinstance(is_remote, bool | int) else None
    interval = _clean(get("interval"))
    currency = _clean(get("currency"))
    salary_min = _to_float(get("min_amount"))
    salary_max = _to_float(get("max_amount"))
    url = str(_clean(get("job_url")) or _clean(get("job_url_direct")) or "")

    job = Job(
        source=site,
        source_url=url,
        source_id=str(_clean(get("id")) or "") or None,
        title=title or "(untitled)",
        company=company or "(unknown company)",
        location=str(location) if location else None,
        remote_type=RemoteType(infer_remote_type(title, location, description, remote_flag)),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=str(currency) if (currency and (salary_min or salary_max)) else None,
        salary_period=_PERIODS.get(str(interval).lower()) if interval else None,
        description=description,
        tech_tags=extract_tech_tags(f"{title}\n{description}", tag_patterns),
        language=Language(detect_language(title, description)),
        posted_at=_to_date(get("date_posted")),
    )
    if scraped_at:
        job.scraped_at = scraped_at
    return job


class JobSpySource(Source):
    name = "jobspy"
    produces: tuple[str, ...] = ("linkedin", "indeed", "google")

    def __init__(self, settings: dict[str, Any], app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = JobSpySettings.model_validate(settings)
        self.produces = tuple(self.cfg.sites)
        self.delay_range = self.cfg.delay_seconds
        self._tag_patterns = compile_tag_patterns(app.tech_tags)
        self._proxies = self.cfg.proxies or app.http.proxies or None

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        extra = [
            JobSpyQuery(term=e.term, location=e.location, remote=e.remote, sites=e.sites,
                        max_age_days=self.app.filters.max_age_days)
            for e in self.cfg.extra_searches
        ]
        return [*base, *extra]

    def fetch(self, query: SearchQuery) -> list[Job]:
        from jobspy import scrape_jobs

        _patch_jobspy_country_fallback()
        sites = getattr(query, "sites", None) or self.cfg.sites
        hours_old = self.cfg.hours_old or query.max_age_days * 24
        jobs: list[Job] = []
        for i, site in enumerate(sites):
            if i > 0:
                polite_sleep(self.delay_range)
            kwargs: dict[str, Any] = {
                "site_name": site,
                "search_term": query.term,
                "location": query.location,
                "results_wanted": self.cfg.results_wanted,
                "country_indeed": self.cfg.country_indeed,
                "description_format": "markdown",
                "linkedin_fetch_description": self.cfg.linkedin_fetch_description,
                "proxies": self._proxies,
                "user_agent": self.app.http.user_agent,
                "verbose": 0,
            }
            if site == "google":
                where = "remote" if query.remote else (query.location or "")
                kwargs["google_search_term"] = f"{query.term} jobs {where}".strip()
            elif site == "indeed":
                kwargs["hours_old"] = hours_old  # is_remote is useless for CZ, see module doc
            else:
                kwargs["hours_old"] = hours_old
                kwargs["is_remote"] = query.remote
            try:
                df = scrape_jobs(**kwargs)
            except Exception as exc:  # noqa: BLE001 - one site failing must not stop the rest
                log.error("jobspy/%s failed for %s: %s: %s", site, query.label(),
                          type(exc).__name__, exc)
                continue
            n_before = len(jobs)
            for _, row in df.iterrows():
                try:
                    job = row_to_job(row, self._tag_patterns)
                except Exception as exc:  # noqa: BLE001
                    log.warning("jobspy/%s: skipping malformed row: %s", site, exc)
                    continue
                if query.remote and site == "linkedin" and job.remote_type == RemoteType.UNKNOWN:
                    job.remote_type = RemoteType.REMOTE  # server-side remote filter applied
                jobs.append(job)
            log.info("jobspy/%s: %s -> %d rows", site, query.label(), len(jobs) - n_before)
        return jobs


class JobSpyQuery(SearchQuery):
    """A SearchQuery that can pin the sites it runs on (used for extra_searches)."""

    sites: list[str] | None = None
