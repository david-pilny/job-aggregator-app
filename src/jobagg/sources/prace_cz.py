"""prace.cz (Alma Career).

Method: HTML of the public listing ``/nabidky/[<city>/]?q=<term>`` (server-rendered
``article[id^=advert-]`` cards). robots.txt disallows ``/search/`` and ``/hledat/``
but allows ``/nabidky/``. A sitemap of all adverts exists but has no dates and no
metadata, so the search page is used. Detail pages are company-branded JS widgets
on ``*.jobs.cz`` without structured data, so they are not fetched.

Cards carry: title, company ("Název firmy"), locality ("Lokalita"), sometimes a
salary ("Mzda") and a "Nová nabídka" highlight; no posting date.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin

from pydantic import BaseModel, Field
from selectolax.parser import HTMLParser, Node

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

BASE_URL = "https://www.prace.cz"
SOURCE = "prace.cz"


class PraceCzSettings(BaseModel):
    locality_slugs: dict[str, str] = Field(default_factory=lambda: {
        "prague": "praha", "praha": "praha", "brno": "brno", "ostrava": "ostrava",
    })


def _labelled_items(card: Node) -> dict[str, str]:
    """li elements look like: <span class=accessibility-hidden>Lokalita:</span>Praha."""
    out: dict[str, str] = {}
    for li in card.css("li"):
        label_node = li.css_first(".accessibility-hidden")
        if label_node is None:
            continue
        label = strip_accents(collapse_ws(label_node.text())).lower().rstrip(":")
        value = collapse_ws(li.text()).replace(collapse_ws(label_node.text()), "", 1).strip()
        if label and value:
            out[label] = value
    return out


def parse_card(card: Node, tagger: Callable[..., list[str]], base_url: str = BASE_URL
               ) -> Job | None:
    link = card.css_first("a[data-testid=advert-link]") or card.css_first("h2 a")
    if link is None:
        return None
    title = collapse_ws(link.text())
    href = link.attributes.get("href", "")
    if not title or not href:
        return None
    url = urljoin(base_url, href).split("?")[0]
    items = _labelled_items(card)
    company = items.get("nazev firmy", "")
    location = items.get("lokalita")
    salary = parse_salary_cz(items.get("mzda") or items.get("plat"))
    highlights = " ".join(
        collapse_ws(n.text()) for n in card.css("[data-testid^=search-results-item-highlights]")
    )
    card_id = (card.attributes.get("id") or "").removeprefix("advert-") or None
    return Job(
        source=SOURCE,
        source_url=url,
        source_id=card_id,
        title=title,
        company=company or "(unknown company)",
        location=location,
        remote_type=RemoteType(infer_remote_type(title, location, highlights)),
        salary_min=salary[0] if salary else None,
        salary_max=salary[1] if salary else None,
        salary_currency=salary[2] if salary else None,
        salary_period=SalaryPeriod(salary[3]) if salary else None,
        tech_tags=tagger(title),
        language=Language(detect_language(title)),
    )


def parse_search_page(html: str, tagger: Callable[..., list[str]], base_url: str = BASE_URL
                      ) -> list[Job]:
    tree = HTMLParser(html)
    jobs: list[Job] = []
    for card in tree.css("article[id^=advert-]"):
        job = parse_card(card, tagger, base_url)
        if job:
            jobs.append(job)
    return jobs


class PraceCzSource(Source):
    name = "prace_cz"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = PraceCzSettings.model_validate(settings)

    def _slug(self, location: str | None) -> str | None:
        loc = strip_accents(location or "").lower()
        for key, slug in self.cfg.locality_slugs.items():
            if key in loc:
                return slug
        return None

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
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
        path = f"/nabidky/{slug}/" if slug else "/nabidky/"
        response = self.get(BASE_URL + path, params={"q": query.term})
        return parse_search_page(response.text, self.tag)
