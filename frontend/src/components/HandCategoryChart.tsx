// GTO+-style range composition chart: buckets the range into made-hand
// categories (straight, top pair, weak pair, no made hand, ...) and draw
// categories (flush draw, gutshot, ...), each as a stacked bar split by
// this node's actions — a category-level analog of RangeBreakdownTable.

import { BarChart, Bar, XAxis, YAxis, Tooltip, LabelList, ResponsiveContainer } from 'recharts'
import { CategoryGroup, SpotActionOption } from '../types'
import { actionColor } from '../utils/categoricalColors'

const GRIDLINE = '#e1e0d9'
const AXIS_INK = '#898781'
const LABEL_INK = '#52514e'

// Distinguishes the two backend-emitted groups (_MADE_HAND_ORDER vs
// _DRAW_ORDER in src/api.py) so they render as separate mini-charts, since
// a combo can appear in both (e.g. a weak pair with a gutshot).
const MADE_HAND_NAMES = new Set([
  'Straight Flush', 'Four of a Kind', 'Full House', 'Flush', 'Straight',
  'Three of a Kind', 'Two Pair', 'Overpair', 'Top Pair', 'Middle Pair',
  'Weak Pair', 'No Made Hand',
])

interface Props {
  categories: CategoryGroup[]
  options: SpotActionOption[]
}

function toRows(cats: CategoryGroup[], options: SpotActionOption[]) {
  return cats.map(c => {
    const row: Record<string, string | number> = { category: c.category, total: c.n_combos }
    options.forEach(o => { row[`a${o.action}`] = c.frequencies[String(o.action)] ?? 0 })
    return row
  })
}

function MiniChart({ cats, options, title }: { cats: CategoryGroup[]; options: SpotActionOption[]; title: string }) {
  if (cats.length === 0) return null
  const rows = toRows(cats, options)
  const lastAction = options[options.length - 1]?.action

  return (
    <div className="flex flex-col gap-1">
      <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide">{title}</div>
      <ResponsiveContainer width="100%" height={Math.max(50, rows.length * 24)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 2, right: 34, bottom: 2, left: 4 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="category" width={112} stroke={GRIDLINE} tick={{ fill: AXIS_INK, fontSize: 11 }} />
          <Tooltip
            formatter={(v: unknown, name: unknown) => {
              const opt = options.find(o => `a${o.action}` === String(name))
              return [`${Number(v).toFixed(1)} combos`, opt?.label ?? String(name)]
            }}
          />
          {options.map(o => (
            <Bar key={o.action} dataKey={`a${o.action}`} stackId="cat" fill={actionColor(o.action)}>
              {o.action === lastAction && (
                <LabelList
                  dataKey="total"
                  position="right"
                  formatter={(v: unknown) => Number(v).toFixed(1)}
                  fill={LABEL_INK}
                  fontSize={10}
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function HandCategoryChart({ categories, options }: Props) {
  if (categories.length === 0) return null
  const made = categories.filter(c => MADE_HAND_NAMES.has(c.category))
  const draws = categories.filter(c => !MADE_HAND_NAMES.has(c.category))

  return (
    <div className="flex flex-col gap-3 border border-gray-200 rounded-md p-2">
      <MiniChart cats={made} options={options} title="Made hands" />
      <MiniChart cats={draws} options={options} title="Draws" />
      <div className="flex gap-3 flex-wrap text-[10px] text-gray-500 border-t border-gray-100 pt-1.5">
        {options.map(o => (
          <span key={o.action} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ backgroundColor: actionColor(o.action) }} />
            {o.label}
          </span>
        ))}
      </div>
    </div>
  )
}
