// Screen cards for the Echo Show-style display. Each card renders a `display` hint returned by
// a FairShare MCP tool. Cards only show numbers from the server; they never calculate money.

import type { ReactNode } from 'react'
import type { Balance, Card, Expense, Money, Payment, Share, Transfer } from './types'

export function CardView({ card }: { card: Card }) {
  const d = card.data as Record<string, never>
  switch (card.card) {
    case 'confirm_split':
      return <ConfirmSplit payer={d.payer} amount={d.amount} description={d.description} shares={d.shares} />
    case 'expense_added':
      return <ExpenseAdded status={d.status} expense={d.expense} balances={d.balances} />
    case 'balances':
      return <Balances headline={d.headline} balances={d.balances} />
    case 'settle_up':
      return <SettleUp transfers={d.transfers} note={d.note} />
    case 'expense_list':
      return <ExpenseList expenses={d.expenses} payments={d.payments} />
    case 'monthly_summary':
      return <MonthlySummary data={card.data as MonthlyData} />
    case 'members':
      return <Members household={d.household} members={d.members} />
    case 'question':
      return <Notice icon="?" tone="question" title="Alexa is asking" text={d.text} />
    case 'error':
      return <Notice icon="!" tone="error" title="Couldn't do that" text={d.message} />
    default:
      return null
  }
}

function CardShell({ title, tag, children }: { title: string; tag?: string; children: ReactNode }) {
  return (
    <section className="card" aria-label={title}>
      <header className="card-head">
        <h2>{title}</h2>
        {tag && <span className="card-tag">{tag}</span>}
      </header>
      {children}
    </section>
  )
}

function ShareBars({ shares, total }: { shares: Share[]; total: Money }) {
  return (
    <ul className="bars">
      {shares.map((s) => (
        <li key={s.member}>
          <span className="bar-label">{s.member}</span>
          <span className="bar-track" aria-hidden>
            <span className="bar-fill" style={{ width: `${(s.amount.paise / total.paise) * 100}%` }} />
          </span>
          <span className="bar-value">{s.amount.text}</span>
        </li>
      ))}
    </ul>
  )
}

function ConfirmSplit(props: { payer: string; amount: Money; description: string; shares: Share[] }) {
  return (
    <CardShell title="Confirm split" tag="Not saved yet">
      <p className="big-amount">{props.amount.text}</p>
      <p className="muted">
        {props.description ? `${capitalise(props.description)} · ` : ''}paid by <strong>{props.payer}</strong>
      </p>
      <ShareBars shares={props.shares} total={props.amount} />
      <p className="hint">Say “Yes, save it” to confirm.</p>
    </CardShell>
  )
}

function ExpenseAdded(props: { status: string; expense: Expense; balances: Balance[] }) {
  const title = { added: 'Expense saved', updated: 'Expense updated', already_saved: 'Already saved' }[props.status]
  const e = props.expense
  return (
    <CardShell title={title ?? 'Expense'} tag={`#${e.id} · ${e.category}`}>
      <p className="big-amount">{e.amount.text}</p>
      <p className="muted">
        {e.description} · paid by <strong>{e.payer}</strong> · {formatDate(e.date)}
      </p>
      <ShareBars shares={e.shares} total={e.amount} />
      <BalanceRows balances={props.balances} compact />
    </CardShell>
  )
}

function Balances({ headline, balances }: { headline?: string; balances: Balance[] }) {
  return (
    <CardShell title={headline || 'Who owes what'}>
      <BalanceRows balances={balances} />
    </CardShell>
  )
}

const STATUS = {
  is_owed: { icon: '▲', label: 'Is owed' },
  owes: { icon: '▼', label: 'Owes' },
  settled: { icon: '✓', label: 'Settled' },
} as const

