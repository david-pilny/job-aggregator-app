import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import Database from 'better-sqlite3'

/**
 * One better-sqlite3 handle per Nitro process. The pipeline owns every table
 * except `job_state`, which is created here on first use. WAL mode lets the
 * daily `jobs run` write while the UI reads, and `busy_timeout` makes the two
 * wait for each other instead of failing with SQLITE_BUSY.
 */

const MIGRATIONS = [
  `CREATE TABLE IF NOT EXISTS job_state (
    job_id     TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'new',
    notes      TEXT,
    applied_at TEXT,
    updated_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_job_state_status ON job_state(status)`
]

let db: Database.Database | undefined

export function useDb(): Database.Database {
  if (db) return db
  const { dbPath } = useRuntimeConfig()
  const path = resolve(process.cwd(), dbPath)
  if (!existsSync(path)) {
    throw createError({
      statusCode: 500,
      statusMessage: `Database not found at ${path}. Set NUXT_DB_PATH to the pipeline's jobs.sqlite.`
    })
  }
  const handle = new Database(path)
  handle.pragma('journal_mode = WAL')
  handle.pragma('busy_timeout = 5000')
  handle.pragma('foreign_keys = ON')
  for (const sql of MIGRATIONS) handle.exec(sql)
  db = handle
  return db
}
