"""startupjobs.cz.

Method: the public offers sitemap ``/sitemap/offers.xml`` (allowed by robots.txt,
no dates), filtered by URL slug keywords, then the detail page of each offer not
already stored. Detail pages are server-rendered and carry a schema.org
JobPosting in JSON-LD (title, company, HTML description, salary, location,
skills). The page text also shows "Aktualizováno DD. MM. YYYY" (used as the
posting date, since ``datePosted`` can be years old for refreshed offers) and a
workplace line such as "Remote, On-site, Hybrid".

Not used on purpose: the listing page is a Nuxt app fed by
``back.startupjobs.cz``, whose robots.txt disallows all bots.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from pydantic import BaseModel, Field

from jobagg.config import AppConfig
from jobagg.models import Job, RemoteType, SearchQuery
from jobagg.normalize import parse_cz_date, strip_accents
from jobagg.sources.base import Source
from jobagg.sources.jsonld import find_job_posting, job_from_posting

log = logging.getLogger(__name__)

BASE_URL = "https://www.startupjobs.cz"
SITEMAP_URL = BASE_URL + "/sitemap/offers.xml"
SOURCE = "startupjobs.cz"

_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)
_UPDATED_RE = re.compile(r"Aktualizov[aá]no\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")
_WORKPLACE_RE = re.compile(
    r"(?m)^\s*((?:Remote|On-site|Hybrid)(?:\s*,\s*(?:Remote|On-site|Hybrid))*)\s*$"
)


class StartupjobsSettings(BaseModel):
    max_details: int = 30
    slug_keywords: list[str] = Field(default_factory=lambda: [
        "vue", "nuxt", "front", "typescript", "javascript", "react", "developer",
        "vyvojar", "programator", "fullstack", "full-stack", "web",
    ])


def sitemap_urls(xml: str) -> list[str]:
    return [u for u in _LOC_RE.findall(xml) if "/nabidka/" in u]


def slug_matches(url: str, keywords: list[str]) -> bool:
    slug = strip_accents(url.rsplit("/", 1)[-1]).lower()
    return any(k in slug for k in keywords)


def page_hints(html: str, today: date | None = None) -> tuple[date | None, RemoteType | None]:
    """(updated date, workplace type) from the rendered page text."""
    text = re.sub(r"<[^>]+>", "\n", html)
    updated = None
    m = _UPDATED_RE.search(text)
    if m:
        updated = parse_cz_date(m.group(1), today)
    remote: RemoteType | None = None
    m = _WORKPLACE_RE.search(text)
    if m:
        options = {o.strip().lower() for o in m.group(1).split(",")}
        if "remote" in options:
            remote = RemoteType.REMOTE
        elif "hybrid" in options:
            remote = RemoteType.HYBRID
        elif options == {"on-site"}:
            remote = RemoteType.ONSITE
    return updated, remote


def parse_detail(html: str, url: str, tagger, today: date | None = None) -> Job | None:
    posting = find_job_posting(html)
    if posting is None:
        return None
    updated, remote = page_hints(html, today)
    return job_from_posting(posting, source=SOURCE, url=url, tagger=tagger,
                            remote_hint=remote, posted_override=updated)


class StartupjobsSource(Source):
    name = "startupjobs"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = StartupjobsSettings.model_validate(settings)

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        return [SearchQuery(term="sitemap", max_age_days=self.app.filters.max_age_days)]

    def fetch(self, query: SearchQuery) -> list[Job]:
        urls = sitemap_urls(self.get(SITEMAP_URL).text)
        matched = [u for u in urls if slug_matches(u, self.cfg.slug_keywords)]
        log.info("startupjobs: %d offers in sitemap, %d match slug keywords", len(urls),
                 len(matched))
        jobs: list[Job] = []
        fetched = 0
        for url in matched:
            if self.is_known(url):
                self.mark_seen(url)
                continue
            if fetched >= self.cfg.max_details:
                break
            try:
                html = self.get(url).text
            except Exception as exc:  # noqa: BLE001
                log.warning("startupjobs: detail fetch failed for %s: %s", url, exc)
                continue
            fetched += 1
            job = parse_detail(html, url, self.tag)
            if job:
                jobs.append(job)
        return jobs
