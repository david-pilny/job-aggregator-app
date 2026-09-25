"""Adapter registry. Add a new source by importing it and listing it in ``REGISTRY``."""

from __future__ import annotations

from jobagg.config import AppConfig
from jobagg.sources.base import Source, SourceResult
from jobagg.sources.jobspy_source import JobSpySource

REGISTRY: dict[str, type[Source]] = {
    JobSpySource.name: JobSpySource,
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
