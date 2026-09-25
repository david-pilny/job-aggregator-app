"""We Work Remotely.

Method: the public category RSS feeds
``https://weworkremotely.com/categories/<category>.rss`` (e.g.
``remote-front-end-programming-jobs``, ``remote-full-stack-programming-jobs``).
Items carry ``<title>`` as "Company: Title", ``<region>``, ``<skills>``,
``<type>``, ``<pubDate>``, ``<link>`` and an HTML ``<description>``. Items whose
region does not match ``allowed_regions`` (e.g. "North America Only") are dropped.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

from pydantic import BaseModel, Field

from jobagg.config import AppConfig
from jobagg.models import Job, Language, RemoteType, SearchQuery
from jobagg.normalize import collapse_ws, detect_language, markdown_to_text
from jobagg.sources.base import Source

log = logging.getLogger(__name__)

FEED_URL = "https://weworkremotely.com/categories/{feed}.rss"
SOURCE = "weworkremotely.com"
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
_FIELD_RE = re.compile(r"<(\w+)>(.*?)</\1>", re.S)


class WwrSettings(BaseModel):
    feeds: list[str] = Field(default_factory=lambda: [
        "remote-front-end-programming-jobs", "remote-full-stack-programming-jobs",
    ])
    allowed_regions: list[str] = Field(default_factory=lambda: [
        "anywhere", "europe", "emea", "worldwide",
    ])


def _clean(value: str) -> str:
    value = re.sub(r"^\s*<!\[CDATA\[(.*?)\]\]>\s*$", r"\1", value, flags=re.S)
    return unescape(value).strip()


def parse_feed(xml: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for block in _ITEM_RE.findall(xml):
        fields: dict[str, str] = {}
        for tag, value in _FIELD_RE.findall(block):
            fields.setdefault(tag, _clean(value))
        if fields.get("title") and fields.get("link"):
            items.append(fields)
    return items


def region_allowed(region: str | None, allowed: list[str]) -> bool:
    if not region:
        return True
    text = region.lower()
    return any(a in text for a in allowed)


def parse_job(item: dict[str, Any], tagger) -> Job:
    raw_title = collapse_ws(item.get("title", ""))
    company, _, title = raw_title.partition(": ")
    if not title:
        company, title = "", raw_title
    description = markdown_to_text(item.get("description", ""))
    posted = None
    if item.get("pubDate"):
        try:
            posted = parsedate_to_datetime(item["pubDate"]).date()
        except (ValueError, TypeError):
            try:
                posted = datetime.fromisoformat(item["pubDate"]).date()
            except ValueError:
                posted = None
    return Job(
        source=SOURCE,
        source_url=item["link"],
        source_id=item.get("guid") or None,
        title=title or "(untitled)",
        company=company or "(unknown company)",
        location=item.get("region") or None,
        remote_type=RemoteType.REMOTE,
        description=description,
        tech_tags=tagger(title, item.get("skills", ""), description),
        language=Language(detect_language(title, description)),
        posted_at=posted,
    )


class WwrSource(Source):
    name = "weworkremotely"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = WwrSettings.model_validate(settings)

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        return [SearchQuery(term=feed, remote=True, max_age_days=self.app.filters.max_age_days)
                for feed in self.cfg.feeds]

    def fetch(self, query: SearchQuery) -> list[Job]:
        xml = self.get(FEED_URL.format(feed=query.term)).text
        jobs: list[Job] = []
        for item in parse_feed(xml):
            if region_allowed(item.get("region"), self.cfg.allowed_regions):
                jobs.append(parse_job(item, self.tag))
        return jobs
