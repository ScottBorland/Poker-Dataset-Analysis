import { useCallback, useEffect, useMemo, useState } from 'react'
import { FingerprintDistributionChart } from '../components/FingerprintDistributionChart'
import { HandsTable } from '../components/HandsTable'
import { getFingerprintDistributionApi, getFingerprintHandsApi } from '../utils/api'
import { FingerprintKey, FingerprintTypeCount, FingerprintHandRow } from '../types'
import { fingerprintKeyId, fingerprintShortLabel } from '../utils/fingerprintKey'

const STREETS = ['preflop', 'flop', 'turn', 'river'] as const
const HANDS_PAGE_SIZE = 100

export default function FingerprintExplorerPage() {
  const [street, setStreet] = useState<string>('flop')
  const [only888, setOnly888] = useState(false)
  const [types, setTypes] = useState<FingerprintTypeCount[]>([])
  const [totalDistinctTypes, setTotalDistinctTypes] = useState(0)
  const [totalRows, setTotalRows] = useState(0)
  const [distLoading, setDistLoading] = useState(false)
  const [distError, setDistError] = useState<string | null>(null)

  const [selected, setSelected] = useState<Map<string, FingerprintKey>>(new Map())

  const [hands, setHands] = useState<FingerprintHandRow[]>([])
  const [handsTotal, setHandsTotal] = useState(0)
  const [handsOffset, setHandsOffset] = useState(0)
  const [handsLoading, setHandsLoading] = useState(false)
  const [handsError, setHandsError] = useState<string | null>(null)
  const [handsLoaded, setHandsLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    setDistLoading(true)
    setDistError(null)
    getFingerprintDistributionApi(street, 30, only888 ? '888poker' : null)
      .then(res => {
        if (cancelled) return
        setTypes(res.types)
        setTotalDistinctTypes(res.total_distinct_types)
        setTotalRows(res.total_rows)
      })
      .catch(err => { if (!cancelled) setDistError(String(err)) })
      .finally(() => { if (!cancelled) setDistLoading(false) })
    return () => { cancelled = true }
  }, [street, only888])

  const toggleSelection = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Map(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        const match = types.find(t => fingerprintKeyId(t.key) === id)
        if (match) next.set(id, match.key)
      }
      return next
    })
  }, [types])

  const removeSelection = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Map(prev)
      next.delete(id)
      return next
    })
  }, [])

  const selectedIds = useMemo(() => new Set(selected.keys()), [selected])

  const loadHands = useCallback(async (offset: number) => {
    if (selected.size === 0) return
    setHandsLoading(true)
    setHandsError(null)
    try {
      const res = await getFingerprintHandsApi(
        Array.from(selected.values()), HANDS_PAGE_SIZE, offset, only888 ? '888poker' : null
      )
      setHands(res.hands)
      setHandsTotal(res.total)
      setHandsOffset(res.offset)
      setHandsLoaded(true)
    } catch (err) {
      setHandsError(String(err))
    } finally {
      setHandsLoading(false)
    }
  }, [selected, only888])

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-gray-50 p-4 gap-3">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-gray-900">Fingerprint Explorer</h1>
        <select
          value={street}
          onChange={e => { setStreet(e.target.value); setSelected(new Map()) }}
          className="border border-gray-300 rounded px-2 py-1 text-sm bg-white"
        >
          {STREETS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-gray-700 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={only888}
            onChange={e => { setOnly888(e.target.checked); setSelected(new Map()) }}
            className="accent-indigo-600"
          />
          888poker only
        </label>
        {!distLoading && !distError && (
          <span className="text-xs text-gray-400">
            top {types.length.toLocaleString()} of {totalDistinctTypes.toLocaleString()} types
            &nbsp;·&nbsp;{totalRows.toLocaleString()} rows
          </span>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-3 overflow-auto" style={{ maxHeight: '55%' }}>
        {distLoading && <div className="text-center text-gray-400 py-8 animate-pulse">Loading distribution…</div>}
        {distError && <div className="text-red-500 text-sm py-4">{distError}</div>}
        {!distLoading && !distError && types.length === 0 && (
          <div className="text-center text-gray-400 py-8">No fingerprints for this street</div>
        )}
        {!distLoading && !distError && types.length > 0 && (
          <FingerprintDistributionChart types={types} selectedIds={selectedIds} onToggle={toggleSelection} />
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {Array.from(selected.entries()).map(([id, key]) => (
          <span key={id} className="inline-flex items-center gap-1 bg-blue-50 border border-blue-200 text-blue-800 text-xs px-2 py-1 rounded-full">
            {fingerprintShortLabel(key)}
            <button onClick={() => removeSelection(id)} className="text-blue-400 hover:text-blue-700 leading-none">×</button>
          </span>
        ))}
        <button
          onClick={() => loadHands(0)}
          disabled={selected.size === 0 || handsLoading}
          className="ml-auto px-3 py-1.5 text-sm font-medium bg-indigo-600 text-white rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700"
        >
          {handsLoading ? 'Loading…' : 'Load matching hands'}
        </button>
      </div>

      <div className="flex-1 min-h-0">
        {handsError && <div className="text-red-500 text-sm py-2">{handsError}</div>}
        {!handsError && handsLoaded && (
          <HandsTable
            hands={hands}
            total={handsTotal}
            limit={HANDS_PAGE_SIZE}
            offset={handsOffset}
            onPageChange={loadHands}
          />
        )}
        {!handsError && !handsLoaded && (
          <div className="text-center text-gray-400 text-sm py-8">
            Select one or more fingerprint types above, then load matching hands.
          </div>
        )}
      </div>
    </div>
  )
}
