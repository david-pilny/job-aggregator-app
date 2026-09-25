"""SQLite storage: canonical jobs, their source links, and run history.

Single file, no server. All timestamps are stored as ISO-8601 UTC strings.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from jobagg.models import Job, SourceRef, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    company_norm    TEXT NOT NULL,
    title_norm      TEXT NOT NULL,
    location        TEXT,
    remote_type     TEXT NOT NULL DEFAULT 'unknown',
    salary_min      REAL,
    salary_max      REAL,
    salary_currency TEXT,
    salary_period   TEXT,
    description     TEXT NOT NULL DEFAULT '',
    tech_tags       TEXT NOT NULL DEFAULT '[]',
    language        TEXT NOT NULL DEFAULT 'other',
    posted_at       TEXT,
    scraped_at      TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    source          TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    source_id       TEXT,
    score           REAL,
    score_breakdown TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_jobs_company_norm ON jobs(company_norm);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at);

CREATE TABLE IF NOT EXISTS job_sources (
    job_id        TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    source        TEXT NOT NULL,
    url           TEXT NOT NULL,
    source_id     TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    PRIMARY KEY (job_id, source, url)
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    dry_run       INTEGER NOT NULL DEFAULT 0,
    fetched       INTEGER NOT NULL DEFAULT 0,
    kept          INTEGER NOT NULL DEFAULT 0,
    unique_count  INTEGER NOT NULL DEFAULT 0,
    new_count     INTEGER NOT NULL DEFAULT 0,
    notified      INTEGER NOT NULL DEFAULT 0,
    errors        TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS run_sources (
    run_id     INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    source     TEXT NOT NULL,
    fetched    INTEGER NOT NULL DEFAULT 0,
    duration_s REAL NOT NULL DEFAULT 0,
    error      TEXT,
    PRIMARY KEY (run_id, source)
);
"""


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@dataclass(frozen=True)
class SourceHistory:
    source: str
    runs: int
    avg_fetched: float
    last_fetched: int | None
    last_error: str | None


