import type { H3Event } from 'h3'
import type { z } from 'zod'

/** Parse query or body with a zod schema; a failure becomes a 400 with the issues attached. */
export function parseQuery<T extends z.ZodType>(event: H3Event, schema: T): z.infer<T> {
  return check(schema.safeParse(getQuery(event)))
}

export async function parseBody<T extends z.ZodType>(event: H3Event, schema: T): Promise<z.infer<T>> {
  return check(schema.safeParse(await readBody(event)))
}

export function parseParams<T extends z.ZodType>(event: H3Event, schema: T): z.infer<T> {
  return check(schema.safeParse(getRouterParams(event)))
}

function check<T>(result: z.ZodSafeParseResult<T>): T {
  if (result.success) return result.data
  throw createError({
    statusCode: 400,
    statusMessage: 'Invalid request',
    data: result.error.issues
  })
}
