# CLAUDE.md

Personal job aggregator: a Python scraping/scoring pipeline (`src/jobagg/`) and a local Nuxt
web UI (`ui/`) sharing one SQLite file (`jobs.sqlite`). Single user, runs on the owner's
machine, no deployment. Read `README.md` for the overall picture and `ui/README.md` for the UI.

## Commands

Pipeline (run from the repo root, uses uv):

```bash
uv run pytest                     # unit tests, fixtures only, never the network
uv run ruff check src tests       # lint (line length 100)
uv run mypy src                   # types
uv run jobs run --dry-run         # full live run without notifications (~2-10 min)
uv run jobs sources -s <adapter>  # one live query for one adapter
```

UI (run from `ui/`, uses pnpm):

```bash
pnpm dev          # http://localhost:3000
pnpm lint         # eslint with @nuxt/eslint stylistic rules
pnpm typecheck    # nuxt typecheck (vue-tsc)
```

## Layout

- `config.yaml`: all user-specific settings; `.env`: secrets (never commit).
- `src/jobagg/`: `models.py` (Job schema), `normalize.py` (pure text helpers),
  `config.py`, `db.py` (all SQL), `filters.py`, `dedupe.py`, `scoring.py`, `pipeline.py`
  (orchestration), `cli.py`, `sources/` (one adapter per file, `base.py` is the contract,
  `__init__.py` is the registry).
- `tests/`: one test module per concern; `tests/fixtures/` holds trimmed real responses.
- `ui/shared/`: types and the jobs query schema used by server and client;
  `ui/server/repositories/`: all SQL; `ui/server/api/`: thin zod-validated routes;
  `ui/app/composables/`: data access; `ui/app/pages/`: one file per page.
- `docs/email-digest-plan.md`: the deferred plan for the email digest, `report.html` and
  scheduling docs (pipeline steps 5-6).

## Conventions

- Adapters: check robots.txt and look for JSON/RSS/sitemap before parsing HTML; document
  the chosen method at the top of the file; use `self.get()` (built-in delays), respect
  `self.is_known(url)` before fetching detail pages; add a fixture and a parser test; add a
  registry entry and a `config.yaml` block. Never bypass logins, CAPTCHAs or paywalls.
- The pipeline owns `jobs`, `job_sources`, `runs`, `run_sources`. The UI owns `job_state`
  and must never write to the pipeline's tables; the pipeline must never touch `job_state`.
- Keep request volume low: modest `results_wanted`, jittered delays, detail pages only for
  new listings.
- Python: type hints everywhere, pydantic models for config and data, no live network in
  tests. TS: strict mode, Nuxt UI components over custom ones, URL-driven list state,
  optimistic updates through `useJobState().patch`.
- Known quirks are documented where they bite: LinkedIn "Czech Republic" → Dominican
  Republic (use "Czechia"), Indeed's remote filter returns nothing for CZ, Google Jobs
  serves a JS-only page, better-sqlite3 uses its prebuilt binary (`pnpm-workspace.yaml`
  disables its rebuild script).

## Workflow with the owner

Work proceeds in numbered build steps with review checkpoints; do not start the next step
after a checkpoint until it is confirmed. Commit per step with a descriptive message.
Live runs are fine for verification but keep them to what the check needs.
