"""Remotive (remote jobs board).

Method: the public JSON API ``https://remotive.com/api/remote-jobs`` with
``category``, ``search`` and ``limit`` parameters (documented, no key needed).
Every listing is remote; ``candidate_required_location`` is filtered against
``allowed_locations`` so US-only roles are dropped.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from jobagg.config import AppConfig
from jobagg.models import Job, Language, RemoteType, SearchQuery
from jobagg.normalize import collapse_ws, detect_language, markdown_to_text, parse_salary_cz
from jobagg.sources.base import Source

log = logging.getLogger(__name__)

API_URL = "https://remotive.com/api/remote-jobs"
SOURCE = "remotive.com"


class RemotiveSettings(BaseModel):
    category: str = "software-dev"
    limit: int = 50
    allowed_locations: list[str] = Field(default_factory=lambda: [
        "worldwide", "europe", "emea", "czech", "eu", "anywhere",
    ])
    # Remotive's search is loose (customer-service roles come back for "Vue developer"),
    # so a listing must mention one of these in its title, tags or description.
    require_keywords: list[str] = Field(default_factory=lambda: [
        "vue", "nuxt", "typescript", "javascript", "frontend", "front-end", "front end",
        "react", "node", "full-stack", "fullstack", "full stack", "web developer",
    ])


def location_allowed(required: str | None, allowed: list[str]) -> bool:
    if not required:
        return True
    text = required.lower()
    return any(a in text for a in allowed)


def mentions_any(keywords: list[str], *texts: str | None) -> bool:
    if not keywords:
        return True
    blob = " ".join(t for t in texts if t).lower()
    return any(k.lower() in blob for k in keywords)


def parse_job(item: dict[str, Any], tagger) -> Job:
    title = collapse_ws(str(item.get("title") or ""))
    description = markdown_to_text(str(item.get("description") or ""))
    tags = item.get("tags") or []
    salary = parse_salary_cz(str(item.get("salary") or "")) if item.get("salary") else None
    posted = None
    if item.get("publication_date"):
        try:
            posted = datetime.fromisoformat(str(item["publication_date"])).date()
        except ValueError:
            posted = None
    return Job(
        source=SOURCE,
        source_url=str(item.get("url") or ""),
        source_id=str(item.get("id") or "") or None,
        title=title or "(untitled)",
        company=collapse_ws(str(item.get("company_name") or "")) or "(unknown company)",
        location=str(item.get("candidate_required_location") or "") or None,
        remote_type=RemoteType.REMOTE,
        salary_min=salary[0] if salary else None,
        salary_max=salary[1] if salary else None,
        salary_currency=salary[2] if salary else None,
        salary_period=salary[3] if salary else None,  # type: ignore[arg-type]
        description=description,
        tech_tags=tagger(title, " ".join(map(str, tags)), description),
        language=Language(detect_language(title, description)),
        posted_at=posted,
    )


class RemotiveSource(Source):
    name = "remotive"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = RemotiveSettings.model_validate(settings)

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        terms: list[str] = []
        for q in base:
            if q.term.lower() not in [t.lower() for t in terms]:
                terms.append(q.term)
        return [SearchQuery(term=t, remote=True, max_age_days=self.app.filters.max_age_days)
                for t in terms]

    def fetch(self, query: SearchQuery) -> list[Job]:
        response = self.get(API_URL, params={"category": self.cfg.category,
                                             "search": query.term, "limit": self.cfg.limit})
        items = response.json().get("jobs", [])
        jobs: list[Job] = []
        for item in items:
            if not location_allowed(item.get("candidate_required_location"),
                                    self.cfg.allowed_locations):
                continue
            if not mentions_any(self.cfg.require_keywords, item.get("title"),
                                " ".join(map(str, item.get("tags") or [])),
                                item.get("description")):
                continue
            jobs.append(parse_job(item, self.tag))
        return jobs
