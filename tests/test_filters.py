from datetime import date

from jobagg.config import FiltersConfig
from jobagg.filters import apply_filters
from jobagg.models import Job


def _job(title: str, posted: date | None = None) -> Job:
    return Job(source="x", source_url=f"https://x/{title}", title=title, company="ACME",
               posted_at=posted)


def test_title_keywords_match_whole_words_only():
    cfg = FiltersConfig(exclude_title_keywords=["junior", "java", "team lead"], max_age_days=14)
    jobs = [
        _job("Junior Vue Developer"),
        _job("JavaScript Developer"),
        _job("Java Developer"),
        _job("Frontend Team Lead"),
        _job("Senior Vue Developer"),
    ]
    kept, dropped = apply_filters(jobs, cfg, today=date(2026, 9, 25))
    assert [j.title for j in kept] == ["JavaScript Developer", "Senior Vue Developer"]
    assert dropped == {"title:junior": 1, "title:java": 1, "title:team lead": 1}


def test_old_listings_are_dropped_unknown_dates_kept():
    cfg = FiltersConfig(exclude_title_keywords=[], max_age_days=14)
    jobs = [
        _job("fresh", date(2026, 9, 20)),
        _job("stale", date(2026, 8, 1)),
        _job("undated", None),
    ]
    kept, dropped = apply_filters(jobs, cfg, today=date(2026, 9, 25))
    assert [j.title for j in kept] == ["fresh", "undated"]
    assert dropped == {"too_old": 1}
