import { spawn, type ChildProcess } from 'node:child_process'
import { resolve } from 'node:path'
import type { RunnerState } from '#shared/types/run'

/**
 * Runs the Python CLI as a child process, one at a time. The command and
 * working directory come from runtimeConfig; the client polls `getState()`.
 * Output is kept in a bounded ring buffer so a chatty run cannot grow memory.
 */

const MAX_LOG_LINES = 500

const state: RunnerState = {
  status: 'idle',
  command: null,
  startedAt: null,
  finishedAt: null,
  exitCode: null,
  log: []
}

let child: ChildProcess | null = null
let partial = ''

function pushLines(chunk: string) {
  partial += chunk.replace(/\r\n?/g, '\n')
  const lines = partial.split('\n')
  partial = lines.pop() ?? ''
  for (const line of lines) {
    if (!line.trim()) continue
    state.log.push(line)
    if (state.log.length > MAX_LOG_LINES) state.log.splice(0, state.log.length - MAX_LOG_LINES)
  }
}

export function getRunnerState(): RunnerState {
  return { ...state, log: [...state.log] }
}

export function isRunning(): boolean {
  return state.status === 'running'
}

export function startPipeline({ dryRun = false } = {}): RunnerState {
  if (isRunning()) {
    throw createError({ statusCode: 409, statusMessage: 'A run is already in progress' })
  }
  const { pipelineCommand, pipelineCwd } = useRuntimeConfig()
  const cwd = resolve(process.cwd(), pipelineCwd)
  const command = dryRun ? `${pipelineCommand} --dry-run` : pipelineCommand

  Object.assign(state, {
    status: 'running',
    command,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    exitCode: null,
    log: [`$ ${command}  (cwd: ${cwd})`]
  })
  partial = ''

  // `shell: true` lets the configured command be a plain string such as "uv run jobs run".
  child = spawn(command, { cwd, shell: true, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } })
  child.stdout?.setEncoding('utf-8').on('data', pushLines)
  child.stderr?.setEncoding('utf-8').on('data', pushLines)
  child.on('error', (error) => {
    pushLines(`\n[runner] failed to start: ${error.message}\n`)
    finish(-1)
  })
  child.on('close', code => finish(code ?? -1))
  return getRunnerState()
}

function finish(code: number) {
  if (partial) pushLines('\n')
  state.status = code === 0 ? 'succeeded' : 'failed'
  state.exitCode = code
  state.finishedAt = new Date().toISOString()
  child = null
}
