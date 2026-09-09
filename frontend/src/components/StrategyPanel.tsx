import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { SpotActionOption } from '../types'

const HERO_FILL = '#184f95'
const VILLAIN_FILL = '#b45309'
const GRIDLINE = '#e1e0d9'
const AXIS_INK = '#898781'

interface Row {
  id: number
  label: string
  freq: number
  option: SpotActionOption
}

interface Props {
  options: SpotActionOption[]
  frequencies: Record<string, number>
  whoseTurn: 'hero' | 'villain'
  description: string
  onPickAction: (option: SpotActionOption) => void
}

export function StrategyPanel({ options, frequencies, whoseTurn, description, onPickAction }: Props) {
  const rows: Row[] = options.map(o => ({
    id: o.action,
    label: o.label,
    freq: frequencies[String(o.action)] ?? 0,
    option: o,
  }))
  const fill = whoseTurn === 'hero' ? HERO_FILL : VILLAIN_FILL

  return (
    <div className="flex flex-col gap-2">
      <div className="text-xs text-gray-500">{description}</div>
      <ResponsiveContainer width="100%" height={Math.max(120, rows.length * 32)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 8 }}>
          <XAxis
            type="number" domain={[0, 1]}
            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
            stroke={GRIDLINE} tick={{ fill: AXIS_INK, fontSize: 11 }}
          />
          <YAxis type="category" dataKey="label" width={130} stroke={GRIDLINE} tick={{ fill: AXIS_INK, fontSize: 11 }} />
          <Tooltip formatter={(v: unknown) => `${(Number(v) * 100).toFixed(1)}%`} />
          <Bar
            dataKey="freq" radius={[0, 4, 4, 0]} maxBarSize={20}
            onClick={(data: unknown) => onPickAction((data as Row).option)}
            cursor="pointer"
          >
            {rows.map(r => <Cell key={r.id} fill={fill} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex gap-2 flex-wrap">
        {options.map(o => (
          <button
            key={o.action}
            onClick={() => onPickAction(o)}
            className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-100"
          >
            {o.label} ({((frequencies[String(o.action)] ?? 0) * 100).toFixed(1)}%)
          </button>
        ))}
      </div>
    </div>
  )
}
