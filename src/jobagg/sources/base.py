"""Common interface for every source adapter.

An adapter implements ``fetch(query) -> list[Job]``. ``Source.run`` wraps it with
timing, per-query error isolation, polite delays and within-adapter de-duplication.
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx

from jobagg.config import AppConfig
from jobagg.models import Job, SearchQuery
from jobagg.normalize import compile_tag_patterns, extract_tech_tags

log = logging.getLogger(__name__)


@dataclass
class SourceResult:
    adapter: str
    jobs: list[Job] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    per_query: dict[str, int] = field(default_factory=dict)

    def count_by_source(self, produces: Sequence[str]) -> dict[str, int]:
        counts = {name: 0 for name in produces}
        for job in self.jobs:
            counts[job.source] = counts.get(job.source, 0) + 1
        return counts


def polite_sleep(delay_range: tuple[float, float]) -> None:
    lo, hi = delay_range
    if hi <= 0:
        return
    time.sleep(random.uniform(lo, max(lo, hi)))


def make_http_client(app: AppConfig) -> httpx.Client:
    """httpx client with a realistic User-Agent, timeout and optional proxy."""
    headers = {
        "User-Agent": app.http.user_agent,
        "Accept-Language": "cs-CZ,cs;q=0.9,en-US;q=0.8,en;q=0.7,de;q=0.6",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    proxy = random.choice(app.http.proxies) if app.http.proxies else None
    return httpx.Client(
        headers=headers,
        timeout=app.http.timeout_seconds,
        follow_redirects=True,
        proxy=proxy,
    )


class Source(ABC):
    """Base class for adapters. Subclasses set ``name`` and ``produces``."""

    name: ClassVar[str]
    #: Values that appear in ``Job.source`` for jobs from this adapter. Used for
    #: per-source health tracking even when an adapter returns nothing. Adapters
    #: may narrow it per instance (e.g. jobspy only lists the configured sites).
    produces: tuple[str, ...] = ()

    def __init__(self, settings: dict[str, Any], app: AppConfig) -> None:
        self.settings = settings
        self.app = app
        self.delay_range: tuple[float, float] = tuple(  # type: ignore[assignment]
            settings.get("delay_seconds", app.http.delay_seconds)
        )
        self._tag_patterns = compile_tag_patterns(app.tech_tags)

    @abstractmethod
    def fetch(self, query: SearchQuery) -> list[Job]:
        """Fetch listings for one query. Raise on hard failure; ``run`` isolates it."""

    def queries(self, base: list[SearchQuery]) -> list[SearchQuery]:
        """Adapters may narrow or extend the global queries (e.g. drop EU-wide ones)."""
        return base

    def tag(self, *texts: str | None) -> list[str]:
        return extract_tech_tags(" ".join(t for t in texts if t), self._tag_patterns)

    def run(self, base_queries: list[SearchQuery], *, extend: bool = True) -> SourceResult:
        """Fetch all queries; ``extend=False`` skips adapter-specific extra searches."""
        result = SourceResult(adapter=self.name)
        started = time.perf_counter()
        seen: set[tuple[str, str]] = set()
        queries = self.queries(base_queries) if extend else list(base_queries)
        for i, query in enumerate(queries):
            if i > 0:
                polite_sleep(self.delay_range)
            try:
                jobs = self.fetch(query)
            except Exception as exc:  # noqa: BLE001 - isolate any adapter failure
                msg = f"{self.name}: {query.label()}: {type(exc).__name__}: {exc}"
                log.error(msg)
                result.errors.append(msg)
                continue
            fresh = 0
            for job in jobs:
                key = (job.source, job.source_url)
                if key in seen:
                    continue
                seen.add(key)
                result.jobs.append(job)
                fresh += 1
            result.per_query[query.label()] = len(jobs)
            log.info("%s: %s -> %d listings (%d new within adapter)",
                     self.name, query.label(), len(jobs), fresh)
        result.duration_s = time.perf_counter() - started
        return result
