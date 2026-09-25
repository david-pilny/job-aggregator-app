"""jobs.cz (Alma Career).

Method: HTML of the public search page ``/prace/[<city>/]?q[]=<term>``, which is
server-rendered (``article.SearchResultCard``). Checked alternatives: there is no
RSS or per-search sitemap, and the internal ``/api/`` and ``/iapi/`` endpoints are
disallowed by robots.txt, so they are deliberately not used. Detail pages mostly
redirect to company-branded JS widgets without structured data, so descriptions
are not fetched; tech tags come from the title only.

Cards carry: title, company, locality, posting date ("Přidáno včera", "9. září"),
salary tag ("70 000 – 90 000 Kč") and remote tags ("Práce převážně z domova",
"Možnost občasné práce z domova").
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from pydantic import BaseModel, Field
from selectolax.parser import HTMLParser, Node

from jobagg.config import AppConfig
from jobagg.models import Job, Language, RemoteType, SalaryPeriod, SearchQuery
from jobagg.normalize import (
    collapse_ws,
    detect_language,
    infer_remote_type,
    parse_cz_date,
    parse_salary_cz,
    strip_accents,
)
from jobagg.sources.base import Source

BASE_URL = "https://www.jobs.cz"
SOURCE = "jobs.cz"


class JobsCzSettings(BaseModel):
    pages: int = 1
    # Substring of the configured location (lowercase, accents stripped) -> URL slug.
    locality_slugs: dict[str, str] = Field(default_factory=lambda: {
        "prague": "praha", "praha": "praha", "brno": "brno", "ostrava": "ostrava",
    })


def _remote_from_tags(tags: list[str]) -> RemoteType | None:
    joined = strip_accents(" ".join(tags)).lower()
    if "obcasne" in joined:
        return RemoteType.HYBRID
    if "z domova" in joined or "remote" in joined:
        return RemoteType.REMOTE
    return None


def parse_card(card: Node, tagger: Callable[..., list[str]], today: date | None = None
               ) -> Job | None:
    link = card.css_first("a[data-jobad-id]")
    if link is None:
        return None
    title = collapse_ws(link.text())
    url = (link.attributes.get("href") or "").split("?")[0]
    if not title or not url:
        return None
    footer = [collapse_ws(li.text()) for li in card.css(".SearchResultCard__footerItem")]
    footer = [f for f in footer if f and "atmoskop" not in f.lower()]
    company = footer[0] if footer else ""
    location = footer[1] if len(footer) > 1 else None
    status = card.css_first(".SearchResultCard__status")
    posted = parse_cz_date(status.text() if status else None, today)
    tags = [collapse_ws(t.text()) for t in card.css(".SearchResultCard__body .Tag")]
    salary = next((parse_salary_cz(t) for t in tags if parse_salary_cz(t)), None)
    remote = _remote_from_tags(tags) or RemoteType(infer_remote_type(title, location))
    return Job(
        source=SOURCE,
        source_url=url,
        source_id=link.attributes.get("data-jobad-id"),
        title=title,
        company=company or "(unknown company)",
        location=location,
        remote_type=remote,
        salary_min=salary[0] if salary else None,
        salary_max=salary[1] if salary else None,
        salary_currency=salary[2] if salary else None,
        salary_period=SalaryPeriod(salary[3]) if salary else None,
        tech_tags=tagger(title),
        language=Language(detect_language(title)),
        posted_at=posted,
    )


def parse_search_page(html: str, tagger: Callable[..., list[str]], today: date | None = None
                      ) -> list[Job]:
    tree = HTMLParser(html)
    jobs: list[Job] = []
    for card in tree.css("article.SearchResultCard"):
        job = parse_card(card, tagger, today)
        if job:
            jobs.append(job)
    return jobs


class JobsCzSource(Source):
    name = "jobs_cz"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = JobsCzSettings.model_validate(settings)

    def _slug(self, location: str | None) -> str | None:
        loc = strip_accents(location or "").lower()
        for key, slug in self.cfg.locality_slugs.items():
            if key in loc:
                return slug
        return None

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        # Collapse locations that map to the same slug (e.g. two country-wide queries).
        seen: set[tuple[str, str | None]] = set()
        out: list[SearchQuery] = []
        for q in base:
            key = (q.term.lower(), self._slug(q.location))
            if key not in seen:
                seen.add(key)
                out.append(q)
        return out

    def fetch(self, query: SearchQuery) -> list[Job]:
        slug = self._slug(query.location)
        path = f"/prace/{slug}/" if slug else "/prace/"
        jobs: list[Job] = []
        for page in range(1, self.cfg.pages + 1):
            params: dict[str, str | int] = {"q[]": query.term}
            if page > 1:
                params["page"] = page
            response = self.get(BASE_URL + path, params=params)
            found = parse_search_page(response.text, self.tag)
            if not found:
                break
            jobs.extend(found)
        return jobs
