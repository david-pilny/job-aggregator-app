import { readFile, stat } from 'node:fs/promises'
import { resolve } from 'node:path'
import { parse as parseYaml } from 'yaml'

/** Read-only view of the pipeline's config.yaml, with a validity check. */
export default defineEventHandler(async () => {
  const { pipelineCwd } = useRuntimeConfig()
  const path = resolve(process.cwd(), pipelineCwd, 'config.yaml')
  try {
    const [content, info] = await Promise.all([readFile(path, 'utf-8'), stat(path)])
    let valid = true
    let error: string | null = null
    try {
      parseYaml(content)
    } catch (e) {
      valid = false
      error = e instanceof Error ? e.message : String(e)
    }
    return { path, content, valid, error, modifiedAt: info.mtime.toISOString() }
  } catch (e) {
    throw createError({
      statusCode: 404,
      statusMessage: `config.yaml not found at ${path}: ${e instanceof Error ? e.message : e}`
    })
  }
})
