"""Parser tests for every custom adapter, against saved fixtures (no network)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from jobagg.config import AppConfig
from jobagg.models import RemoteType, SearchQuery
from jobagg.normalize import compile_tag_patterns, extract_tech_tags
from jobagg.sources import (
    arbeitnow,
    cocuma,
    jobs_cz,
    jobstack,
    prace_cz,
    remotive,
    startupjobs,
    weworkremotely,
    wttj,
)
from jobagg.sources.jsonld import find_job_posting

FX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 9, 25)
_PATTERNS = compile_tag_patterns({
    "vue": ["vue.js", "vuejs", "vue 3"], "nuxt": [], "typescript": ["ts"],
    "javascript": ["js"], "react": ["react js", "react native"], "node.js": ["node", "nodejs"],
    "python": [], ".net": ["c#"], "php": [], "graphql": [],
})


def tagger(*texts: str | None) -> list[str]:
    return extract_tech_tags(" ".join(t for t in texts if t), _PATTERNS)


def read(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


@pytest.fixture
def app() -> AppConfig:
    return AppConfig.model_validate({"http": {"delay_seconds": [0, 0]}})


# --- jobs.cz -------------------------------------------------------------------

def test_jobs_cz_cards():
    jobs = jobs_cz.parse_search_page(read("jobs_cz_search.html"), tagger, today=TODAY)
    assert len(jobs) == 6
    first = jobs[0]
    assert first.source == "jobs.cz"
    assert first.source_url.startswith("https://www.jobs.cz/rpd/") and "?" not in first.source_url
    assert first.source_id == "2001363021"
    assert first.title == "Group Full-stack developer - Marketing Technology"
    assert first.company == "Fortuna Group"
    assert first.location.startswith("Praha")
    assert first.posted_at == date(2026, 9, 9)
    by_id = {j.source_id: j for j in jobs}
    salaried = by_id["2001396430"]
    assert (salaried.salary_min, salaried.salary_max, salaried.salary_currency) == (
        70000, 90000, "CZK")
    assert salaried.salary_period.value == "month"
    remote = by_id["2001431189"]
    assert remote.remote_type == RemoteType.REMOTE  # "Práce převážně z domova"
    assert remote.posted_at == date(2026, 9, 24)  # "Přidáno včera"


def test_jobs_cz_query_slugs(app):
    src = jobs_cz.JobsCzSource({}, app)
    assert src._slug("Prague, Czechia") == "praha"
    assert src._slug("Czechia") is None
    queries = [SearchQuery(term="Vue", location="Prague, Czechia"),
               SearchQuery(term="Vue", location="Czechia", remote=True),
               SearchQuery(term="vue", location="Praha")]
    assert len(src.queries(queries)) == 2


# --- prace.cz ------------------------------------------------------------------

def test_prace_cz_cards():
    jobs = prace_cz.parse_search_page(read("prace_cz_search.html"), tagger)
    assert 3 <= len(jobs) <= 6
    for job in jobs:
        assert job.source == "prace.cz"
        assert job.source_url.startswith("https://")
        assert "?" not in job.source_url
        assert job.company and job.company != "(unknown company)"
        assert job.source_id
    assert any(j.location for j in jobs)


# --- jobstack ------------------------------------------------------------------

def test_jobstack_items():
    jobs = jobstack.parse_listing(read("jobstack_list.html"), tagger)
    assert len(jobs) == 6
    first, second = jobs[0], jobs[1]
    assert first.source_url == "https://www.jobstack.it/it-job/tester/6889c55291378"
    assert first.company == "URC Systems" and first.location == "Brno"
    assert (first.salary_min, first.salary_max, first.salary_currency) == (None, 55000, "CZK")
    assert second.remote_type == RemoteType.HYBRID
    assert second.company == "Principal engineering s.r.o."
    assert second.description == "Seniority: Medior, Senior"


def test_jobstack_queries(app):
    src = jobstack.JobstackSource({"categories": ["vue-js-developer"], "locations": ["", "remote"]},
                                  app)
    qs = src.queries([SearchQuery(term="ignored")])
    assert [(q.term, q.location, q.remote) for q in qs] == [
        ("vue-js-developer", None, False), ("vue-js-developer", "remote", True)]


# --- cocuma --------------------------------------------------------------------

def test_cocuma_list_and_detail(app):
    cards = cocuma.parse_list(read("cocuma_list.html"))
    assert 6 <= len(cards) <= 8  # "/s/..." promo thumbnails are skipped
    assert cards[0].url == "https://www.cocuma.cz/job/head-of-sales/10431/"
    assert cards[0].company == "Dateio" and cards[0].city == "Praha" and cards[0].fresh
    description, sidebar = cocuma.parse_detail(read("cocuma_detail.html"))
    assert description.startswith("ICT Infrastructure Engineer/Technician")
    assert "Mám zájem o tuto příležitost" not in description[200:]
    assert "síťová" in description or "sítě" in description
    src = cocuma.CocumaSource({}, app)
    job = src.build_job(cards[1], tagger, read("cocuma_detail.html"))
    assert job.source == "cocuma.cz" and job.language.value == "cs"
    assert len(job.description) > 500


def test_cocuma_fetch_skips_known_and_caps_details(app, monkeypatch):
    pages = {"https://www.cocuma.cz/jobs/": read("cocuma_list.html")}
    calls: list[str] = []

    def fake_get(self, url, **kw):
        calls.append(url)
        if url in pages:
            return httpx.Response(200, text=pages[url])
        if url.startswith("https://www.cocuma.cz/job/"):
            return httpx.Response(200, text=read("cocuma_detail.html"))
        raise httpx.HTTPStatusError("404", request=httpx.Request("GET", url),
                                    response=httpx.Response(404))

    monkeypatch.setattr(cocuma.CocumaSource, "get", fake_get)
    src = cocuma.CocumaSource({"pages": 3, "max_details": 1,
                               "title_keywords": ["engineer", "manager"]}, app)
    known = {"https://www.cocuma.cz/job/head-of-sales/10431/"}
    result = src.run([SearchQuery(term="x")], known_urls=known)
    assert not result.errors
    assert calls[0] == "https://www.cocuma.cz/jobs/"
    assert calls[1] == "https://www.cocuma.cz/jobs/page/2/"  # 404 -> stops paging
    detail_calls = [c for c in calls if "/job/" in c]
    assert len(detail_calls) == 1  # max_details honoured
    titles = [j.title for j in result.jobs]
    assert "ICT Infrastructure Engineer/Technician (síťař)" in titles
    assert result.seen_urls == []  # head-of-sales does not match the keywords


# --- startupjobs ---------------------------------------------------------------

def test_startupjobs_sitemap_and_detail():
    urls = startupjobs.sitemap_urls(read("startupjobs_offers.xml"))
    assert len(urls) == 20 and all("/nabidka/" in u for u in urls)
    kws = startupjobs.StartupjobsSettings().slug_keywords
    assert startupjobs.slug_matches(
        "https://www.startupjobs.cz/nabidka/107469/senior-frontend-engineer", kws)
    assert not startupjobs.slug_matches(
        "https://www.startupjobs.cz/nabidka/21242/customer-care-chat", kws)

    html = read("startupjobs_detail.html")
    url = "https://www.startupjobs.cz/nabidka/69505/remote-full-stack-developer-react-node-js"
    job = startupjobs.parse_detail(html, url, tagger, today=TODAY)
    assert job is not None
    assert job.source == "startupjobs.cz" and job.source_url == url
    assert job.title == "Remote Full-stack Developer (React + Node.js)"
    assert job.company == "Sudolabs"
    assert job.location == "Košice, Košický kraj, Slovensko"
    assert job.posted_at == date(2026, 8, 5)  # "Aktualizováno 05. 08. 2026" beats datePosted
    assert job.remote_type == RemoteType.REMOTE  # "Remote, On-site, Hybrid" line
    assert (job.salary_min, job.salary_max, job.salary_currency) == (None, 130000, "CZK")
    assert job.salary_period.value == "month"
    assert {"react", "node.js", "typescript", "graphql"} <= set(job.tech_tags)
    assert job.description.startswith("Type of contract:")


# --- welcome to the jungle -----------------------------------------------------

def test_wttj_sitemap_filter_and_detail():
    entries = wttj.sitemap_entries(read("wttj_sitemap.xml"))
    assert len(entries) == 5 and entries[0][1] == date(2026, 9, 20)
    cfg = wttj.WttjSettings()
    matched = [u for u, d in entries if wttj.slug_matches(u, cfg.slug_cities, cfg.slug_keywords)]
    assert matched == [
        "https://www.welcometothejungle.com/en/companies/restream/jobs/"
        "senior-software-engineer-backend-billing-team_prague_7xmr25xh",
        "https://www.welcometothejungle.com/en/companies/acme/jobs/senior-vue-developer_prague",
        "https://www.welcometothejungle.com/en/companies/acme/jobs/senior-vue-developer_prague_old",
    ]
    assert wttj.job_sitemaps("<loc>https://x/sitemaps/job-listings.0.xml.gz</loc>"
                             "<loc>https://x/sitemaps/articles.0.xml.gz</loc>") == [
        "https://x/sitemaps/job-listings.0.xml.gz"]

    html = read("wttj_detail.html")
    posting = find_job_posting(html)
    assert posting and posting["@type"] == "JobPosting"
    job = wttj.parse_detail(html, "https://www.welcometothejungle.com/x", tagger)
    assert job is not None and job.source == "welcometothejungle.com"
    assert job.title and job.company and job.description
    assert job.posted_at is not None


# --- remotive / arbeitnow / wwr --------------------------------------------------

def test_remotive_parse_and_location_filter():
    data = json.loads(read("remotive.json"))
    allowed = remotive.RemotiveSettings().allowed_locations
    kept = [remotive.parse_job(j, tagger) for j in data["jobs"]
            if remotive.location_allowed(j["candidate_required_location"], allowed)]
    assert [j.location for j in kept] == ["Worldwide", "Europe",
                                          "Northern America, LATAM, Europe, APAC"]
    job = kept[0]
    assert job.source == "remotive.com" and job.remote_type == RemoteType.REMOTE
    assert job.source_url.startswith("https://remotive.com/remote-jobs/")
    assert job.posted_at is not None and job.description


def test_remotive_keyword_filter():
    assert remotive.mentions_any(["vue", "react"], "Senior Vue Developer", None)
    assert remotive.mentions_any(["vue"], "Engineer", "", "we use Vue 3 and Pinia")
    assert not remotive.mentions_any(["vue", "react"], "Content Reviewer", "android", "ios")
    assert remotive.mentions_any([], "anything")


def test_arbeitnow_parse_and_filter():
    data = json.loads(read("arbeitnow.json"))
    cfg = arbeitnow.ArbeitnowSettings()
    # Location/remote rule alone keeps the single remote listing ...
    kept = [arbeitnow.parse_job(j, tagger) for j in data["data"]
            if arbeitnow.keep(j, cfg.keep_locations)]
    assert len(kept) == 1
    job = kept[0]
    assert job.remote_type == RemoteType.REMOTE and job.location == "Mühltal"
    assert job.source == "arbeitnow.com" and job.posted_at is not None
    assert job.language.value == "de"
    # ... but it is a sales role, so the keyword requirement drops it.
    assert not any(arbeitnow.keep(j, cfg.keep_locations, cfg.require_keywords)
                   for j in data["data"])
    vue_item = dict(data["data"][6], title="Vue.js Entwickler (m/w/d)")
    assert arbeitnow.keep(vue_item, cfg.keep_locations, cfg.require_keywords)


def test_wwr_feed_parse_and_region_filter():
    items = weworkremotely.parse_feed(read("wwr_fullstack.rss"))
    assert len(items) == 5
    allowed = weworkremotely.WwrSettings().allowed_regions
    kept = [weworkremotely.parse_job(i, tagger) for i in items
            if weworkremotely.region_allowed(i.get("region"), allowed)]
    assert len(kept) == 4
    job = kept[0]
    assert job.source == "weworkremotely.com" and job.remote_type == RemoteType.REMOTE
    assert job.company and job.title and ": " not in job.company
    assert job.source_url.startswith("https://weworkremotely.com/")
    assert job.posted_at is not None and len(job.description) > 100
