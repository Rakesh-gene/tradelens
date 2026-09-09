import { apiRequest } from './apiClient.js'

export function login(credentials, options = {}) {
  return apiRequest('/api/login', { ...options, method: 'POST', body: credentials })
}

export function register(registration, options = {}) {
  return apiRequest('/api/register', { ...options, method: 'POST', body: registration })
}

export function getCurrentUser(token, options = {}) {
  return apiRequest('/api/auth/me', { ...options, token })
}
