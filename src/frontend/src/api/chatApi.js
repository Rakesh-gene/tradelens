import { authenticatedRequest } from './authenticatedApi.js'

export const SETUP_QUESTION = 'What is the setup in Reliance today?'

export function getChatCapabilities(options = {}) {
  return authenticatedRequest('/api/chat/capabilities', options)
}

export function askEquitySetup(message, options = {}) {
  const { contextSymbol, ...requestOptions } = options
  return authenticatedRequest('/api/chat/messages', {
    ...requestOptions, method: 'POST', body: { message, ...(contextSymbol ? { contextSymbol } : {}) },
  })
}

export function getChatConfiguration(options = {}) {
  return authenticatedRequest('/api/admin/chat/configuration', options)
}

export function saveChatConfiguration(body, options = {}) {
  return authenticatedRequest('/api/admin/chat/configuration', { ...options, method: 'PATCH', body })
}
