"""Extract a schema.org JobPosting from a page's JSON-LD (used by sitemap-based adapters)."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from selectolax.parser import HTMLParser

from jobagg.models import Job, Language, RemoteType, SalaryPeriod
from jobagg.normalize import detect_language, infer_remote_type, markdown_to_text

log = logging.getLogger(__name__)

_UNIT_TO_PERIOD = {
    "HOUR": SalaryPeriod.HOUR, "DAY": SalaryPeriod.DAY, "WEEK": SalaryPeriod.WEEK,
    "MONTH": SalaryPeriod.MONTH, "YEAR": SalaryPeriod.YEAR,
}


def _walk(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        found = [node] if node.get("@type") == "JobPosting" else []
        for value in node.values():
            found.extend(_walk(value))
        return found
    if isinstance(node, list):
        return [x for item in node for x in _walk(item)]
    return []


def find_job_posting(html: str) -> dict[str, Any] | None:
    """Return the first JobPosting object found in any ``application/ld+json`` block."""
    tree = HTMLParser(html)
    for script in tree.css('script[type="application/ld+json"]'):
        raw = script.text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        postings = _walk(data)
        if postings:
            return postings[0]
    return None


def _to_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _location_text(posting: dict[str, Any]) -> str | None:
    loc = posting.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return None
    address = loc.get("address")
    if isinstance(address, str):
        return address
    if isinstance(address, dict):
        parts = [address.get("addressLocality"), address.get("addressRegion"),
                 address.get("addressCountry")]
        return ", ".join(str(p) for p in parts if p) or None
    return loc.get("name")


def _salary(
    posting: dict[str, Any],
) -> tuple[float | None, float | None, str | None, SalaryPeriod | None]:
    base = posting.get("baseSalary")
    if not isinstance(base, dict):
        return None, None, None, None
    currency = base.get("currency")
    value = base.get("value")
    if isinstance(value, dict):
        lo = _to_float(value.get("minValue"))
        hi = _to_float(value.get("maxValue"))
        single = _to_float(value.get("value"))
        if single and not (lo or hi):
            lo = hi = single
        period = _UNIT_TO_PERIOD.get(str(value.get("unitText", "")).upper())
    else:
        lo = hi = _to_float(value)
        period = None
    if lo is None and hi is None:
        return None, None, None, None
    return lo, hi, str(currency) if currency else None, period


def job_from_posting(posting: dict[str, Any], *, source: str, url: str,
                     tagger: Any, remote_hint: RemoteType | None = None,
                     posted_override: date | None = None) -> Job:
    org = posting.get("hiringOrganization")
    company = org.get("name") if isinstance(org, dict) else org
    title = str(posting.get("title") or "").strip()
    description = markdown_to_text(str(posting.get("description") or ""))
    skills = posting.get("skills") or posting.get("qualifications") or ""
    if isinstance(skills, list):
        skills = ", ".join(map(str, skills))
    location = _location_text(posting)
    lo, hi, currency, period = _salary(posting)
    remote = remote_hint
    if remote is None:
        if str(posting.get("jobLocationType", "")).upper() == "TELECOMMUTE":
            remote = RemoteType.REMOTE
        else:
            remote = RemoteType(infer_remote_type(title, location, description))
    ident = posting.get("identifier")
    source_id = ident.get("value") if isinstance(ident, dict) else None
    return Job(
        source=source,
        source_url=url,
        source_id=str(source_id) if source_id else None,
        title=title or "(untitled)",
        company=str(company or "(unknown company)"),
        location=location,
        remote_type=remote,
        salary_min=lo,
        salary_max=hi,
        salary_currency=currency,
        salary_period=period,
        description=description,
        tech_tags=tagger(title, str(skills), description),
        language=Language(detect_language(title, description)),
        posted_at=posted_override or _parse_date(posting.get("datePosted")),
    )
