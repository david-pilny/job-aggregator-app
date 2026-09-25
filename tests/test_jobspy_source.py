"""JobSpy adapter tests against a saved DataFrame sample (no network)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from jobagg.config import AppConfig
from jobagg.models import SearchQuery
from jobagg.normalize import compile_tag_patterns
from jobagg.sources.jobspy_source import JobSpySource, row_to_job

FIXTURE = Path(__file__).parent / "fixtures" / "jobspy_sample.json"


@pytest.fixture(scope="module")
def sample() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def app() -> AppConfig:
    return AppConfig.model_validate({
        "tech_tags": {"vue": ["vue.js", "vuejs", "vue 3"], "nuxt": [], "typescript": ["ts"],
                      "react": [], ".net": ["c#"]},
        "sources": {"jobspy": {"enabled": True, "sites": ["linkedin", "indeed"],
                               "delay_seconds": [0, 0],
                               "extra_searches": [{"term": "Vue.js developer", "remote": True,
                                                   "sites": ["linkedin"]}]}},
    })


def test_row_to_job_maps_fields(sample):
    patterns = compile_tag_patterns({"vue": ["vue.js", "vue 3"], ".net": ["c#"]})
    rows = {r["site"]: r for r in sample}
    li = row_to_job(rows["linkedin"], patterns)
    assert li.source == "linkedin"
    assert li.source_url.startswith("https://www.linkedin.com/jobs/view/")
    assert li.title and li.company
    assert li.posted_at is not None
    assert li.id

    ind = row_to_job(rows["indeed"], patterns)
    assert ind.source == "indeed"
    assert ind.source_url.startswith("https://cz.indeed.com/")
    assert ind.description  # Indeed carries the full description
    assert ind.language.value in {"cs", "en", "de"}


def test_row_to_job_tolerates_nan_and_missing(sample):
    patterns = compile_tag_patterns({"vue": []})
    row = pd.Series({"site": "indeed", "title": "Vue Dev", "company": float("nan"),
                     "job_url": "https://cz.indeed.com/x", "min_amount": float("nan"),
                     "date_posted": pd.NaT, "is_remote": float("nan")})
    job = row_to_job(row, patterns)
    assert job.company == "(unknown company)"
    assert job.salary_min is None and job.salary_currency is None
    assert job.posted_at is None
    assert job.remote_type.value == "unknown"


def test_salary_and_remote_flag_mapping():
    patterns = compile_tag_patterns({})
    job = row_to_job({"site": "indeed", "title": "Vue Dev", "company": "ACME",
                      "job_url": "u", "min_amount": 80000.0, "max_amount": 100000.0,
                      "currency": "CZK", "interval": "monthly", "is_remote": True}, patterns)
    assert job.salary_text() == "80,000-100,000 CZK/month"
    assert job.remote_type.value == "remote"


def test_adapter_calls_each_site_and_isolates_failures(app, sample, monkeypatch):
    calls: list[dict] = []

    def fake_scrape_jobs(**kwargs):
        calls.append(kwargs)
        site = kwargs["site_name"]
        if site == "indeed" and kwargs.get("is_remote"):
            raise RuntimeError("boom")
        return pd.DataFrame([r for r in sample if r["site"] == site])

    monkeypatch.setattr("jobspy.scrape_jobs", fake_scrape_jobs)
    src = JobSpySource(app.sources["jobspy"].extra_fields(), app)
    assert src.produces == ("linkedin", "indeed")

    base = [SearchQuery(term="Vue developer", location="Prague, Czechia", remote=False),
            SearchQuery(term="Vue developer", location="Czechia", remote=True)]
    result = src.run(base)

    # 2 base queries x 2 sites + 1 extra search on linkedin only
    assert [c["site_name"] for c in calls] == ["linkedin", "indeed", "linkedin", "indeed",
                                               "linkedin"]
    assert calls[0]["hours_old"] == 14 * 24 and calls[0]["is_remote"] is False
    assert calls[2]["is_remote"] is True and calls[2]["hours_old"] == 14 * 24  # linkedin: both
    assert calls[3]["hours_old"] == 14 * 24 and "is_remote" not in calls[3]  # indeed: age only
    assert calls[4]["search_term"] == "Vue.js developer"

    assert not result.errors  # a single failing site is logged, not raised
    urls = {j.source_url for j in result.jobs}
    assert len(urls) == len(result.jobs)  # de-duplicated within the adapter
    assert {j.source for j in result.jobs} == {"linkedin", "indeed"}


def test_linkedin_remote_query_marks_unknown_as_remote(app, sample, monkeypatch):
    def fake_scrape_jobs(**kwargs):
        rows = [dict(r, is_remote=None) for r in sample if r["site"] == kwargs["site_name"]]
        return pd.DataFrame(rows)

    monkeypatch.setattr("jobspy.scrape_jobs", fake_scrape_jobs)
    src = JobSpySource({"sites": ["linkedin"], "delay_seconds": [0, 0]}, app)
    remote = src.run([SearchQuery(term="Vue", location="Czechia", remote=True)], extend=False)
    assert remote.jobs and all(j.remote_type.value == "remote" for j in remote.jobs)
    onsite = src.run([SearchQuery(term="Vue", location="Prague", remote=False)], extend=False)
    assert any(j.remote_type.value == "unknown" for j in onsite.jobs)
