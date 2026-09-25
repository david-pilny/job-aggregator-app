"""Orchestration for ``jobs run``: scrape -> filter -> dedupe -> store -> (score, notify)."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from jobagg.config import AppConfig
from jobagg.db import Database
from jobagg.dedupe import merge_exact
from jobagg.filters import apply_filters
from jobagg.models import Job, SearchQuery
from jobagg.sources import build_sources

log = logging.getLogger(__name__)

# A source that used to average at least this many results but now returns 0 is flagged.
_HEALTH_MIN_AVG = 3.0


@dataclass
class SourceStat:
    adapter: str
    source: str
    fetched: int
    duration_s: float
    error: str | None = None
    warning: str | None = None


@dataclass
class RunSummary:
    run_id: int
    dry_run: bool
    fetched: int = 0
    kept: int = 0
    unique: int = 0
    dropped: Counter[str] = field(default_factory=Counter)
    new_jobs: list[Job] = field(default_factory=list)
    all_jobs: list[Job] = field(default_factory=list)
    stats: list[SourceStat] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        return [s.warning for s in self.stats if s.warning]


def build_queries(app: AppConfig) -> list[SearchQuery]:
    return [
        SearchQuery(term=term, location=loc.name, remote=loc.remote,
                    max_age_days=app.filters.max_age_days)
        for term in app.search.terms
        for loc in app.search.locations
    ]


def scrape_all(
    app: AppConfig, only: list[str] | None = None
) -> tuple[list[Job], list[SourceStat], list[str]]:
    """Run every enabled adapter in isolation; never raises because of one source."""
    jobs: list[Job] = []
    stats: list[SourceStat] = []
    errors: list[str] = []
    queries = build_queries(app)
    for source in build_sources(app, only=only):
        log.info("=== %s: %d queries", source.name, len(source.queries(queries)))
        try:
            result = source.run(queries)
        except Exception as exc:  # noqa: BLE001 - belt and braces around Source.run
            msg = f"{source.name}: crashed: {type(exc).__name__}: {exc}"
            log.exception(msg)
            errors.append(msg)
            for name in source.produces:
                stats.append(SourceStat(source.name, name, 0, 0.0, error=msg))
            continue
        errors.extend(result.errors)
        counts = result.count_by_source(source.produces)
        per_source_error = "; ".join(result.errors) or None
        for name, n in counts.items():
            stats.append(
                SourceStat(source.name, name, n, result.duration_s, error=per_source_error)
            )
        log.info("=== %s: %d listings in %.1fs%s", source.name, len(result.jobs),
                 result.duration_s, f", {len(result.errors)} error(s)" if result.errors else "")
        jobs.extend(result.jobs)
    return jobs, stats, errors


def check_health(db: Database, stats: list[SourceStat], run_id: int) -> None:
    for stat in stats:
        if stat.error:
            stat.warning = f"{stat.source}: error - {stat.error[:160]}"
            continue
        if stat.fetched > 0:
            continue
        hist = db.source_history(stat.source, last_n=5, before_run=run_id)
        if hist.runs and hist.avg_fetched >= _HEALTH_MIN_AVG:
            stat.warning = (f"{stat.source}: returned 0 results "
                            f"(average {hist.avg_fetched:.0f} over the last {hist.runs} runs)")


def run_pipeline(app: AppConfig, db: Database, *, dry_run: bool = False,
                 only: list[str] | None = None) -> RunSummary:
    run_id = db.start_run(dry_run=dry_run)
    summary = RunSummary(run_id=run_id, dry_run=dry_run)

    raw, stats, errors = scrape_all(app, only=only)
    summary.fetched = len(raw)
    summary.stats = stats
    summary.errors = errors

    kept, dropped = apply_filters(raw, app.filters)
    summary.kept = len(kept)
    summary.dropped = dropped
    if dropped:
        log.info("filters dropped %d: %s", sum(dropped.values()),
                 ", ".join(f"{k}={v}" for k, v in dropped.most_common()))

    unique = merge_exact(kept)
    summary.unique = len(unique)
    log.info("%d listings -> %d after filters -> %d unique", len(raw), len(kept), len(unique))

    result = db.upsert_jobs(unique)
    new_ids = set(result.new_ids)
    summary.all_jobs = db.get_jobs(j.id for j in unique)
    summary.new_jobs = [j for j in summary.all_jobs if j.id in new_ids]
    log.info("stored: %d new, %d already known (db total %d)",
             len(result.new_ids), len(result.updated_ids), db.job_count())

    for stat in stats:
        db.record_source(run_id, stat.source, stat.fetched, stat.duration_s, stat.error)
    check_health(db, stats, run_id)
    for warning in summary.warnings:
        log.warning("health: %s", warning)

    db.finish_run(run_id, fetched=summary.fetched, kept=summary.kept, unique_count=summary.unique,
                  new_count=len(summary.new_jobs), notified=False, errors=errors)
    return summary
