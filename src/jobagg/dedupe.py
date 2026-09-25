"""Deduplication: merge listings of the same job into one canonical record.

Step 2 ships the exact-key merge (same normalized company + title => same id).
Fuzzy matching with rapidfuzz is added in step 3 on top of ``merge_jobs``.
"""

from __future__ import annotations

from collections.abc import Iterable

from jobagg.models import Job, SourceRef


def richness(job: Job) -> float:
    """How much useful data a listing carries; higher wins as the primary record."""
    score = 0.0
    if job.has_salary:
        score += 3.0
    score += min(len(job.description), 4000) / 1000.0
    if job.posted_at is not None:
        score += 0.5
    if job.location:
        score += 0.25
    if job.remote_type.value != "unknown":
        score += 0.5
    return score


def _fill(primary: object, other: object) -> object:
    return primary if primary not in (None, "", []) else other


def merge_jobs(a: Job, b: Job) -> Job:
    """Merge two listings of the same job. The richer one is the primary record.

    Missing fields on the primary are filled from the other listing; the longer
    description wins; every source URL is preserved.
    """
    primary, other = (a, b) if richness(a) >= richness(b) else (b, a)
    data = primary.model_dump()
    data["id"] = a.id
    for field in ("location", "salary_min", "salary_max", "salary_currency", "salary_period",
                  "posted_at", "source_id"):
        data[field] = _fill(getattr(primary, field), getattr(other, field))
    if len(other.description) > len(primary.description):
        data["description"] = other.description
    if primary.remote_type.value == "unknown":
        data["remote_type"] = other.remote_type
    if primary.language.value == "other":
        data["language"] = other.language
    if primary.posted_at and other.posted_at:
        data["posted_at"] = min(primary.posted_at, other.posted_at)
    data["tech_tags"] = sorted(set(primary.tech_tags) | set(other.tech_tags))
    data["scraped_at"] = max(primary.scraped_at, other.scraped_at)
    data["first_seen_at"] = min(
        (d for d in (a.first_seen_at, b.first_seen_at) if d is not None), default=None
    )
    data["score"] = _fill(primary.score, other.score)
    data["score_breakdown"] = primary.score_breakdown or other.score_breakdown

    merged = Job.model_validate(data)
    refs: list[SourceRef] = []
    for ref in [*primary.all_sources, *other.all_sources]:
        if (ref.source, ref.url) != (merged.source, merged.source_url) and ref not in refs:
            refs.append(ref)
    merged.extra_sources = refs
    return merged


def merge_exact(jobs: Iterable[Job]) -> list[Job]:
    """Collapse listings sharing the same dedup id, preserving first-seen order."""
    by_id: dict[str, Job] = {}
    for job in jobs:
        by_id[job.id] = merge_jobs(by_id[job.id], job) if job.id in by_id else job
    return list(by_id.values())
