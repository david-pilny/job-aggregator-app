"""Deduplication: merge listings of the same job into one canonical record.

Two listings are duplicates when their normalized company matches and their
normalized titles are similar (rapidfuzz ``token_set_ratio`` >= threshold).
A weaker title match is accepted when both descriptions are long and similar.

Applied in two passes: within the current batch (union-find over company groups),
then against jobs already stored so a re-listed job adopts its existing id and
does not count as new.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable

from rapidfuzz import fuzz

from jobagg.config import DedupeConfig
from jobagg.models import Job, SourceRef

_DESC_PREFIX = 1500  # compare only the start of descriptions; boilerplate follows anyway


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

    The merged record keeps ``a``'s id. Missing fields on the primary are filled
    from the other listing; the longer description wins; all source URLs are kept.
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


def is_duplicate(a: Job, b: Job, cfg: DedupeConfig) -> bool:
    """Same company and a similar enough title (or a near title + same description)."""
    if a.company_norm != b.company_norm:
        return False
    title_ratio = fuzz.token_set_ratio(a.title_norm, b.title_norm)
    if title_ratio >= cfg.title_threshold:
        return True
    if cfg.description_threshold <= 0 or title_ratio < cfg.title_threshold - cfg.title_slack:
        return False
    if len(a.description) < 200 or len(b.description) < 200:
        return False
    desc_ratio = fuzz.ratio(a.description[:_DESC_PREFIX], b.description[:_DESC_PREFIX])
    return desc_ratio >= cfg.description_threshold


def merge_batch(jobs: Iterable[Job], cfg: DedupeConfig) -> list[Job]:
    """Collapse duplicates within one batch; keeps first-seen order of groups."""
    items = list(jobs)
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_company: dict[str, list[int]] = defaultdict(list)
    for idx, job in enumerate(items):
        by_company[job.company_norm].append(idx)
    for indices in by_company.values():
        for pos, i in enumerate(indices):
            for j in indices[pos + 1:]:
                if find(i) != find(j) and is_duplicate(items[i], items[j], cfg):
                    parent[find(j)] = find(i)

    groups: dict[int, Job] = {}
    for idx, job in enumerate(items):
        root = find(idx)
        groups[root] = merge_jobs(groups[root], job) if root in groups else job
    return list(groups.values())


def merge_exact(jobs: Iterable[Job]) -> list[Job]:
    """Collapse listings sharing the same dedup id only (no fuzzy matching)."""
    by_id: dict[str, Job] = {}
    for job in jobs:
        by_id[job.id] = merge_jobs(by_id[job.id], job) if job.id in by_id else job
    return list(by_id.values())


def adopt_existing_ids(
    jobs: Iterable[Job],
    lookup: Callable[[str], list[Job]],
    cfg: DedupeConfig,
) -> list[Job]:
    """Re-key batch jobs that fuzzy-match a stored job to that job's id.

    ``lookup(company_norm)`` returns stored jobs for a company. Exact-id matches
    are left alone; the DB upsert merges those itself.
    """
    out: list[Job] = []
    for job in jobs:
        candidates = [c for c in lookup(job.company_norm) if c.id != job.id]
        match = next((c for c in candidates if is_duplicate(job, c, cfg)), None)
        if match is not None:
            job = job.model_copy(update={"id": match.id})
        out.append(job)
    return merge_exact(out)
