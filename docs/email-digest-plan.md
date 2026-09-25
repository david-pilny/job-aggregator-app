# Plan: email digest, HTML report and scheduling (pipeline steps 5–6)

Status: **not started, low priority.** The web UI (`ui/`) currently covers browsing and
tracking, so the digest is a convenience rather than a blocker. Everything below is written
against the code as of 2026-09-25 so it can be picked up cold.

## What already exists

- `config.yaml` has the `notify.email` section (`enabled`, `to`, `subject_prefix`,
  `min_score`, `max_items`) and `report` (`path`, `min_score`); `.env.example` lists
  `SMTP_HOST/PORT/USER/PASSWORD/FROM` and `EMAIL_TO`. `src/jobagg/config.py` already
  validates these into `EmailConfig` / `ReportConfig`.
- `jobs run` produces a `RunSummary` (`src/jobagg/pipeline.py`) with `new_jobs`,
  `all_jobs`, per-source `stats` (each with an optional health `warning`), `errors` and
  `dropped` counts. `db.finish_run()` takes a `notified` flag that is currently always
  `False`.
- `Job.score_breakdown`, `Job.all_sources`, `Job.salary_text()` and `Job.tech_tags` give
  the digest everything it needs to render a row.
- `jobs report` in `src/jobagg/cli.py` is a stub that raises "not implemented".
- `db.active_jobs(active_days)` returns the rescored active set for the report.
- The `--dry-run` flag exists and is stored on the run; it must keep meaning
  "do everything except send the email".

## Step 5a: email digest (`src/jobagg/notify.py`)

**Content** (one email per run, only when there is at least one new match ≥ `min_score`):

1. Subject: `{subject_prefix} {n} new matches ({top_title} @ {company}, …)` — keep under
   ~80 chars.
2. New matches sorted by score desc, capped at `max_items`. Per job: title (linked to the
   primary URL), company, location + remote badge, salary if known, tech tags, score with
   the breakdown in a `title` tooltip, and one link per source (`job.all_sources`).
3. A short "Source health" section at the bottom: per source `fetched` count and duration
   from `summary.stats`; any `warning` (zero results / error) rendered in red. Also list
   `summary.errors` and the `dropped` counter one-liner.
4. Footer: run id, timestamps, link to the local report file and to the UI
   (`http://localhost:3000/?minScore=…`).

**Implementation notes**

- Render with a small Jinja-free approach: an f-string/`html.escape` template module
  (`jobagg/templates/digest.py`) producing both `text/plain` and `text/html` parts via
  `email.message.EmailMessage.add_alternative`. No new dependency needed.
- `send_digest(summary, app) -> bool` using `smtplib.SMTP` + `starttls()` (port 587) with
  a fallback to `SMTP_SSL` when `SMTP_PORT == 465`. Read credentials from env only
  (`os.environ`), never from `config.yaml`. Missing credentials → log a warning and return
  `False`; never raise past the pipeline.
- Recipient: `EMAIL_TO` env overrides `notify.email.to`.
- Wire into `run_pipeline`: after scoring, `if not dry_run and email.enabled: notified =
  send_digest(...)`, then pass `notified` to `db.finish_run`. In `--dry-run`, still build
  the digest and write it to `digest.html` next to the DB so the layout can be checked
  without sending (this file is already in `.gitignore`).
- CLI: `jobs run` gains `--print-digest` to dump the text part to stdout.
- Tests: render the digest from a fixed `RunSummary` (two jobs, one health warning) and
  assert on the HTML/plain text; test the SMTP path with `unittest.mock` on
  `smtplib.SMTP` (assert `starttls`, `login`, `send_message` calls). No network.

**Open decisions**

- Threshold: send only when new matches ≥ `min_score`, or always send with a "nothing new"
  line so silence never means "broken"? Suggest: always send when a source health warning
  exists, otherwise only with matches.
- Should the digest include jobs re-seen with a *changed* salary/description? Not for v1.

## Step 5b: HTML report (`src/jobagg/report.py`, `jobs report`)

Self-contained `report.html` with all active jobs (`db.active_jobs`) scoring ≥
`report.min_score`, generated on every run and by `jobs report`.

- Inline CSS + a small inline `<script>`; the job rows are embedded as a JSON array and
  rendered client-side so filtering (min score slider, remote type, source, status if the
  `job_state` table exists) and sorting (score, date, salary) work offline.
- Read `job_state` **if present** (the UI creates it) so the report can show saved/applied
  flags; the pipeline must not create or write that table.
- Since the Nuxt UI now exists, keep this deliberately simple: it is the "open it on a
  phone from the email link" fallback, not a second UI.
- Test: generate from three fixture jobs and assert the JSON payload and a few rendered
  strings.

## Step 6: scheduling and README

- Root `README.md`: setup (`uv sync`, `config.yaml`, `.env`), how to run, how to add a
  source (Source subclass, `produces`, fixture + test, registry entry, config block), known
  limitations (LinkedIn has no descriptions unless `linkedin_fetch_description`, Google Jobs
  blocked from many networks, jobs.cz/prace.cz detail pages are JS widgets, WTTJ sitemap
  cost, "Czech Republic" vs "Czechia" LinkedIn quirk), and why GitHub Actions / cloud
  runners are not the default (boards block datacenter IPs).
- Scheduling instructions for all three: cron (`crontab -e`, `0 7 * * * cd … && uv run
  jobs run >> logs/run.log 2>&1`), launchd (`~/Library/LaunchAgents/…plist` with
  `StartCalendarInterval`), and Windows Task Scheduler (`schtasks /create /sc daily /tn
  jobagg /tr "…" /st 07:00`) since this project currently runs on Windows.
- Mention the UI's "Run now" as the manual alternative and that both can share the DB (WAL).

## Rough order when picked up

1. `notify.py` rendering + tests (no SMTP yet) → check `digest.html` from a dry run.
2. SMTP sending + `notified` flag + CLI flag.
3. `report.py` + `jobs report`.
4. README + scheduling docs.
