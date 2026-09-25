from datetime import date

from jobagg.config import FiltersConfig
from jobagg.filters import apply_filters
from jobagg.models import Job, Language


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


def test_language_filter_keeps_unknown_by_default():
    jobs = [_job("Vue Developer"), _job("Développeur Vue.js"), _job("Vue Entwickler")]
    jobs[0].language, jobs[1].language, jobs[2].language = (
        Language.EN, Language.OTHER, Language.DE)
    cfg = FiltersConfig(languages=["cs", "en"])
    kept, dropped = apply_filters(jobs, cfg, today=date(2026, 9, 25))
    assert [j.title for j in kept] == ["Vue Developer", "Développeur Vue.js"]
    assert dropped == {"language:de": 1}
    cfg = FiltersConfig(languages=["cs", "en"], drop_unknown_language=True)
    kept, _ = apply_filters(jobs, cfg, today=date(2026, 9, 25))
    assert [j.title for j in kept] == ["Vue Developer"]


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
