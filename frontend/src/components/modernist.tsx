// Shared Modernist primitives (design_handoff_poker_flow). Flat, zero-radius,
// Archivo, 2px rules, one red accent, inverted onto a dark ground. Buttons
// are always uppercase 800 and flush left.

import { ReactNode } from 'react'

export function SectionLabel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`font-extrabold text-[11px] tracking-label uppercase text-ink ${className}`}>
      {children}
    </div>
  )
}

export function Badge({
  children, tone = 'accent',
}: {
  children: ReactNode
  tone?: 'accent' | 'ink' | 'outline'
}) {
  const cls =
    tone === 'accent' ? 'bg-accent text-ground'
    : tone === 'ink' ? 'bg-ink text-ground'
    : 'border border-divider-strong text-ink-muted'
  return (
    <span className={`inline-flex items-center font-extrabold text-[9px] tracking-seat uppercase px-[5px] py-[2px] ${cls}`}>
      {children}
    </span>
  )
}

type BtnVariant = 'outline' | 'accent' | 'ghost' | 'fold'

export function Btn({
  children, onClick, disabled, variant = 'outline', active = false,
  className = '', title, type = 'button',
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: BtnVariant
  active?: boolean
  className?: string
  title?: string
  type?: 'button' | 'submit'
}) {
  const base =
    'font-extrabold text-[11px] tracking-btn uppercase text-left px-3 py-[7px] ' +
    'disabled:opacity-40 disabled:cursor-not-allowed'
  const byVariant: Record<BtnVariant, string> = {
    outline: active
      ? 'bg-ink text-ground'
      : 'border border-divider-strong text-ink hover:bg-[rgba(243,242,242,.1)]',
    accent: 'bg-accent text-ground hover:bg-accent-light active:bg-accent-deep',
    ghost: active
      ? 'bg-ink text-ground'
      : 'text-ink-muted hover:bg-[rgba(243,242,242,.1)]',
    fold: 'border border-divider-strong text-ink hover:border-accent hover:text-accent',
  }
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${byVariant[variant]} ${className}`}
    >
      {children}
    </button>
  )
}

/** Joined segmented control — one active segment, 1px shared borders. */
export function Segmented<T extends string | number>({
  options, value, onChange, size = 'md', className = '', full = false,
}: {
  options: { value: T; label: ReactNode; disabled?: boolean }[]
  value: T | T[]
  onChange: (v: T) => void
  size?: 'sm' | 'md'
  className?: string
  full?: boolean
}) {
  const values = Array.isArray(value) ? value : [value]
  const pad = size === 'sm' ? 'px-[9px] py-[6px] text-[10px]' : 'px-3 py-[7px] text-[11px]'
  return (
    <div className={`${full ? 'flex' : 'inline-flex'} ${className}`}>
      {options.map((o, i) => {
        const on = values.includes(o.value)
        return (
          <button
            key={String(o.value)}
            type="button"
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            className={`font-extrabold tracking-btn uppercase ${pad} border border-divider-strong
              ${full ? 'flex-1 text-center' : ''}
              ${i > 0 ? '-ml-px' : ''}
              ${on ? 'bg-accent text-ground border-accent relative z-10'
                   : 'text-ink-muted hover:bg-[rgba(243,242,242,.08)]'}
              disabled:opacity-30 disabled:cursor-not-allowed`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

const SUIT_GLYPH: Record<string, string> = { h: '♥', d: '♦', c: '♣', s: '♠' }
const RED_SUITS = new Set(['h', 'd'])

/** A card face or back. `card` null → back; `dim` → a folded player's
 *  revealed card. Sizes match the handoff: hole 30x42, board 44x62. */
export function PlayingCard({
  card, w = 30, h = 42, live = false, dim = false, onClick,
}: {
  card?: string | null
  w?: number
  h?: number
  live?: boolean
  dim?: boolean
  onClick?: () => void
}) {
  const style = { width: w, height: h } as const
  if (!card || card.length < 2) {
    return (
      <div
        style={style}
        onClick={onClick}
        className={`border border-divider-mid ${live ? 'bg-surface-deep' : 'bg-surface'} ${onClick ? 'cursor-pointer hover:brightness-125' : ''}`}
      />
    )
  }
  const rank = card[0] === 'T' ? '10' : card[0]
  const suit = card[1]
  const red = RED_SUITS.has(suit)
  return (
    <div
      style={style}
      onClick={onClick}
      className={`flex flex-col items-start justify-start px-1 pt-0.5 leading-none font-extrabold
        ${dim ? 'bg-ink-dim text-surface' : 'bg-[#f8f4f4]'}
        ${!dim && red ? 'text-card-red' : ''} ${!dim && !red ? 'text-ground' : ''}
        ${onClick ? 'cursor-pointer hover:brightness-95' : ''}`}
    >
      <span style={{ fontSize: Math.round(h * 0.34) }}>{rank}</span>
      <span style={{ fontSize: Math.round(h * 0.3) }}>{SUIT_GLYPH[suit] ?? suit}</span>
    </div>
  )
}

/** Horizontal stacked-frequency bar (node action mix, combo action bars). */
export function MixBar({
  segments, height = 26,
}: {
  segments: { pct: number; color: string; key: string }[]
  height?: number
}) {
  return (
    <div className="flex w-full bg-surface-deep" style={{ height }}>
      {segments.map(s => (
        <div key={s.key} style={{ width: `${s.pct * 100}%`, backgroundColor: s.color }} />
      ))}
    </div>
  )
}
