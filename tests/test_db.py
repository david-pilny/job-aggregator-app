from datetime import UTC, date, datetime, timedelta

import pytest

from jobagg.db import Database
from jobagg.models import Job, RemoteType


@pytest.fixture
def db(tmp_path):
    with Database(tmp_path / "t.sqlite") as database:
        yield database


def _job(**kw) -> Job:
    base = dict(source="linkedin", source_url="https://li/1", title="Vue Developer",
                company="ACME", description="hello", tech_tags=["vue"],
                remote_type=RemoteType.REMOTE, posted_at=date(2026, 9, 20))
    base.update(kw)
    return Job(**base)


def test_first_upsert_is_new_second_is_not(db):
    now = datetime(2026, 9, 25, 8, 0, tzinfo=UTC)
    r1 = db.upsert_jobs([_job()], now=now)
    assert r1.new_ids and not r1.updated_ids

    later = now + timedelta(days=1)
    r2 = db.upsert_jobs([_job(source="indeed", source_url="https://in/1")], now=later)
    assert not r2.new_ids and r2.updated_ids

    stored = db.get_job(_job().id)
    assert stored is not None
    assert stored.first_seen_at == now
    assert stored.last_seen_at == later
    assert {s.url for s in stored.all_sources} == {"https://li/1", "https://in/1"}
    assert db.job_count() == 1


def test_roundtrip_preserves_fields(db):
    job = _job(salary_min=90000, salary_max=120000, salary_currency="CZK", salary_period="month",
               language="cs", location="Praha")
    db.upsert_jobs([job])
    back = db.get_job(job.id)
    assert back.salary_text() == "90,000-120,000 CZK/month"
    assert back.language.value == "cs"
    assert back.remote_type == RemoteType.REMOTE
    assert back.tech_tags == ["vue"]
    assert back.posted_at == date(2026, 9, 20)


def test_existing_row_is_enriched_not_replaced(db):
    db.upsert_jobs([_job(description="short")])
    db.upsert_jobs([_job(source="jobs.cz", source_url="https://j/1", description="x" * 500,
                         salary_min=100000, salary_currency="CZK")])
    back = db.get_job(_job().id)
    assert back.description == "x" * 500
    assert back.salary_min == 100000
    assert back.source == "jobs.cz"


def test_runs_and_source_history(db):
    for n in (10, 12, 0):
        run_id = db.start_run(dry_run=False)
        db.record_source(run_id, "linkedin", n, 1.5, None)
        db.finish_run(run_id, fetched=n, kept=n, unique_count=n, new_count=n, notified=False,
                      errors=[])
    hist = db.source_history("linkedin", last_n=5, before_run=run_id)
    assert hist.runs == 2
    assert hist.avg_fetched == 11
    assert db.source_history("nope").runs == 0
    assert len(db.recent_runs()) == 3


def test_active_jobs_window(db):
    now = datetime(2026, 9, 25, tzinfo=UTC)
    db.upsert_jobs([_job()], now=now - timedelta(days=30))
    db.upsert_jobs([_job(title="Nuxt Developer")], now=now - timedelta(days=2))
    active = db.active_jobs(active_days=21, now=now)
    assert [j.title for j in active] == ["Nuxt Developer"]
