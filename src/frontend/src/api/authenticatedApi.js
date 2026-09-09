import { clearAccessToken, readAccessToken } from '../auth/authSession.js'
import { ApiError, apiRequest } from './apiClient.js'

export async function authenticatedRequest(path, options = {}) {
  try {
    return await apiRequest(path, { ...options, token: readAccessToken() })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      clearAccessToken()
      options.onUnauthorized?.()
      throw new ApiError('Your session expired. Please sign in again.', {
        status: 401,
        code: error.code,
        details: error.details,
        requestId: error.requestId,
      })
    }
    throw error
  }
}
