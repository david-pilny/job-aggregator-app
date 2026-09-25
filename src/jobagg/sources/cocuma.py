"""cocuma.cz (Czech company-culture job board).

Method: HTML of the unfiltered list ``/jobs/`` and ``/jobs/page/<n>/``
(server-rendered ``a.job-thumbnail`` cards), filtered locally by title keywords,
then the detail page ``/job/<slug>/<id>/`` for matches not already stored (title,
lead, description, sidebar with contract type / salary). robots.txt disallows
search (``/jobs/?q=``) and city/county filters, so the plain list is paged
instead; no feed, sitemap of jobs, or JSON endpoint was found.

The global search terms are ignored; ``title_keywords`` decides which cards are
worth a detail request. Cards show a "Fresh" badge for recent listings; there is
no posting date.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from urllib.parse import urljoin

from pydantic import BaseModel, Field
from selectolax.parser import HTMLParser

from jobagg.config import AppConfig
from jobagg.models import Job, Language, RemoteType, SalaryPeriod, SearchQuery
from jobagg.normalize import (
    collapse_ws,
    detect_language,
    infer_remote_type,
    parse_salary_cz,
    strip_accents,
)
from jobagg.sources.base import Source

log = logging.getLogger(__name__)

BASE_URL = "https://www.cocuma.cz"
SOURCE = "cocuma.cz"
_APPLY_MARKER = "Mám zájem o tuto příležitost"


class CocumaSettings(BaseModel):
    pages: int = 15
    max_details: int = 30
    fetch_details: bool = True
    title_keywords: list[str] = Field(default_factory=lambda: [
        "vue", "nuxt", "front", "typescript", "javascript", "react", "develop",
        "vyvojar", "programator", "engineer", "fullstack", "full-stack", "web",
    ])


class Card(BaseModel):
    url: str
    title: str
    company: str
    city: str | None = None
    fresh: bool = False


def parse_list(html: str, base_url: str = BASE_URL) -> list[Card]:
    tree = HTMLParser(html)
    cards: list[Card] = []
    for a in tree.css("a.job-thumbnail"):
        title = a.css_first(".job-thumbnail-title")
        company = a.css_first(".job-thumbnail-company")
        city = a.css_first(".job-thumbnail-city")
        href = a.attributes.get("href")
        if not (title and href) or "/job/" not in href:
            continue  # "/s/..." thumbnails are promoted pages, not listings
        cards.append(Card(
            url=urljoin(base_url, href),
            title=collapse_ws(title.text()),
            company=collapse_ws(company.text()) if company else "",
            city=collapse_ws(city.text()) if city else None,
            fresh="fresh" in collapse_ws(a.text()).lower()[:40],
        ))
    return cards


def parse_detail(html: str) -> tuple[str, str]:
    """Return (description text, sidebar text) from a job detail page."""
    tree = HTMLParser(html)
    for tag in tree.css("script, style, nav, footer, header"):
        tag.decompose()
    h1 = tree.css_first("h1")
    sidebar = tree.css_first(".job-sidebar")
    sidebar_text = collapse_ws(sidebar.text(separator=" ")) if sidebar else ""
    body = tree.body.text(separator="\n") if tree.body else ""
    text = re.sub(r"[ \t]+", " ", body)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if h1:
        start = text.find(collapse_ws(h1.text()))
        if start >= 0:
            text = text[start:]
    end = text.rfind(_APPLY_MARKER)
    if end > 0:
        text = text[:end]
    text = text.replace(_APPLY_MARKER, "")  # the apply button also sits mid-page
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip(), sidebar_text


def _matches(title: str, keywords: list[str]) -> bool:
    plain = strip_accents(title).lower()
    return any(strip_accents(k).lower() in plain for k in keywords)


class CocumaSource(Source):
    name = "cocuma"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = CocumaSettings.model_validate(settings)

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        return [SearchQuery(term="*", max_age_days=self.app.filters.max_age_days)]

    def build_job(self, card: Card, tagger: Callable[..., list[str]],
                  detail_html: str | None = None) -> Job:
        description, sidebar = parse_detail(detail_html) if detail_html else ("", "")
        salary = parse_salary_cz(sidebar) or parse_salary_cz(description[:600])
        remote = RemoteType(infer_remote_type(card.title, card.city, f"{sidebar} {description}"))
        return Job(
            source=SOURCE,
            source_url=card.url,
            source_id=card.url.rstrip("/").rsplit("/", 1)[-1] or None,
            title=card.title,
            company=card.company or "(unknown company)",
            location=card.city,
            remote_type=remote,
            salary_min=salary[0] if salary else None,
            salary_max=salary[1] if salary else None,
            salary_currency=salary[2] if salary else None,
            salary_period=SalaryPeriod(salary[3]) if salary else None,
            description=description,
            tech_tags=tagger(card.title, description),
            language=Language(detect_language(card.title, description)),
        )

    def fetch(self, query: SearchQuery) -> list[Job]:
        cards: list[Card] = []
        for page in range(1, self.cfg.pages + 1):
            url = BASE_URL + ("/jobs/" if page == 1 else f"/jobs/page/{page}/")
            try:
                response = self.get(url)
            except Exception as exc:  # noqa: BLE001 - past the last page or transient
                log.info("cocuma: stopping at page %d (%s)", page, exc)
                break
            found = parse_list(response.text)
            if not found:
                break
            cards.extend(found)
        matched = [c for c in cards if _matches(c.title, self.cfg.title_keywords)]
        log.info("cocuma: %d cards on %d page(s), %d match title keywords",
                 len(cards), page, len(matched))
        jobs: list[Job] = []
        details = 0
        for card in matched:
            if self.is_known(card.url):
                self.mark_seen(card.url)
                continue
            html = None
            if self.cfg.fetch_details and details < self.cfg.max_details:
                try:
                    html = self.get(card.url).text
                    details += 1
                except Exception as exc:  # noqa: BLE001
                    log.warning("cocuma: detail fetch failed for %s: %s", card.url, exc)
            jobs.append(self.build_job(card, self.tag, html))
        return jobs
