import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from 'recharts'
import { FingerprintTypeCount } from '../types'
import { fingerprintKeyId, fingerprintShortLabel, fingerprintFullDescription } from '../utils/fingerprintKey'

const UNSELECTED_FILL = '#6da7ec'  // sequential blue, step 300
const SELECTED_FILL = '#184f95'    // sequential blue, step 600
const AXIS_INK = '#898781'         // muted ink
const GRIDLINE = '#e1e0d9'         // hairline gray

interface Props {
  types: FingerprintTypeCount[]
  selectedIds: Set<string>
  onToggle: (id: string) => void
}

interface ChartRow {
  id: string
  label: string
  count: number
  selected: boolean
  tooltipLines: string[]
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ChartRow }> }) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0].payload
  return (
    <div className="bg-white border border-gray-200 rounded-md shadow-md px-3 py-2 text-xs text-gray-700 max-w-xs">
      <div className="font-semibold text-gray-900 mb-1">{row.count.toLocaleString()} hands</div>
      {row.tooltipLines.map((line, i) => (
        <div key={i}>{line}</div>
      ))}
    </div>
  )
}

export function FingerprintDistributionChart({ types, selectedIds, onToggle }: Props) {
  const rows: ChartRow[] = types.map(t => {
    const id = fingerprintKeyId(t.key)
    const selected = selectedIds.has(id)
    return {
      id,
      label: `${selected ? '✓ ' : ''}${fingerprintShortLabel(t.key)}`,
      count: t.count,
      selected,
      tooltipLines: fingerprintFullDescription(t.key),
    }
  })

  const height = Math.max(240, rows.length * 28)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={rows}
        layout="vertical"
        barCategoryGap={2}
        margin={{ top: 8, right: 24, bottom: 8, left: 8 }}
      >
        <XAxis
          type="number"
          tickFormatter={(v: number) => v.toLocaleString()}
          stroke={GRIDLINE}
          tick={{ fill: AXIS_INK, fontSize: 11 }}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={260}
          stroke={GRIDLINE}
          tick={{ fill: AXIS_INK, fontSize: 11 }}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
        <Bar
          dataKey="count"
          radius={[0, 4, 4, 0]}
          maxBarSize={20}
          onClick={(data: unknown) => onToggle((data as ChartRow).id)}
          cursor="pointer"
        >
          {rows.map(row => (
            <Cell key={row.id} fill={row.selected ? SELECTED_FILL : UNSELECTED_FILL} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
