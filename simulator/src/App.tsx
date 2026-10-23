import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchConfig, resetConversation, sendTurn } from './api'
import { CardView } from './cards'
import {
  COMMAND_TIMEOUT_MS, FOLLOW_UP_TIMEOUT_MS, NoSpeechError,
  canListen, canSpeak, chime, listenOnce, speak, stopSpeaking,
} from './speech'
import { TracePanel } from './Trace'
import type { Config, Turn } from './types'

const LIVE_SUGGESTIONS = [
  'I paid ₹2,400 for groceries. Split it with Priya and Neha, but Neha was away half the week.',
  'This is Priya. I paid Rahul back ₹500.',
  'Who owes what?',
  'Settle up. What are the fewest payments?',
  'How much did we spend this month?',
  'Undo that.',
]

function newConversationId(): string {
  return `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [configError, setConfigError] = useState('')
  const [mode, setMode] = useState<'live' | 'scripted'>('scripted')
  // Simulated Alexa+ voice ID. null = Alexa doesn't know who is talking yet.
  const [speaker, setSpeaker] = useState<string | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState<'command' | 'follow-up' | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [micError, setMicError] = useState('')
  const [voiceOn, setVoiceOn] = useState(canSpeak)
  const [followUp, setFollowUp] = useState(true)
  const [heardSoFar, setHeardSoFar] = useState('')
  const [conversationId, setConversationId] = useState(newConversationId)
  const stopListening = useRef<() => void>(() => {})
  const nextTurnId = useRef(1)

  // Latest state for callbacks that fire later (e.g. when Alexa finishes speaking).
  const latestState = useRef({ speaker, mode, conversationId, voiceOn, followUp, busy: false, listening: false })
  useEffect(() => {
    Object.assign(latestState.current, { speaker, mode, conversationId, voiceOn, followUp })
  }, [speaker, mode, conversationId, voiceOn, followUp])

  useEffect(() => {
    fetchConfig()
      .then((c) => {
        setConfig(c)
        setMode(c.default_mode)
      })
      .catch(() => setConfigError("Can't reach the orchestrator. Start everything with: python run.py"))
  }, [])

  const latest = turns.at(-1)
  const latestCard = latest?.response?.cards.at(-1)

  const suggestions = useMemo(() => {
    if (!config) return []
    if (mode === 'live') return LIVE_SUGGESTIONS.map((utterance) => ({ speaker: null, utterance }))
    const played = turns.map((t) => t.utterance)
    const lastIndex = config.script.reduce((last, line, i) => (played.includes(line.utterance) ? i : last), -1)
    return config.script.slice(lastIndex + 1, lastIndex + 3)
  }, [config, mode, turns])

  /** Send one turn. `viaVoice` turns get Alexa-style follow-up listening after the reply. */
  async function send(utterance: string, scriptedSpeaker: string | null = null, viaVoice = false) {
    const text = utterance.trim()
    const state = latestState.current
    if (!text || state.busy) return
    const who = scriptedSpeaker ?? state.speaker
    stopSpeaking()
    state.busy = true
    setBusy(true)
    setInput('')
    const id = nextTurnId.current++
    setTurns((prev) => [...prev, { id, speaker: who, utterance: text }])
    let reply: string | null = null
    try {
      const response = await sendTurn({
        conversation_id: state.conversationId, speaker: who ?? '', utterance: text, mode: state.mode,
      })
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, speaker: response.speaker, response } : t)))
      // The server may have recognised who spoke ("This is Priya…"): keep them selected.
      if (response.speaker) {
        setSpeaker(response.speaker)
        state.speaker = response.speaker
      }
      reply = response.speech
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Something went wrong.'
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, error: `${message} Is the orchestrator running?` } : t)))
    } finally {
      state.busy = false
      setBusy(false)
    }
    if (reply === null) return

    // Like an Echo: speak, then (in Follow-Up Mode) listen again without pressing the mic.
    const afterReply = () => {
      setSpeaking(false)
      // A short gap so the tail of Alexa's voice isn't picked up as the next command.
      if (viaVoice && latestState.current.followUp && canListen) setTimeout(() => startListening('follow-up'), 500)
    }
    if (state.voiceOn) {
      setSpeaking(true)
      speak(reply, afterReply)
    } else {
      afterReply()
    }
  }

  function startListening(kind: 'command' | 'follow-up') {
    const state = latestState.current
    if (state.listening || state.busy) return
    stopSpeaking()
    setMicError('')
    setHeardSoFar('')
    if (kind === 'command') chime()
    const session = listenOnce(kind === 'follow-up' ? FOLLOW_UP_TIMEOUT_MS : COMMAND_TIMEOUT_MS, setHeardSoFar)
    stopListening.current = session.stop
    state.listening = true
    setListening(kind)
    session.result
      .then((heard) => {
        void send(heard, null, true)
      })
      .catch((err: Error) => {
        // Silence after a reply just ends the conversation, as on an Echo.
        if (!(err instanceof NoSpeechError) || kind === 'command') setMicError(err.message)
      })
      .finally(() => {
        state.listening = false
        setListening(null)
        setHeardSoFar('')
      })
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void send(input)
  }

  function toggleMic() {
    if (listening) stopListening.current()
    else startListening('command')
  }

  async function startOver() {
    stopListening.current()
    stopSpeaking()
    setSpeaking(false)
    await resetConversation(conversationId).catch(() => {})
    setConversationId(newConversationId())
    setTurns([])
  }

  function changeMode(next: 'live' | 'scripted') {
    if (next === mode) return
    setMode(next)
    void startOver()
  }

  const members = config?.members.length ? config.members : ['Rahul', 'Priya', 'Neha']
  const orbState = listening ? 'listening' : busy ? 'thinking' : 'idle'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>₹</span>
          <div>
            <h1>FairShare</h1>
            <p className="muted">Shared household expenses, settled by voice</p>
          </div>
          <span className="badge">Simulated Alexa+</span>
        </div>
        <div className="controls">
          <div className="segmented" role="group" aria-label="Assistant mode">
            {(['live', 'scripted'] as const).map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={mode === m}
                disabled={!config?.modes.includes(m)}
                title={m === 'live' && !config?.modes.includes('live') ? 'Add an LLM key to .env to enable live mode' : undefined}
                onClick={() => changeMode(m)}
              >
                {m === 'live' ? 'Live (LLM)' : 'Scripted'}
              </button>
            ))}
          </div>
          {canSpeak && (
            <button type="button" className="ghost" aria-pressed={voiceOn} onClick={() => { setVoiceOn(!voiceOn); stopSpeaking() }}>
              {voiceOn ? '🔊 Voice on' : '🔇 Voice off'}
            </button>
          )}
          {canListen && (
            <>
              <button
                type="button"
                className="ghost"
                aria-pressed={followUp}
                onClick={() => setFollowUp(!followUp)}
                title="After Alexa replies, keep listening for about 5 seconds — no need to press the mic again"
              >
                {followUp ? '🔁 Follow-up on' : '🔁 Follow-up off'}
              </button>
            </>
          )}
          <button type="button" className="ghost" onClick={() => void startOver()}>
            New conversation
          </button>
        </div>
      </header>

      {configError && <p className="banner error" role="alert">{configError}</p>}
      {config && !config.mcp_ok && (
        <p className="banner error" role="alert">
          The FairShare MCP server isn't reachable at {config.mcp_url}. Start everything with: python run.py
        </p>
      )}

      <main className="stage">
        <div className="device">
          <div className={`screen ${listening ? 'listening' : ''}`}>
            <div className="screen-top">
              <span className="household">{config?.household || 'Household'}</span>
              <div className="speakers" role="radiogroup" aria-label="Voice ID (simulated)">
                <span className="muted" title="On a real Echo, Alexa+ voice ID recognises who is talking. Here you pick, or just say “This is Priya…”">
                  Voice ID <span className="sim-tag">simulated</span>
                </span>
                <button
                  type="button"
                  role="radio"
                  aria-checked={speaker === null}
                  className="speaker"
                  onClick={() => setSpeaker(null)}
                >
                  <span className="avatar unknown" aria-hidden>?</span>
                  Unknown
                </button>
                {members.map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={speaker === m}
                    className="speaker"
                    onClick={() => setSpeaker(m)}
                  >
                    <span className="avatar" aria-hidden>{m[0]}</span>
                    {m}
                  </button>
                ))}
              </div>
            </div>

            <div className="screen-body">
              <div className="dialog">
                {!latest && (
                  <div className="welcome">
                    <p className="big-text">Say who paid, and how to split it.</p>
                    <p className="muted">
                      Try: “{suggestions[0]?.utterance ?? 'Who owes what?'}”
                    </p>
                  </div>
                )}
                {latest && (
                  <>
                    <p className="you-said">
                      <span className={`avatar ${latest.speaker ? '' : 'unknown'}`} aria-hidden>
                        {latest.speaker?.[0] ?? '?'}
                      </span>
                      <span>
                        <span className="speaker-line">
                          {latest.speaker ?? 'Unknown speaker'}
                          {latest.response?.speaker_source === 'said' && (
                            <span className="sim-tag">recognised from what they said</span>
                          )}
                          {latest.response?.speaker_source === 'voice_id' && <span className="sim-tag">voice ID</span>}
                        </span>
                        “{latest.utterance}”
                      </span>
                    </p>
                    <div className={`orb ${orbState}`} aria-hidden />
                    <p className="alexa-says" aria-live="polite">
                      {latest.error ?? latest.response?.speech ?? 'One moment…'}
                    </p>
                  </>
                )}
              </div>
              <div className="card-area">{latestCard && <CardView card={latestCard} />}</div>
            </div>

            <form className="screen-input" onSubmit={onSubmit}>
              {canListen && (
                <button
                  type="button"
                  className={`mic ${orbState}`}
                  onClick={toggleMic}
                  disabled={busy}
                  aria-label={listening ? 'Stop listening' : `Talk as ${speaker ?? 'an unknown speaker'}`}
                >
                  <svg viewBox="0 0 24 24" aria-hidden>
                    <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z" />
                  </svg>
                </button>
              )}
              <label className="visually-hidden" htmlFor="utterance">What {speaker ?? 'the speaker'} says</label>
              <input
                id="utterance"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={listening ? 'Listening…' : speaker ? `${speaker}: “Alexa, …”` : '“Alexa, this is Priya…”'}
                autoComplete="off"
                disabled={busy}
              />
              <button type="submit" className="send" disabled={busy || !input.trim()}>
                Send
              </button>
            </form>
            <p className="listen-status" role="status">
              {listening && heardSoFar && <>Heard: “{heardSoFar}”</>}
              {listening === 'follow-up' && !heardSoFar && 'Listening for a follow-up…'}
              {listening === 'command' && !heardSoFar && 'Listening…'}
              {!listening && speaking && 'Alexa is speaking…'}
            </p>
            {micError && <p className="mic-error" role="alert">{micError}</p>}
          </div>
          <div className="device-base" aria-hidden />

          {suggestions.length > 0 && (
            <div className="suggestions">
              <p className="muted">{mode === 'scripted' ? 'Next in the demo script' : 'Try saying'}</p>
              <ul>
                {suggestions.map((s) => (
                  <li key={s.utterance}>
                    <button type="button" disabled={busy} onClick={() => void send(s.utterance, s.speaker)}>
                      {s.speaker && <strong>{s.speaker}: </strong>}
                      {s.utterance}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <TracePanel turns={turns} mcpUrl={config?.mcp_url ?? 'http://127.0.0.1:8010/mcp'} />
      </main>

      <footer className="footer muted">
        Simulated Alexa+ experience — Alexa+ integration isn't available to hackathon participants, so this
        device stands in for it. Every number comes from the FairShare MCP server.
        {config?.model && mode === 'live' && <> Live mode model: <code>{config.model}</code>.</>}
        {' '}Demo household data is fictional.
      </footer>
    </div>
  )
}
