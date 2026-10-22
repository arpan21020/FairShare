// Shapes returned by the orchestrator (backend/orchestrator/app.py) and the MCP tools'
// `display` cards (backend/houseledger/presenters.py).

export type Money = { paise: number; text: string }

export type Card = { card: string; data: Record<string, unknown> }

export type TraceEntry = {
  tool: string
  arguments: Record<string, unknown>
  ok: boolean
  speech: string
  data: Record<string, unknown>
  ms: number
}

export type SpeakerSource = 'voice_id' | 'said' | 'script'

export type TurnResponse = {
  speech: string
  mode: 'live' | 'scripted'
  cards: Card[]
  trace: TraceEntry[]
  ms: number
  speaker: string | null
  speaker_source: SpeakerSource | null
}

export type ScriptLine = { speaker: string; utterance: string }

export type Config = {
  modes: ('live' | 'scripted')[]
  default_mode: 'live' | 'scripted'
  model: string | null
  mcp_url: string
  mcp_ok: boolean
  household: string
  members: string[]
  script: ScriptLine[]
}

export type Turn = {
  id: number
  speaker: string | null // null until known
  utterance: string
  response?: TurnResponse
  error?: string
}

export type Balance = {
  member: string
  net: Money
  owes: Money
  is_owed: Money
  status: 'owes' | 'is_owed' | 'settled'
}

export type Share = { member: string; amount: Money }

export type Expense = {
  id: number
  payer: string
  amount: Money
  description: string
  category: string
  date: string
  shares: Share[]
}

export type Payment = { id: number; from: string; to: string; amount: Money; date: string; note: string }

export type Transfer = { from: string; to: string; amount: Money }
