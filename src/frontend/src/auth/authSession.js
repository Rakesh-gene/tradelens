export const ACCESS_TOKEN_KEY = 'tradelensAccessToken'

function storage() {
  return typeof window === 'undefined' ? null : window.sessionStorage
}

export function readAccessToken() {
  return storage()?.getItem(ACCESS_TOKEN_KEY) || null
}

export function writeAccessToken(token) {
  if (!token || typeof token !== 'string') throw new TypeError('An access token is required.')
  storage()?.setItem(ACCESS_TOKEN_KEY, token)
}

export function clearAccessToken() {
  storage()?.removeItem(ACCESS_TOKEN_KEY)
}