@dataclass(frozen=True)
class UpsertResult:
    new_ids: list[str]
    updated_ids: list[str]


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- jobs ---------------------------------------------------------------

    def has_job(self, job_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row is not None

    def get_job(self, job_id: str) -> Job | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def known_ids(self) -> set[str]:
        return {r["id"] for r in self.conn.execute("SELECT id FROM jobs")}

    def upsert_jobs(self, jobs: Iterable[Job], now: datetime | None = None) -> UpsertResult:
        """Insert unseen jobs, refresh seen ones. Returns which ids were new.

        Existing rows are enriched (not replaced): a newly seen salary or a longer
        description wins, and every source URL is attached.
        """
        from jobagg.dedupe import merge_jobs  # local import to avoid a cycle

        now = now or utcnow()
        new_ids: list[str] = []
        updated_ids: list[str] = []
        with self.conn:
            for job in jobs:
                existing = self.get_job(job.id)
                if existing is None:
                    job.first_seen_at = job.first_seen_at or now
                    job.last_seen_at = now
                    self._insert_job(job)
                    new_ids.append(job.id)
                else:
                    merged = merge_jobs(existing, job)
                    merged.first_seen_at = existing.first_seen_at
                    merged.last_seen_at = now
                    self._update_job(merged)
                    updated_ids.append(job.id)
                self._upsert_sources(job.id, job.all_sources, now)
        return UpsertResult(new_ids=new_ids, updated_ids=updated_ids)

    def update_scores(self, jobs: Iterable[Job]) -> None:
        with self.conn:
            self.conn.executemany(
                "UPDATE jobs SET score = ?, score_breakdown = ? WHERE id = ?",
                [(j.score, json.dumps(j.score_breakdown), j.id) for j in jobs],
            )

    def get_jobs(self, ids: Iterable[str]) -> list[Job]:
        out: list[Job] = []
        for job_id in ids:
            job = self.get_job(job_id)
            if job:
                out.append(job)
        return out

    def active_jobs(self, active_days: int, now: datetime | None = None) -> list[Job]:
        cutoff = (now or utcnow()) - timedelta(days=active_days)
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE last_seen_at >= ? ORDER BY score DESC, last_seen_at DESC",
            (cutoff.isoformat(),),
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def jobs_by_company_norm(self, company_norm: str) -> list[Job]:
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE company_norm = ?", (company_norm,)
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def job_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

    def _insert_job(self, job: Job) -> None:
        self.conn.execute(
            """
            INSERT INTO jobs (id, title, company, company_norm, title_norm, location,
                remote_type, salary_min, salary_max, salary_currency, salary_period,
                description, tech_tags, language, posted_at, scraped_at, first_seen_at,
                last_seen_at, source, source_url, source_id, score, score_breakdown)
            VALUES (:id, :title, :company, :company_norm, :title_norm, :location,
                :remote_type, :salary_min, :salary_max, :salary_currency, :salary_period,
                :description, :tech_tags, :language, :posted_at, :scraped_at, :first_seen_at,
                :last_seen_at, :source, :source_url, :source_id, :score, :score_breakdown)
            """,
            self._job_params(job),
        )

    def _update_job(self, job: Job) -> None:
        self.conn.execute(
            """
            UPDATE jobs SET title=:title, company=:company, company_norm=:company_norm,
                title_norm=:title_norm, location=:location, remote_type=:remote_type,
                salary_min=:salary_min, salary_max=:salary_max,
                salary_currency=:salary_currency, salary_period=:salary_period,
                description=:description, tech_tags=:tech_tags, language=:language,
                posted_at=:posted_at, scraped_at=:scraped_at, last_seen_at=:last_seen_at,
                source=:source, source_url=:source_url, source_id=:source_id,
                score=:score, score_breakdown=:score_breakdown
            WHERE id=:id
            """,
            self._job_params(job),
        )

    def _upsert_sources(self, job_id: str, refs: Iterable[SourceRef], now: datetime) -> None:
        for ref in refs:
            self.conn.execute(
                """
                INSERT INTO job_sources
                    (job_id, source, url, source_id, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, source, url) DO UPDATE SET last_seen_at = excluded.last_seen_at
                """,
                (job_id, ref.source, ref.url, ref.source_id, now.isoformat(), now.isoformat()),
            )

    def _sources_for(self, job_id: str) -> list[SourceRef]:
        rows = self.conn.execute(
            "SELECT source, url, source_id FROM job_sources WHERE job_id = ? "
            "ORDER BY first_seen_at",
            (job_id,),
        ).fetchall()
        return [
            SourceRef(source=r["source"], url=r["url"], source_id=r["source_id"]) for r in rows
        ]

    @staticmethod
    def _job_params(job: Job) -> dict[str, object]:
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "company_norm": job.company_norm,
            "title_norm": job.title_norm,
            "location": job.location,
            "remote_type": job.remote_type.value,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_period": job.salary_period.value if job.salary_period else None,
            "description": job.description,
            "tech_tags": json.dumps(job.tech_tags),
            "language": job.language.value,
            "posted_at": _iso(job.posted_at),
            "scraped_at": _iso(job.scraped_at),
            "first_seen_at": _iso(job.first_seen_at),
            "last_seen_at": _iso(job.last_seen_at),
            "source": job.source,
            "source_url": job.source_url,
            "source_id": job.source_id,
            "score": job.score,
            "score_breakdown": json.dumps(job.score_breakdown),
        }

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        primary = (row["source"], row["source_url"])
        extra = [r for r in self._sources_for(row["id"]) if (r.source, r.url) != primary]
        return Job(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            location=row["location"],
            remote_type=row["remote_type"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_currency=row["salary_currency"],
            salary_period=row["salary_period"],
            description=row["description"],
            tech_tags=json.loads(row["tech_tags"]),
            language=row["language"],
            posted_at=_parse_date(row["posted_at"]),
            scraped_at=_parse_dt(row["scraped_at"]) or utcnow(),
            first_seen_at=_parse_dt(row["first_seen_at"]),
            last_seen_at=_parse_dt(row["last_seen_at"]),
            source=row["source"],
            source_url=row["source_url"],
            source_id=row["source_id"],
            score=row["score"],
            score_breakdown=json.loads(row["score_breakdown"] or "{}"),
            extra_sources=extra,
        )

    # --- runs ---------------------------------------------------------------

    def start_run(self, dry_run: bool = False) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO runs (started_at, dry_run) VALUES (?, ?)",
                (utcnow().isoformat(), int(dry_run)),
            )
        return int(cur.lastrowid or 0)

    def record_source(
        self, run_id: int, source: str, fetched: int, duration_s: float, error: str | None
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO run_sources (run_id, source, fetched, duration_s, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, source) DO UPDATE SET fetched = excluded.fetched,
                    duration_s = excluded.duration_s, error = excluded.error
                """,
                (run_id, source, fetched, duration_s, error),
            )

    def finish_run(
        self,
        run_id: int,
        *,
        fetched: int,
        kept: int,
        unique_count: int,
        new_count: int,
        notified: bool,
        errors: list[str],
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                UPDATE runs SET finished_at = ?, fetched = ?, kept = ?, unique_count = ?,
                    new_count = ?, notified = ?, errors = ?
                WHERE id = ?
                """,
                (
                    utcnow().isoformat(),
                    fetched,
                    kept,
                    unique_count,
                    new_count,
                    int(notified),
                    json.dumps(errors),
                    run_id,
                ),
            )

    def source_history(
        self, source: str, last_n: int = 5, before_run: int | None = None
    ) -> SourceHistory:
        """Average result count for a source over its previous ``last_n`` runs."""
        sql = "SELECT fetched, error FROM run_sources WHERE source = ?"
        params: list[object] = [source]
        if before_run is not None:
            sql += " AND run_id < ?"
            params.append(before_run)
        sql += " ORDER BY run_id DESC LIMIT ?"
        params.append(last_n)
        rows = self.conn.execute(sql, params).fetchall()
        if not rows:
            return SourceHistory(source, 0, 0.0, None, None)
        counts = [int(r["fetched"]) for r in rows]
        return SourceHistory(
            source=source,
            runs=len(rows),
            avg_fetched=sum(counts) / len(counts),
            last_fetched=counts[0],
            last_error=rows[0]["error"],
        )

    def recent_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
