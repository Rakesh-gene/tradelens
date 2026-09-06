export const TOKEN_KEY = 'tradelensAccessToken'

export async function apiGet(path, { signal, onUnauthorized } = {}) {
  const token = window.sessionStorage.getItem(TOKEN_KEY)
  const response = await fetch(path, {
    signal,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  let payload = {}
  try { payload = await response.json() } catch { payload = {} }
  if (response.status === 401) {
    window.sessionStorage.removeItem(TOKEN_KEY)
    onUnauthorized?.()
    throw new Error('Your session expired. Please sign in again.')
  }
  if (!response.ok) throw new Error(payload.error || 'TradeLens could not load this data.')
  return payload
}

export async function apiPost(path, body, { signal, onUnauthorized } = {}) {
  const token = window.sessionStorage.getItem(TOKEN_KEY)
  const response = await fetch(path, {
    method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  })
  let payload = {}
  try { payload = await response.json() } catch { payload = {} }
  if (response.status === 401) {
    window.sessionStorage.removeItem(TOKEN_KEY)
    onUnauthorized?.()
    throw new Error('Your session expired. Please sign in again.')
  }
  if (!response.ok) throw new Error(payload.error || 'TradeLens could not complete this request.')
  return payload
}
