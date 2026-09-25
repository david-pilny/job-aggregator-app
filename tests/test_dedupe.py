from datetime import date

from jobagg.dedupe import merge_exact, merge_jobs, richness
from jobagg.models import Job, RemoteType


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


def test_merge_exact_collapses_same_id_only():
    a = _job(source_url="https://li/1")
    b = _job(source="indeed", source_url="https://in/1")
    c = _job(title="Backend Developer", source_url="https://li/2")
    out = merge_exact([a, b, c])
    assert len(out) == 2
    assert len(out[0].all_sources) == 2
    assert out[1].title == "Backend Developer"
