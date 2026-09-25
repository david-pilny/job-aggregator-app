"""jobstack.it (Czech IT board).

Method: HTML of the public category pages ``/it-jobs/<category>[/<location>]``
(server-rendered ``li.jobposts-item``). robots.txt allows them; the sitemap lists
jobs but without dates; no JSON API was found. Cards already carry title,
company, city, salary ("až 165 000 Kč / měsíc"), contract type, a
Hybrid/Remote label and seniority labels, so detail pages are not fetched.

The global search terms are ignored: jobstack is browsed by its own categories
(``categories`` in config), optionally per location ("praha", "brno", "remote").
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin

from pydantic import BaseModel, Field
from selectolax.parser import HTMLParser, Node

from jobagg.config import AppConfig
from jobagg.models import Job, Language, RemoteType, SalaryPeriod, SearchQuery
from jobagg.normalize import collapse_ws, detect_language, infer_remote_type, parse_salary_cz
from jobagg.sources.base import Source

BASE_URL = "https://www.jobstack.it"
SOURCE = "jobstack.it"


class JobstackSettings(BaseModel):
    categories: list[str] = Field(default_factory=lambda: [
        "vue-js-developer", "javascript-developer", "react-developer",
        "node-js-developer", "full-stack-developer", "web-koder",
    ])
    locations: list[str] = Field(default_factory=lambda: [""])
    pages: int = 1


def _label_texts(item: Node) -> list[str]:
    return [collapse_ws(s.text()) for s in item.css(".custom-profile-label")]


def parse_item(item: Node, tagger: Callable[..., list[str]], base_url: str = BASE_URL
               ) -> Job | None:
    link = item.css_first("a.jobpost-mainlink") or item.css_first("a[href]")
    heading = item.css_first("h3")
    if link is None or heading is None:
        return None
    title = collapse_ws(heading.text())
    url = urljoin(base_url, link.attributes.get("href", ""))
    company = ""
    city = None
    for span in item.css(".custom-profile-label--secondary"):
        text = collapse_ws(span.text())
        if span.css_first("[class*=building]"):
            company = text
        elif span.css_first("[class*=pin]"):
            city = text
    labels = _label_texts(item)
    remote_label = next((lb for lb in labels if lb.lower() in ("remote", "hybrid", "home office")),
                        None)
    if remote_label:
        remote = RemoteType.HYBRID if remote_label.lower() == "hybrid" else RemoteType.REMOTE
    else:
        remote = RemoteType(infer_remote_type(title, city))
    salary_node = item.css_first(".jobposts-item_salary")
    salary = parse_salary_cz(salary_node.text() if salary_node else None)
    seniority = [lb for lb in labels if lb in ("Junior", "Medior", "Senior")]
    description = f"Seniority: {', '.join(seniority)}" if seniority else ""
    return Job(
        source=SOURCE,
        source_url=url,
        source_id=url.rstrip("/").rsplit("/", 1)[-1] or None,
        title=title,
        company=company or "(unknown company)",
        location=city,
        remote_type=remote,
        salary_min=salary[0] if salary else None,
        salary_max=salary[1] if salary else None,
        salary_currency=salary[2] if salary else None,
        salary_period=SalaryPeriod(salary[3]) if salary else None,
        description=description,
        tech_tags=tagger(title, " ".join(labels)),
        language=Language(detect_language(title)),
    )


def parse_listing(html: str, tagger: Callable[..., list[str]], base_url: str = BASE_URL
                  ) -> list[Job]:
    tree = HTMLParser(html)
    jobs: list[Job] = []
    for item in tree.css("li.jobposts-item"):
        job = parse_item(item, tagger, base_url)
        if job:
            jobs.append(job)
    return jobs


class JobstackSource(Source):
    name = "jobstack"
    produces = (SOURCE,)

    def __init__(self, settings: dict, app: AppConfig) -> None:
        super().__init__(settings, app)
        self.cfg = JobstackSettings.model_validate(settings)

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        return [SearchQuery(term=cat, location=loc or None, remote=(loc == "remote"),
                            max_age_days=self.app.filters.max_age_days)
                for cat in self.cfg.categories for loc in self.cfg.locations]

    def fetch(self, query: SearchQuery) -> list[Job]:
        path = f"/it-jobs/{query.term}" + (f"/{query.location}" if query.location else "")
        jobs: list[Job] = []
        for page in range(1, self.cfg.pages + 1):
            params = {"page": page} if page > 1 else None
            response = self.get(BASE_URL + path, params=params)
            found = parse_listing(response.text, self.tag)
            if not found:
                break
            jobs.extend(found)
        return jobs
