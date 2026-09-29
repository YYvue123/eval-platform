/**
 * URL list query helpers. Page catch must not assign items=[] without setting an error flag.
 */
export function readListQuery(query = {}) {
  const page = Math.max(1, Number.parseInt(query.page, 10) || 1)
  let page_size = Number.parseInt(query.page_size, 10)
  if (!Number.isFinite(page_size) || page_size < 1) page_size = 20
  page_size = Math.min(100, page_size)
  const q = typeof query.q === 'string' ? query.q : ''
  const status = typeof query.status === 'string' ? query.status : ''
  return { page, page_size, q, status }
}

export async function writeListQuery(router, patch) {
  const current = { ...(router.currentRoute.value.query || {}) }
  const next = { ...current, ...patch }
  for (const key of Object.keys(next)) {
    const v = next[key]
    if (v === '' || v == null) delete next[key]
    else next[key] = String(v)
  }
  return router.replace({ query: next })
}
