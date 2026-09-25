# Job aggregator

Personal tool that collects developer job listings from several job portals once a day,
merges them into one deduplicated list, scores them against my profile (Vue / Nuxt /
TypeScript, remote-first, Prague) and stores everything in SQLite. A local web UI browses
the matches and tracks applications.

Two parts, one repository:

| Part | Where | Stack |
| --- | --- | --- |
| Pipeline (scrape → filter → dedupe → score → store) | `src/jobagg/` | Python 3.11+, python-jobspy, httpx, selectolax, pydantic, rapidfuzz, SQLite |
| Web UI (browse, filter, track, run) | `ui/` | Nuxt 4, Nuxt UI v4, better-sqlite3 — see [`ui/README.md`](ui/README.md) |

Personal use only: request volume is low and polite, robots.txt is respected, nothing
behind a login is touched, and only the fields needed for matching are stored.

## Setup

```bash
uv sync                         # creates .venv with all dependencies
cp .env.example .env            # SMTP settings, only needed for the (future) email digest
uv run jobs sources             # one live query per adapter to check they work
uv run jobs run --dry-run       # full run: scrape, filter, dedupe, score, store (no email)
```

`uv run jobs run` prints a summary and the new jobs, and writes everything to
`jobs.sqlite` next to `config.yaml`. The first run is slow (about 10 minutes) because the
sitemap-based adapters fetch their backlog of detail pages; later runs only fetch listings
that are not stored yet.

Then start the UI:

```bash
cd ui && pnpm install && pnpm dev     # http://localhost:3000
```

### One command for everything

The UI server also schedules the pipeline: while `pnpm dev` (or a production
`node .output/server/index.mjs`) is running, Nitro's cron runner starts `jobs run` at
07:00 every day (`NUXT_PIPELINE_SCHEDULE`, see `ui/.env.example`), with the log on the
runs page. So from the repo root:

```bash
pnpm dev            # UI + scheduled pipeline runs
pnpm start          # one dry pipeline run first, then the UI
pnpm pipeline       # just the pipeline
pnpm test           # pytest + UI lint + typecheck
```

The OS scheduler below is only needed if the pipeline should run while the UI is closed.

## CLI

| Command | What it does |
| --- | --- |
| `jobs run` | Scrape all enabled sources, filter, dedupe, score, store, notify (email not built yet) |
| `jobs run --dry-run` | Same, but never sends anything |
| `jobs run --show-all` | Print every fetched job, not only the new ones |
| `jobs run -s jobs_cz -s jobstack` | Run only the given adapters |
| `jobs sources [--all]` | Run the first query of each adapter and print counts, request numbers and errors |
| `jobs report` | Not implemented yet, see `docs/email-digest-plan.md` |

Add `-v` for debug logs, `-c path/to/config.yaml` to use another config.

## Configuration

Everything user-specific lives in `config.yaml`; nothing is hardcoded. The main sections:

- `search.terms` × `search.locations`: the queries most adapters run. Use "Czechia", not
  "Czech Republic" (LinkedIn maps the latter to the Dominican Republic).
- `sources.<name>`: `enabled` plus adapter-specific options. Each adapter documents its
  options and its data-access method at the top of its file in `src/jobagg/sources/`.
- `filters`: `max_age_days`, whole-word `exclude_title_keywords`, allowed `languages`.
- `dedupe`: title similarity threshold (rapidfuzz `token_set_ratio`, default 85) and the
  description fallback.
- `scoring`: weights (stack 45, remote 25, seniority 15, salary 5, freshness 10), which
  tags count as "stack", remote ranking, seniority keywords, and a `relevance` hook where an
  LLM-based check can be plugged in later (`module:Class` implementing
  `jobagg.scoring.RelevanceChecker`).
- `tech_tags`: keyword dictionary used to extract tags from titles and descriptions.
- `http`: user agent, timeout, randomized delay between requests, optional proxies.

Secrets go in `.env` (never committed).

## How it works

1. Every adapter implements `fetch(query) -> list[Job]` (`src/jobagg/sources/base.py`).
   The base class provides an HTTP client with a 2–5 s jittered pause before each request,
   per-query error isolation, tag extraction, and "known URL" skipping: listings already in
   the database are marked as seen again instead of re-fetched.
2. Hard filters drop excluded titles, old postings and unwanted languages.
3. Dedup merges listings of the same job: same normalized company (legal forms such as
   s.r.o., a.s., GmbH stripped) and similar title. Within a run this is a union-find over
   company groups; against the database, a fuzzy match adopts the stored job's id, so a
   re-listed job is never "new" again. The richest listing (salary, longest description)
   becomes the primary record and every source URL is kept.
