"""welcometothejungle.com (Czech listings).

Method: the job sitemaps (``/sitemaps/index.xml.gz`` -> ``job-listings.N.xml.gz``,
each ~10k URLs with ``lastmod``), filtered by URL slug: the slug ends with the
city (``..._prague``), and a keyword list keeps only developer-ish titles. New
matches are then fetched once; detail pages carry a schema.org JobPosting in
JSON-LD. robots.txt disallows every URL with a query string, including search
(``/jobs?query=``), so search and the Algolia backend behind it are not used.

Cost: about ten gzipped sitemaps (~25 MB) per run, then only new detail pages.
"""

from __future__ import annotations

import gzip
import logging
import re
from datetime import date, timedelta

from pydantic import BaseModel, Field

from jobagg.config import AppConfig
from jobagg.models import Job, SearchQuery
from jobagg.normalize import strip_accents
from jobagg.sources.base import Source
from jobagg.sources.jsonld import find_job_posting, job_from_posting

log = logging.getLogger(__name__)

INDEX_URL = "https://www.welcometothejungle.com/sitemaps/index.xml.gz"
SOURCE = "welcometothejungle.com"
_ENTRY_RE = re.compile(r"<url>\s*<loc>(.*?)</loc>(?:.*?<lastmod>(.*?)</lastmod>)?.*?</url>", re.S)
_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)


class WttjSettings(BaseModel):
    slug_cities: list[str] = Field(default_factory=lambda: ["prague", "praha", "brno", "ostrava",
                                                           "czech"])
    slug_keywords: list[str] = Field(default_factory=lambda: [
        "vue", "nuxt", "front", "typescript", "javascript", "react", "developer",
        "fullstack", "full-stack", "web-engineer", "software-engineer",
    ])
    max_details: int = 20


def decode(content: bytes) -> str:
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    return content.decode("utf-8", errors="replace")


def job_sitemaps(index_xml: str) -> list[str]:
    return [u for u in _LOC_RE.findall(index_xml) if "job-listings" in u]


def sitemap_entries(xml: str) -> list[tuple[str, date | None]]:
    out: list[tuple[str, date | None]] = []
    for url, lastmod in _ENTRY_RE.findall(xml):
        d = None
        if lastmod:
            try:
                d = date.fromisoformat(lastmod.strip()[:10])
            except ValueError:
                d = None
        out.append((url.strip(), d))
    return out


def slug_matches(url: str, cities: list[str], keywords: list[str]) -> bool:
    slug = strip_accents(url.rsplit("/jobs/", 1)[-1]).lower()
    if "/jobs/" not in url:
        return False
    return any(c in slug for c in cities) and any(k in slug for k in keywords)


def parse_detail(html: str, url: str, tagger) -> Job | None:
    posting = find_job_posting(html)
    if posting is None:
        return None
    return job_from_posting(posting, source=SOURCE, url=url, tagger=tagger)


class WttjSource(Source):
    name = "wttj"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = WttjSettings.model_validate(settings)

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        return [SearchQuery(term="sitemap", max_age_days=self.app.filters.max_age_days)]

    def fetch(self, query: SearchQuery) -> list[Job]:
        cutoff = date.today() - timedelta(days=query.max_age_days)
        index = decode(self.get(INDEX_URL).content)
        candidates: list[str] = []
        total = 0
        for sitemap in job_sitemaps(index):
            entries = sitemap_entries(decode(self.get(sitemap).content))
            total += len(entries)
            for url, lastmod in entries:
                if lastmod and lastmod < cutoff:
                    continue
                if slug_matches(url, self.cfg.slug_cities, self.cfg.slug_keywords):
                    candidates.append(url)
        log.info("wttj: %d sitemap entries, %d candidate Czech dev listings", total,
                 len(candidates))
        jobs: list[Job] = []
        fetched = 0
        for url in candidates:
            if self.is_known(url):
                self.mark_seen(url)
                continue
            if fetched >= self.cfg.max_details:
                break
            try:
                html = self.get(url).text
            except Exception as exc:  # noqa: BLE001
                log.warning("wttj: detail fetch failed for %s: %s", url, exc)
                continue
            fetched += 1
            job = parse_detail(html, url, self.tag)
            if job:
                jobs.append(job)
        return jobs
