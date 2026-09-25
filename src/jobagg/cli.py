"""Command-line entry point: ``jobs run|report|sources``."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable

import click

from jobagg import __version__
from jobagg.config import AppConfig, load_config
from jobagg.db import Database
from jobagg.models import Job

log = logging.getLogger("jobagg")


def setup_logging(verbosity: int) -> None:
    level = logging.DEBUG if verbosity >= 1 else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    noisy = logging.WARNING if verbosity < 2 else logging.DEBUG
    for name in ("httpx", "httpcore", "urllib3", "JobSpy"):
        logging.getLogger(name).setLevel(noisy)


def _shorten(text: str | None, width: int) -> str:
    text = text or ""
    return text if len(text) <= width else text[: width - 1] + "…"


def print_jobs(jobs: Iterable[Job], limit: int | None = None) -> None:
    rows = list(jobs)
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        click.echo("(no jobs)")
        return
    header = (f"{'score':>5}  {'title':<44} {'company':<24} {'location':<22} "
              f"{'remote':<8} {'salary':<20} {'tags':<28} sources")
    click.echo(header)
    click.echo("-" * len(header))
    for j in rows:
        score = f"{j.score:5.0f}" if j.score is not None else "    -"
        sources = ",".join(s.source for s in j.all_sources)
        click.echo(
            f"{score}  {_shorten(j.title, 44):<44} {_shorten(j.company, 24):<24} "
            f"{_shorten(j.location, 22):<22} {j.remote_type.value:<8} "
            f"{_shorten(j.salary_text(), 20):<20} "
            f"{_shorten(','.join(j.tech_tags), 28):<28} {sources}"
        )


def _open_db(app: AppConfig) -> Database:
    return Database(app.db_path)


@click.group()
@click.option("--config", "-c", "config_path", type=click.Path(), envvar="JOBAGG_CONFIG",
              default=None, help="Path to config.yaml (default: ./config.yaml).")
@click.option("-v", "--verbose", count=True, help="-v debug logs, -vv also library logs.")
@click.version_option(__version__, prog_name="jobs")
@click.pass_context
def main(ctx: click.Context, config_path: str | None, verbose: int) -> None:
    """Personal job aggregator."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    setup_logging(verbose)
    ctx.ensure_object(dict)
    try:
        ctx.obj["app"] = load_config(config_path)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command()
@click.option("--dry-run", is_flag=True, help="Do everything except send the email.")
@click.option("--source", "-s", "sources", multiple=True, help="Run only these adapter(s).")
@click.option("--limit", default=40, show_default=True, help="Max jobs to print.")
@click.option("--show-all", is_flag=True, help="Print all fetched jobs, not only new ones.")
@click.pass_context
def run(ctx: click.Context, dry_run: bool, sources: tuple[str, ...], limit: int,
        show_all: bool) -> None:
    """Scrape, dedupe, score, store and notify."""
    from jobagg.pipeline import run_pipeline

    app: AppConfig = ctx.obj["app"]
    with _open_db(app) as db:
        summary = run_pipeline(app, db, dry_run=dry_run, only=list(sources) or None)

    click.echo()
    click.echo(f"Run #{summary.run_id}{' (dry run)' if dry_run else ''}: "
               f"{summary.fetched} fetched, {summary.kept} after filters, "
               f"{summary.unique} unique, {len(summary.new_jobs)} new")
    for stat in summary.stats:
        flag = " !! " + stat.warning if stat.warning else ""
        click.echo(f"  {stat.source:<14} {stat.fetched:>4} results  {stat.duration_s:6.1f}s{flag}")
    if summary.dropped:
        click.echo("  dropped: " + ", ".join(f"{k}={v}" for k, v in summary.dropped.most_common()))
    click.echo()
    jobs = summary.all_jobs if show_all else summary.new_jobs
    click.echo("All fetched jobs:" if show_all else "New jobs:")
    print_jobs(sorted(jobs, key=lambda j: (-(j.score or 0), j.title)), limit=limit)
    if len(jobs) > limit:
        click.echo(f"... and {len(jobs) - limit} more")


@main.command()
@click.pass_context
def report(ctx: click.Context) -> None:
    """Regenerate the local HTML report from stored jobs."""
    raise click.ClickException("report is not implemented yet (build step 5)")


@main.command()
@click.option("--all", "include_disabled", is_flag=True, help="Also test disabled adapters.")
@click.option("--source", "-s", "sources", multiple=True, help="Test only these adapter(s).")
@click.pass_context
def sources(ctx: click.Context, include_disabled: bool, sources: tuple[str, ...]) -> None:
    """Test each adapter with one query and print how many results it returns."""
    from jobagg.pipeline import build_queries
    from jobagg.sources import build_sources

    app: AppConfig = ctx.obj["app"]
    queries = build_queries(app)
    adapters = build_sources(app, only=list(sources) or None, include_disabled=include_disabled)
    if not adapters:
        click.echo("no adapters enabled")
        return
    click.echo("Running the first query of each adapter (detail pages are not skipped).")
    for adapter in adapters:
        result = adapter.run(queries, limit=1)
        counts = result.count_by_source(adapter.produces)
        status = "ERROR" if result.errors else "ok"
        label = next(iter(result.per_query), "-")
        click.echo(f"{adapter.name:<14} {status:<5} {len(result.jobs):>4} results, "
                   f"{result.requests:>3} requests in {result.duration_s:5.1f}s  [{label}]  " +
                   ", ".join(f"{k}={v}" for k, v in counts.items()))
        for err in result.errors:
            click.echo(f"    {err}")
        for job in result.jobs[:3]:
            click.echo(f"    - {job.title} @ {job.company} [{job.remote_type.value}] "
                       f"{job.source_url}")


if __name__ == "__main__":
    main()