function BalanceRows({ balances, compact = false }: { balances: Balance[]; compact?: boolean }) {
  const largest = Math.max(1, ...balances.map((b) => Math.abs(b.net.paise)))
  return (
    <ul className={`balances ${compact ? 'compact' : ''}`}>
      {balances.map((b) => {
        const status = STATUS[b.status]
        const amount = b.status === 'owes' ? b.owes.text : b.status === 'is_owed' ? b.is_owed.text : ''
        const width = `${(Math.abs(b.net.paise) / largest) * 50}%`
        return (
          <li key={b.member} className={`balance ${b.status}`}>
            <span className="avatar" aria-hidden>{b.member[0]}</span>
            <span className="balance-name">{b.member}</span>
            <span className="balance-track" aria-hidden>
              <span className="balance-fill" style={{ width }} />
            </span>
            <span className="balance-status">
              <span aria-hidden>{status.icon}</span> {status.label} {amount}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function SettleUp({ transfers, note }: { transfers: Transfer[]; note: string }) {
  return (
    <CardShell title="Settle up" tag={transfers.length ? `${transfers.length} payment${transfers.length > 1 ? 's' : ''}` : undefined}>
      {transfers.length === 0 ? (
        <p className="big-text">✓ Everyone is settled up.</p>
      ) : (
        <ol className="transfers">
          {transfers.map((t, i) => (
            <li key={i}>
              <span className="avatar" aria-hidden>{t.from[0]}</span>
              <strong>{t.from}</strong>
              <span className="arrow" aria-label="pays">
                <span className="arrow-amount">{t.amount.text}</span>
                <span className="arrow-line" aria-hidden />
              </span>
              <strong>{t.to}</strong>
              <span className="avatar" aria-hidden>{t.to[0]}</span>
            </li>
          ))}
        </ol>
      )}
      <p className="hint">{note}</p>
    </CardShell>
  )
}

function ExpenseList({ expenses, payments }: { expenses: Expense[]; payments: Payment[] }) {
  return (
    <CardShell title="Recent activity">
      <ul className="rows">
        {expenses.map((e) => (
          <li key={`e${e.id}`}>
            <span className="row-date">{formatDate(e.date)}</span>
            <span className="row-main">{e.description} <span className="muted">· {e.payer}</span></span>
            <span className="row-amount">{e.amount.text}</span>
          </li>
        ))}
        {payments.slice(0, 3).map((p) => (
          <li key={`p${p.id}`} className="payment-row">
            <span className="row-date">{formatDate(p.date)}</span>
            <span className="row-main">{p.from} → {p.to} <span className="muted">· payment</span></span>
            <span className="row-amount">{p.amount.text}</span>
          </li>
        ))}
      </ul>
    </CardShell>
  )
}

type MonthlyData = {
  month_name: string
  total: Money
  expense_count: number
  by_category: { category: string; amount: Money }[]
  by_member: { member: string; paid: Money; share: Money }[]
}

function MonthlySummary({ data }: { data: MonthlyData }) {
  const largest = Math.max(1, ...data.by_category.map((c) => c.amount.paise))
  return (
    <CardShell title={data.month_name} tag={`${data.expense_count} expenses`}>
      <p className="big-amount">{data.total.text}</p>
      <ul className="bars">
        {data.by_category.map((c) => (
          <li key={c.category}>
            <span className="bar-label">{capitalise(c.category)}</span>
            <span className="bar-track" aria-hidden>
              <span className="bar-fill" style={{ width: `${(c.amount.paise / largest) * 100}%` }} />
            </span>
            <span className="bar-value">{c.amount.text}</span>
          </li>
        ))}
      </ul>
      <table className="members-table">
        <thead>
          <tr><th scope="col">Member</th><th scope="col">Paid</th><th scope="col">Their share</th></tr>
        </thead>
        <tbody>
          {data.by_member.map((m) => (
            <tr key={m.member}><td>{m.member}</td><td>{m.paid.text}</td><td>{m.share.text}</td></tr>
          ))}
        </tbody>
      </table>
    </CardShell>
  )
}

function Members({ household, members }: { household: string; members: string[] }) {
  return (
    <CardShell title="Household" tag={household}>
      <ul className="member-chips">
        {members.map((m) => (
          <li key={m}><span className="avatar" aria-hidden>{m[0]}</span>{m}</li>
        ))}
      </ul>
    </CardShell>
  )
}

function Notice({ icon, tone, title, text }: { icon: string; tone: string; title: string; text: string }) {
  return (
    <section className={`card notice ${tone}`} aria-label={title}>
      <span className="notice-icon" aria-hidden>{icon}</span>
      <div>
        <h2>{title}</h2>
        <p className="big-text">{text}</p>
      </div>
    </section>
  )
}

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}
