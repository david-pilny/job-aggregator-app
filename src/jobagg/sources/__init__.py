"""Adapter registry. Add a new source by importing it and listing it in ``REGISTRY``."""

from __future__ import annotations

from jobagg.config import AppConfig
from jobagg.sources.arbeitnow import ArbeitnowSource
from jobagg.sources.base import Source, SourceResult
from jobagg.sources.cocuma import CocumaSource
from jobagg.sources.jobs_cz import JobsCzSource
from jobagg.sources.jobspy_source import JobSpySource
from jobagg.sources.jobstack import JobstackSource
from jobagg.sources.prace_cz import PraceCzSource
from jobagg.sources.remotive import RemotiveSource
from jobagg.sources.startupjobs import StartupjobsSource
from jobagg.sources.weworkremotely import WwrSource
from jobagg.sources.wttj import WttjSource

REGISTRY: dict[str, type[Source]] = {
    cls.name: cls
    for cls in (
        JobSpySource, JobsCzSource, PraceCzSource, JobstackSource, CocumaSource,
        StartupjobsSource, WttjSource, RemotiveSource, ArbeitnowSource, WwrSource,
    )
}


def build_sources(app: AppConfig, only: list[str] | None = None,
                  include_disabled: bool = False) -> list[Source]:
    """Instantiate adapters that are enabled in config (or explicitly requested)."""
    wanted = set(only or [])
    unknown = wanted - set(REGISTRY)
    if unknown:
        raise KeyError(f"unknown source(s): {', '.join(sorted(unknown))}; "
                       f"known: {', '.join(sorted(REGISTRY))}")
    out: list[Source] = []
    for name, cls in REGISTRY.items():
        settings = app.source_settings(name)
        if wanted and name not in wanted:
            continue
        if not settings.enabled and not include_disabled and not wanted:
            continue
        out.append(cls(settings.extra_fields(), app))
    return out


__all__ = ["REGISTRY", "Source", "SourceResult", "build_sources"]
