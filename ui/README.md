# Job aggregator UI

Local, single-user web UI over the Python pipeline's SQLite database. Browse and filter
scored job matches, track your own progress per job (saved, applied, interviewing, offer,
rejected, notes), inspect source health, and start a pipeline run from the browser.

Stack: Nuxt 4, Nuxt UI v4 (Tailwind CSS v4), TypeScript strict, `better-sqlite3` in Nuxt
server routes, `zod` for route input. No auth, no deployment target: it runs on your machine.

## Setup

```bash
cd ui
pnpm install          # better-sqlite3 uses its prebuilt binary; no C++ toolchain needed
cp .env.example .env  # optional, defaults assume ../jobs.sqlite and ../config.yaml
pnpm dev              # http://localhost:3000
```

The pipeline must have run at least once so that `jobs.sqlite` exists. The UI creates its own
`job_state` table on first start and never writes to the pipeline's tables.

## Environment variables

All optional; defaults are relative to the `ui/` folder.

| Variable                | Default            | Purpose                                              |
| ----------------------- | ------------------ | ---------------------------------------------------- |
| `NUXT_DB_PATH`          | `../jobs.sqlite`   | The pipeline's SQLite file                            |
| `NUXT_PIPELINE_CWD`     | `..`               | Working directory for "Run now" (where config.yaml lives) |
| `NUXT_PIPELINE_COMMAND` | `uv run jobs run`  | Command spawned by "Run now" (`--dry-run` is appended when ticked) |
| `NUXT_PIPELINE_SCHEDULE` | `0 7 * * *`       | Cron for the in-process schedule; `""` disables it. Read at startup, so restart after changing |

## Scheduled runs

`server/tasks/pipeline.ts` is a Nitro scheduled task. While the server is up it starts the
pipeline on the cron above through the same runner as "Run now", so it never overlaps a
manual run; the log appears on the runs page. In dev you can trigger it by hand with
`GET http://localhost:3000/_nitro/tasks/pipeline`.

## Running alongside the pipeline

The database is opened in WAL mode with a 5 s busy timeout, so the daily `jobs run` (cron,
Task Scheduler, or the "Run now" button) and the UI can use the file at the same time. When a
run finishes, reload the jobs page to see new matches; the runs page refreshes itself.

`job_state` is the only UI-owned table. Deleting it resets all statuses and notes; the
pipeline's data is unaffected.

## Pages

- **Jobs** (`/`): server-side filtered, sorted and paginated table. Every filter lives in the
  URL, so links are shareable. Row click opens the detail panel; `j`/`k` move a highlight,
  `Enter` opens it, `s` saves, `x` marks not interested, `o` opens the listing, `Esc` clears.
  Checkbox selection enables bulk "Mark seen" / "Not interested".
- **Tracker** (`/tracker`): kanban of saved → applied → interviewing → offer / rejected. Drag
  a card or use its "Move to" menu.
- **Sources & runs** (`/runs`): recent runs with a per-source result matrix. Solid orange =
  a source returned 0 although it usually returns results; solid red = adapter error. "Run
  now" starts one pipeline run at a time and shows its log.
- **Settings** (`/settings`): read-only `config.yaml` with a YAML validity check.

Global shortcuts: `g` then `j` / `t` / `r` / `s` jump between pages.

## Layout

```
shared/        types and the jobs query schema, used by server and client
server/utils   db handle + job_state migration, zod helpers, pipeline runner
server/repositories   all SQL
server/api     thin routes
app/composables useJobs, useJobState, useTracker, useRuns
app/pages      one file per page; app/components/job/* are shared pieces
```

## Checks

```bash
pnpm lint
pnpm typecheck
```
