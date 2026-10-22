// "Under the hood" panel: every MCP tools/call the assistant made, newest turn first.

import type { Turn } from './types'

export function TracePanel({ turns, mcpUrl }: { turns: Turn[]; mcpUrl: string }) {
  const withCalls = [...turns].reverse()
  return (
    <aside className="trace" aria-label="MCP trace">
      <header className="trace-head">
        <h2>MCP trace</h2>
        <p className="muted">
          Streamable HTTP · <code>{mcpUrl}</code>
        </p>
      </header>
      {withCalls.length === 0 && <p className="muted trace-empty">Tool calls will appear here.</p>}
      <ol className="trace-turns">
        {withCalls.map((turn) => (
          <li key={turn.id} className="trace-turn">
            <p className="trace-utterance">
              <strong>{turn.response?.speaker ?? turn.speaker ?? 'Unknown speaker'}:</strong> “{turn.utterance}”
            </p>
            {turn.response && turn.response.trace.length === 0 && (
              <p className="muted trace-none">No tool call — Alexa replied directly.</p>
            )}
            {turn.response?.trace.map((call, i) => (
              <details key={i} className={`trace-call ${call.ok ? 'ok' : 'failed'}`}>
                <summary>
                  <span className="trace-method">tools/call</span> <strong>{call.tool}</strong>
                  <span className="trace-meta">
                    {call.ok ? '✓' : '✗ error'} · {call.ms} ms
                  </span>
                </summary>
                <p className="trace-label">arguments</p>
                <pre>{JSON.stringify(call.arguments, null, 2)}</pre>
                <p className="trace-label">result · speech</p>
                <p className="trace-speech">{call.speech}</p>
                <p className="trace-label">result · data</p>
                <pre>{JSON.stringify(call.data, null, 2)}</pre>
              </details>
            ))}
            {turn.response && (
              <p className="trace-footer muted">
                {turn.response.mode === 'live' ? 'LLM-driven' : 'Scripted'} · turn took {turn.response.ms} ms
              </p>
            )}
          </li>
        ))}
      </ol>
    </aside>
  )
}
