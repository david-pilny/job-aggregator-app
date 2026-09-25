"""Configuration loading: ``config.yaml`` (everything user-specific) + ``.env`` (secrets)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class LocationConfig(BaseModel):
    name: str
    remote: bool = False


class SearchConfig(BaseModel):
    terms: list[str] = Field(default_factory=lambda: ["Frontend developer"])
    locations: list[LocationConfig] = Field(
        default_factory=lambda: [LocationConfig(name="Prague, Czech Republic")]
    )


class StorageConfig(BaseModel):
    db_path: str = "jobs.sqlite"
    active_days: int = 21


class HttpConfig(BaseModel):
    user_agent: str = DEFAULT_USER_AGENT
    timeout_seconds: float = 20.0
    delay_seconds: tuple[float, float] = (2.0, 5.0)
    proxies: list[str] = Field(default_factory=list)


class SourceSettings(BaseModel):
    """Common part of every ``sources.<name>`` section; adapters validate the rest."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = True

    def extra_fields(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class FiltersConfig(BaseModel):
    exclude_title_keywords: list[str] = Field(default_factory=list)
    max_age_days: int = 14


class ScoringWeights(BaseModel):
    stack: float = 45.0
    remote: float = 25.0
    seniority: float = 15.0
    salary: float = 5.0
    freshness: float = 10.0


class ScoringConfig(BaseModel):
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    # tag -> points (relative; the stack component is scaled to weights.stack)
    stack_tags: dict[str, float] = Field(
        default_factory=lambda: {"vue": 1.0, "nuxt": 1.0, "typescript": 0.7}
    )
    title_multiplier: float = 1.5
    remote_scores: dict[str, float] = Field(
        default_factory=lambda: {"remote": 1.0, "hybrid": 0.6, "unknown": 0.4, "onsite": 0.1}
    )
    senior_keywords: list[str] = Field(default_factory=lambda: ["senior", "medior", "mid"])
    lead_keywords: list[str] = Field(default_factory=lambda: ["lead", "head", "manager"])
    fresh_days: int = 3


class EmailConfig(BaseModel):
    enabled: bool = True
    to: str = ""
    subject_prefix: str = "[jobs]"
    min_score: float = 40.0
    max_items: int = 40


class NotifyConfig(BaseModel):
    email: EmailConfig = Field(default_factory=EmailConfig)


class ReportConfig(BaseModel):
    path: str = "report.html"
    min_score: float = 0.0


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search: SearchConfig = Field(default_factory=SearchConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    sources: dict[str, SourceSettings] = Field(default_factory=dict)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    tech_tags: dict[str, list[str]] = Field(default_factory=dict)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)

    # Filled by ``load_config``; not part of the YAML.
    base_dir: Path = Field(default_factory=Path.cwd, exclude=True)

    @field_validator("tech_tags", mode="before")
    @classmethod
    def _none_to_list(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: (v or []) for k, v in value.items()}
        return value

    def resolve(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.base_dir / p

    @property
    def db_path(self) -> Path:
        return self.resolve(self.storage.db_path)

    @property
    def report_path(self) -> Path:
        return self.resolve(self.report.path)

    def source_settings(self, name: str) -> SourceSettings:
        return self.sources.get(name, SourceSettings(enabled=False))


def find_config_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("JOBAGG_CONFIG")
    if env:
        return Path(env)
    return Path.cwd() / "config.yaml"


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    """Load ``config.yaml`` and the ``.env`` next to it (if present)."""
    cfg_path = find_config_path(path).resolve()
    if not cfg_path.exists():
        raise FileNotFoundError(f"config file not found: {cfg_path}")
    load_dotenv(cfg_path.parent / ".env", override=False)
    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    cfg = AppConfig.model_validate(raw)
    cfg.base_dir = cfg_path.parent
    return cfg
