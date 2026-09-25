"""Hard filters applied before dedup/scoring: excluded title keywords and max age."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from datetime import date, timedelta

from jobagg.config import FiltersConfig
from jobagg.models import Job


def compile_keyword_patterns(keywords: Iterable[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Whole-word, case-insensitive patterns. 'java' will not match 'javascript'."""
    out: list[tuple[str, re.Pattern[str]]] = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(kw)}(?!\w)", re.IGNORECASE | re.UNICODE)
        out.append((kw, pattern))
    return out


def excluded_by_title(title: str, patterns: list[tuple[str, re.Pattern[str]]]) -> str | None:
    for keyword, rx in patterns:
        if rx.search(title):
            return keyword
    return None


def apply_filters(
    jobs: Iterable[Job], cfg: FiltersConfig, today: date | None = None
) -> tuple[list[Job], Counter[str]]:
    """Return (kept, dropped-by-reason). Jobs with an unknown posting date are kept."""
    today = today or date.today()
    cutoff = today - timedelta(days=cfg.max_age_days)
    patterns = compile_keyword_patterns(cfg.exclude_title_keywords)
    kept: list[Job] = []
    dropped: Counter[str] = Counter()
    allowed = set(cfg.languages)
    for job in jobs:
        keyword = excluded_by_title(job.title, patterns)
        if keyword:
            dropped[f"title:{keyword}"] += 1
            continue
        if job.posted_at is not None and job.posted_at < cutoff:
            dropped["too_old"] += 1
            continue
        lang = job.language.value
        if allowed and lang not in allowed and (lang != "other" or cfg.drop_unknown_language):
            dropped[f"language:{lang}"] += 1
            continue
        kept.append(job)
    return kept, dropped
