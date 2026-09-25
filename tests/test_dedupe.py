from datetime import date

from jobagg.config import DedupeConfig
from jobagg.dedupe import (
    adopt_existing_ids,
    is_duplicate,
    merge_batch,
    merge_exact,
    merge_jobs,
    richness,
)
from jobagg.models import Job, RemoteType

CFG = DedupeConfig(title_threshold=85, description_threshold=90, title_slack=20)


def _job(**kw) -> Job:
    base = dict(source="linkedin", source_url="https://li/1", title="Vue Developer",
                company="ACME s.r.o.")
    base.update(kw)
    return Job(**base)


def test_richer_listing_becomes_primary_and_sources_are_kept():
    thin = _job(source="linkedin", source_url="https://li/1", description="")
    rich = _job(source="jobs.cz", source_url="https://jobs.cz/1", description="x" * 2000,
                salary_min=80000, salary_currency="CZK", posted_at=date(2026, 9, 20))
    assert richness(rich) > richness(thin)

    merged = merge_jobs(thin, rich)
    assert merged.id == thin.id
    assert merged.source == "jobs.cz"
    assert merged.salary_min == 80000
    assert [s.url for s in merged.all_sources] == ["https://jobs.cz/1", "https://li/1"]


def test_merge_fills_missing_fields_from_other_listing():
    a = _job(description="long " * 300, location=None, remote_type=RemoteType.UNKNOWN,
             tech_tags=["vue"])
    b = _job(source="indeed", source_url="https://in/1", location="Praha",
             remote_type=RemoteType.REMOTE, tech_tags=["nuxt"], posted_at=date(2026, 9, 1))
    merged = merge_jobs(a, b)
    assert merged.source == "linkedin"
    assert merged.location == "Praha"
    assert merged.remote_type == RemoteType.REMOTE
    assert merged.posted_at == date(2026, 9, 1)
    assert merged.tech_tags == ["nuxt", "vue"]


def test_is_duplicate_same_company_similar_title():
    a = _job(title="Senior Frontend Developer (Vue.js)", company="ACME s.r.o.")
    b = _job(title="Senior Frontend Developer - Vue", company="acme", source_url="u2")
    assert is_duplicate(a, b, CFG)
    assert not is_duplicate(a, _job(title="Backend Developer", company="acme"), CFG)
    assert not is_duplicate(a, _job(title="Senior Frontend Developer (Vue.js)",
                                    company="Other"), CFG)


def test_is_duplicate_falls_back_to_description():
    desc = "We are hiring a frontend engineer to build our Vue app. " * 10
    a = _job(title="Frontend Engineer", description=desc)
    b = _job(title="Frontend Developer", description=desc, source_url="u2")
    assert is_duplicate(a, b, CFG)
    assert not is_duplicate(a, b, DedupeConfig(description_threshold=0))
    assert not is_duplicate(a, _job(title="Frontend Developer", description=""), CFG)


def test_merge_batch_groups_across_portals():
    jobs = [
        _job(title="Vue Developer", source="linkedin", source_url="li/1"),
        _job(title="Vue.js Developer (m/f/d)", source="indeed", source_url="in/1",
             description="x" * 1000),
        _job(title="Vue Developer", source="jobs.cz", source_url="jc/1", salary_min=90000),
        _job(title="QA Engineer", source="jobs.cz", source_url="jc/2"),
        _job(title="Vue Developer", company="Other Co", source_url="li/9"),
    ]
    out = merge_batch(jobs, CFG)
    assert len(out) == 3
    vue = next(j for j in out if j.company == "ACME s.r.o." and "Vue" in j.title)
    assert vue.id == jobs[0].id  # keeps the first-seen id
    assert vue.source == "jobs.cz"  # richest (salary) is primary
    assert {s.source for s in vue.all_sources} == {"linkedin", "indeed", "jobs.cz"}


def test_adopt_existing_ids_relinks_to_stored_job():
    stored = _job(title="Senior Vue.js Developer", source_url="old")
    incoming = [_job(title="Senior Vue Developer (m/f/d)", source="indeed", source_url="new"),
                _job(title="Data Engineer", source_url="new2")]
    lookup = {stored.company_norm: [stored]}
    out = adopt_existing_ids(incoming, lambda c: lookup.get(c, []), CFG)
    assert out[0].id == stored.id
    assert out[0].source_url == "new"
    assert out[1].id == incoming[1].id


def test_merge_exact_collapses_same_id_only():
    a = _job(source_url="https://li/1")
    b = _job(source="indeed", source_url="https://in/1")
    c = _job(title="Backend Developer", source_url="https://li/2")
    out = merge_exact([a, b, c])
    assert len(out) == 2
    assert len(out[0].all_sources) == 2
    assert out[1].title == "Backend Developer"
