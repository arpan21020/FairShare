import type { Config, TurnResponse } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    throw new Error(`The orchestrator returned ${response.status}.`)
  }
  return response.json() as Promise<T>
}

export function fetchConfig(): Promise<Config> {
  return request<Config>('/api/config')
}

export function sendTurn(body: {
  conversation_id: string
  speaker: string // simulated voice ID; empty if unknown
  utterance: string
  mode: 'live' | 'scripted'
}): Promise<TurnResponse> {
  return request<TurnResponse>('/api/turn', { method: 'POST', body: JSON.stringify(body) })
}

export function resetConversation(conversationId: string): Promise<{ ok: boolean }> {
  return request(`/api/conversations/${encodeURIComponent(conversationId)}/reset`, { method: 'POST' })
}