4. Scoring gives 0–100 from the configured weights; the breakdown is stored per job and
   all active jobs are rescored on every run so freshness decays.
5. Storage: `jobs`, `job_sources`, `runs`, `run_sources` in SQLite (WAL mode). A job is
   new when its id was never seen. A source that returns 0 after averaging results before
   is flagged in the run summary and on the UI's runs page.

## Sources

| Adapter | Method | Notes |
| --- | --- | --- |
| `jobspy` (LinkedIn, Indeed, Google Jobs) | python-jobspy | Google is off by default: it serves a JavaScript-only page to the scraper from most networks |
| `jobs_cz`, `prace_cz` | server-rendered search cards | Internal APIs are disallowed by robots.txt; detail pages are JS widgets, so no descriptions |
| `jobstack` | category listing pages | Rich cards (salary, city, hybrid label, seniority) |
| `cocuma` | paged list + detail pages for new keyword matches | Search is disallowed by robots.txt |
| `startupjobs` | offers sitemap + JSON-LD on detail pages | Backend API disallows all bots |
| `wttj` (Welcome to the Jungle) | job sitemaps (~25 MB/run) + JSON-LD | Search URLs are disallowed; low yield for Czechia, disable if unwanted |
| `remotive`, `arbeitnow` | public JSON APIs | Loose search, so a keyword relevance filter is applied |
| `weworkremotely` | category RSS feeds | Region filter keeps worldwide/Europe roles |

### Adding a source

1. Check robots.txt, then look for a JSON endpoint, RSS feed or sitemap before touching HTML.
2. Create `src/jobagg/sources/<name>.py` with a `Source` subclass: set `name` (the config
   key) and `produces` (the value stored in `Job.source`), implement `fetch(query)`, and
   document the method at the top of the file. Use `self.get(url)` for HTTP (delays and
   errors are handled), `self.tag(...)` for tech tags, `self.is_known(url)` /
   `self.mark_seen(url)` before fetching detail pages.
3. Register it in `src/jobagg/sources/__init__.py` and add a `sources.<name>` block to
   `config.yaml`.
4. Save a trimmed real response under `tests/fixtures/` and add a parser test in
   `tests/test_adapters.py`. Tests never touch the network.
5. `uv run jobs sources -s <name>` for a live smoke test.

## Scheduling

Run it on your own machine; job boards often block datacenter IPs, which is why GitHub
Actions or cloud runners are not the default.

**cron (Linux/macOS)**

```
0 7 * * * cd /path/to/job-aggretor && uv run jobs run >> logs/run.log 2>&1
```

**launchd (macOS)** — save as `~/Library/LaunchAgents/cz.pilny.jobagg.plist`, then
`launchctl load` it:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>cz.pilny.jobagg</string>
  <key>ProgramArguments</key><array>
    <string>/opt/homebrew/bin/uv</string><string>run</string><string>jobs</string><string>run</string>
  </array>
  <key>WorkingDirectory</key><string>/path/to/job-aggretor</string>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/path/to/job-aggretor/logs/run.log</string>
  <key>StandardErrorPath</key><string>/path/to/job-aggretor/logs/run.log</string>
</dict></plist>
```

**Windows Task Scheduler**

```
schtasks /create /sc daily /st 07:00 /tn jobagg /tr "cmd /c cd /d C:\path\to\job-aggretor && uv run jobs run >> logs\run.log 2>&1"
```

The UI's "Run now" button and its built-in schedule are the alternatives; everything can
use the database at the same time thanks to WAL mode. Do not run both the OS scheduler and
the UI schedule at the same time of day; a second run is harmless but wasteful.

## Development

```bash
uv run pytest            # 51 tests, fixtures only, no network
uv run ruff check src tests
uv run mypy src
```

## Known limitations

- LinkedIn returns no descriptions unless `linkedin_fetch_description` is on (one extra
  request per job); tags for those jobs come from the title only.
- Remote-type and language detection are keyword heuristics; "home office" in Czech
  listings often means occasional, which is classified as hybrid only when the card says so.
- Salaries are rare on LinkedIn and Indeed CZ; the Czech boards and startupjobs provide most
  of them.
- Fuzzy dedup can merge two genuinely different openings with the same title at one
  company (for example in two cities); all URLs are kept, so nothing is lost.
- Email digest and `report.html` are not built yet: see `docs/email-digest-plan.md`.
