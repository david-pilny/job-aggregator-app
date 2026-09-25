"""Arbeitnow (German-centric board with a public API).

Method: the public JSON API ``https://www.arbeitnow.com/api/job-board-api``
with ``search`` and ``page`` parameters (documented, no key). Listings are kept
when they are flagged remote or located in Czechia; ``created_at`` is a unix
timestamp; descriptions are HTML.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from jobagg.config import AppConfig
from jobagg.models import Job, Language, RemoteType, SearchQuery
from jobagg.normalize import collapse_ws, detect_language, infer_remote_type, markdown_to_text
from jobagg.sources.base import Source
from jobagg.sources.remotive import mentions_any

log = logging.getLogger(__name__)

API_URL = "https://www.arbeitnow.com/api/job-board-api"
SOURCE = "arbeitnow.com"


class ArbeitnowSettings(BaseModel):
    pages: int = 1
    keep_locations: list[str] = Field(default_factory=lambda: ["czech", "prague", "praha", "brno"])
    # The API search is loose; a listing must mention one of these in title/tags/description.
    require_keywords: list[str] = Field(default_factory=lambda: [
        "vue", "nuxt", "typescript", "javascript", "frontend", "front-end", "front end",
        "react", "node", "full-stack", "fullstack", "full stack", "webentwickler",
        "web developer",
    ])


def keep(item: dict[str, Any], locations: list[str], require_keywords: list[str] | None = None
         ) -> bool:
    is_remote = item.get("remote") in (True, "True", "true", 1)
    loc = str(item.get("location") or "").lower()
    if not is_remote and not any(k in loc for k in locations):
        return False
    return mentions_any(require_keywords or [], item.get("title"),
                        " ".join(map(str, item.get("tags") or [])), item.get("description"))


def parse_job(item: dict[str, Any], tagger) -> Job:
    title = collapse_ws(str(item.get("title") or ""))
    description = markdown_to_text(str(item.get("description") or ""))
    location = str(item.get("location") or "") or None
    is_remote = item.get("remote") in (True, "True", "true", 1)
    posted = None
    if item.get("created_at"):
        try:
            posted = datetime.fromtimestamp(int(item["created_at"]), tz=UTC).date()
        except (ValueError, TypeError, OSError):
            posted = None
    tags = item.get("tags") or []
    return Job(
        source=SOURCE,
        source_url=str(item.get("url") or ""),
        source_id=str(item.get("slug") or "") or None,
        title=title or "(untitled)",
        company=collapse_ws(str(item.get("company_name") or "")) or "(unknown company)",
        location=location,
        remote_type=RemoteType.REMOTE if is_remote
        else RemoteType(infer_remote_type(title, location, description)),
        description=description,
        tech_tags=tagger(title, " ".join(map(str, tags)), description),
        language=Language(detect_language(title, description)),
        posted_at=posted,
    )


class ArbeitnowSource(Source):
    name = "arbeitnow"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = ArbeitnowSettings.model_validate(settings)

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        terms: list[str] = []
        for q in base:
            if q.term.lower() not in [t.lower() for t in terms]:
                terms.append(q.term)
        return [SearchQuery(term=t, remote=True, max_age_days=self.app.filters.max_age_days)
                for t in terms]

    def fetch(self, query: SearchQuery) -> list[Job]:
        jobs: list[Job] = []
        for page in range(1, self.cfg.pages + 1):
            response = self.get(API_URL, params={"search": query.term, "page": page})
            payload = response.json()
            for item in payload.get("data", []):
                if keep(item, self.cfg.keep_locations, self.cfg.require_keywords):
                    jobs.append(parse_job(item, self.tag))
            if not (payload.get("links") or {}).get("next"):
                break
        return jobs
