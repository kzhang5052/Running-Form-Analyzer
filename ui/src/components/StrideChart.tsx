type Series = { data: number[]; color: string; label: string }

type Props = {
  t: number[]
  series: Series[]
  strikes?: { t: number; side: 'L' | 'R' }[]
  height?: number
  caption: string
  zeroLine?: boolean
}

const W = 800

export default function StrideChart({
  t,
  series,
  strikes,
  height = 150,
  caption,
  zeroLine,
}: Props) {
  const H = height
  const pad = 6
  let lo = Infinity
  let hi = -Infinity
  for (const s of series)
    for (const v of s.data) {
      if (v < lo) lo = v
      if (v > hi) hi = v
    }
  if (zeroLine) {
    lo = Math.min(lo, 0)
    hi = Math.max(hi, 0)
  }
  if (hi - lo < 1e-6) hi = lo + 1
  const t0 = t[0]
  const t1 = t[t.length - 1] || 1
  const x = (tt: number) => pad + ((tt - t0) / (t1 - t0)) * (W - 2 * pad)
  const y = (v: number) => H - pad - ((v - lo) / (hi - lo)) * (H - 2 * pad)
  const path = (data: number[]) =>
    data
      .map((v, i) => `${i ? 'L' : 'M'}${x(t[i]).toFixed(1)},${y(v).toFixed(1)}`)
      .join('')
  const nearestIdx = (tt: number) => {
    let best = 0
    let bd = Infinity
    for (let i = 0; i < t.length; i++) {
      const d = Math.abs(t[i] - tt)
      if (d < bd) {
        bd = d
        best = i
      }
    }
    return best
  }

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full bg-well"
        preserveAspectRatio="none"
        role="img"
        aria-label={caption}
      >
        {zeroLine && (
          <line
            x1={0}
            x2={W}
            y1={y(0)}
            y2={y(0)}
            stroke="#2c333b"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
          />
        )}
        {series.map((s) => (
          <path
            key={s.label}
            d={path(s.data)}
            fill="none"
            stroke={s.color}
            strokeWidth={1.6}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {strikes?.map((s, i) => {
          const idx = nearestIdx(s.t)
          const serie = series[s.side === 'L' ? 0 : 1] ?? series[0]
          return (
            <circle
              key={i}
              cx={x(t[idx])}
              cy={y(serie.data[idx])}
              r={3.2}
              fill="#c8f135"
            />
          )
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        {series.map((s) => (
          <span key={s.label} className="font-data text-[11px]" style={{ color: s.color }}>
            — {s.label}
          </span>
        ))}
        {strikes && (
          <span className="font-data text-[11px] text-volt">● foot strike</span>
        )}
        <span className="microlabel">{caption}</span>
      </figcaption>
    </figure>
  )
}
