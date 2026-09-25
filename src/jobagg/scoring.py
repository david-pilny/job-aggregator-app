"""Score jobs 0-100 against the profile in ``config.yaml``.

Components (each 0..1, multiplied by its weight):
- stack:     configured stack tags found in the title (x title_multiplier) or body
- remote:    remote > hybrid > unknown > onsite
- seniority: senior/mid wording in the title; lead-only and junior rank low
- salary:    a listed salary earns the full (small) weight
- freshness: full points while younger than fresh_days, linear decay to 0 at max_age_days

Extension point: a ``RelevanceChecker`` can adjust the final score (for example an
LLM reading the description). Configure ``scoring.relevance: "module:Class"``.
"""

from __future__ import annotations

import importlib
import logging
import re
from collections.abc import Iterable
from datetime import date
from typing import Protocol

from jobagg.config import ScoringConfig
from jobagg.models import Job
from jobagg.normalize import compile_tag_patterns

log = logging.getLogger(__name__)


class RelevanceChecker(Protocol):
    """Adjusts a job's score after the rule-based components. Return the new score."""

    def adjust(self, job: Job, score: float) -> float: ...


class NoopRelevance:
    def adjust(self, job: Job, score: float) -> float:
        return score


def load_relevance_checker(spec: str) -> RelevanceChecker:
    if not spec or spec == "none":
        return NoopRelevance()
    module_name, _, attr = spec.partition(":")
    if not attr:
        raise ValueError(f"scoring.relevance must look like 'package.module:Class', got {spec!r}")
    cls = getattr(importlib.import_module(module_name), attr)
    return cls()  # type: ignore[no-any-return]


def _word_patterns(words: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(rf"(?<!\w){re.escape(w)}(?!\w)", re.IGNORECASE) for w in words if w]


class Scorer:
    def __init__(self, cfg: ScoringConfig, max_age_days: int = 14,
                 relevance: RelevanceChecker | None = None) -> None:
        self.cfg = cfg
        self.max_age_days = max(max_age_days, cfg.fresh_days + 1)
        self.relevance = relevance or load_relevance_checker(cfg.relevance)
        self._stack_patterns = compile_tag_patterns({tag: [] for tag in cfg.stack_tags})
        self._senior = _word_patterns(cfg.senior_keywords)
        self._lead = _word_patterns(cfg.lead_keywords)
        self._junior = _word_patterns(cfg.junior_keywords)
        best_tag = max(cfg.stack_tags.values(), default=1.0)
        self._stack_full = best_tag * cfg.title_multiplier

    # --- components -----------------------------------------------------------

    def stack(self, job: Job) -> float:
        raw = 0.0
        title = job.title
        tags = set(job.tech_tags)
        for tag, weight in self.cfg.stack_tags.items():
            in_title = bool(self._stack_patterns[tag].search(title))
            if in_title:
                raw += weight * self.cfg.title_multiplier
            elif tag in tags:
                raw += weight
        return min(1.0, raw / self._stack_full) if self._stack_full else 0.0

    def remote(self, job: Job) -> float:
        return float(self.cfg.remote_scores.get(job.remote_type.value, 0.0))

    def seniority(self, job: Job) -> float:
        title = job.title
        if any(p.search(title) for p in self._junior):
            return 0.0
        is_senior = any(p.search(title) for p in self._senior)
        is_lead = any(p.search(title) for p in self._lead)
        if is_lead and not is_senior:
            return self.cfg.lead_score
        if is_senior:
            return 1.0
        return self.cfg.unknown_seniority_score

    def salary(self, job: Job) -> float:
        return 1.0 if job.has_salary else 0.0

    def freshness(self, job: Job, today: date) -> float:
        if job.posted_at is None:
            return 0.5
        age = (today - job.posted_at).days
        if age <= self.cfg.fresh_days:
            return 1.0
        span = self.max_age_days - self.cfg.fresh_days
        return max(0.0, 1.0 - (age - self.cfg.fresh_days) / span)

    # --- total ----------------------------------------------------------------

    def score(self, job: Job, today: date | None = None) -> Job:
        today = today or date.today()
        w = self.cfg.weights
        parts = {
            "stack": round(w.stack * self.stack(job), 1),
            "remote": round(w.remote * self.remote(job), 1),
            "seniority": round(w.seniority * self.seniority(job), 1),
            "salary": round(w.salary * self.salary(job), 1),
            "freshness": round(w.freshness * self.freshness(job, today), 1),
        }
        total = sum(parts.values())
        adjusted = self.relevance.adjust(job, total)
        if adjusted != total:
            parts["relevance"] = round(adjusted - total, 1)
        job.score = round(max(0.0, min(100.0, adjusted)), 1)
        job.score_breakdown = parts
        return job

    def score_all(self, jobs: Iterable[Job], today: date | None = None) -> list[Job]:
        return [self.score(j, today) for j in jobs]
