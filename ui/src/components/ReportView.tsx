import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import StrideChart from '@/components/StrideChart'
import { getResult, type Result, type Feedback } from '@/lib/api'
import { navigate } from '@/App'

const STATUS = {
  warn: { color: 'text-warnc', border: 'border-warnc', label: 'Fix' },
  info: { color: 'text-info', border: 'border-info', label: 'Watch' },
  good: { color: 'text-good', border: 'border-good', label: 'Good' },
} as const

function Stat({
  label,
  value,
  unit,
  accent,
}: {
  label: string
  value: string
  unit?: string
  accent?: boolean
}) {
  return (
    <div className="border-l border-line py-1 pl-4 first:border-l-0 first:pl-0">
      <div className="microlabel">{label}</div>
      <div
        className={`font-display mt-1 text-4xl font-bold leading-none tracking-tight ${
          accent ? 'text-volt' : 'text-fog'
        }`}
      >
        {value}
        {unit && (
          <span className="ml-1 font-data text-xs font-normal text-steel">
            {unit}
          </span>
        )}
      </div>
    </div>
  )
}

function FindingRow({ f }: { f: Feedback }) {
  const s = STATUS[f.status]
  return (
    <div className={`border-l-2 ${s.border} py-4 pl-5`}>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className={`font-data text-[11px] uppercase tracking-[0.18em] ${s.color}`}>
          {s.label}
        </span>
        <h3 className="font-display text-lg font-bold uppercase tracking-wide text-fog">
          {f.title}
        </h3>
        <span className="font-data text-[13px] text-steel">{f.value}</span>
      </div>
      <p className="mt-1.5 max-w-2xl text-[14px] leading-relaxed text-fog/85">
        {f.message}
      </p>
    </div>
  )
}

export default function ReportView({ jobId }: { jobId: string }) {
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getResult(jobId)
      .then(setResult)
      .catch(() => setError('Report not found — it may have been cleared.'))
  }, [jobId])

  if (error)
    return (
      <div>
        <p className="font-data text-sm text-bad">{error}</p>
        <Button
          onClick={() => navigate('/')}
          className="mt-6 h-10 rounded-none bg-volt px-8 font-display text-base font-bold uppercase tracking-wide text-ink hover:bg-volt/85"
        >
          New analysis
        </Button>
      </div>
    )
  if (!result)
    return <p className="font-data text-sm text-steel">Loading report…</p>

  const { metrics: m, feedback, chart } = result
  const counts = { warn: 0, info: 0, good: 0 }
  feedback.forEach((f) => counts[f.status]++)
  const strikeDist = Object.entries(m.foot_strike_counts)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${v}× ${k}`)
    .join(' · ')

  return (
    <div>
      {/* Header row */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="microlabel mb-2">
            Report {jobId} · {m.n_steps} steps over {m.duration_s.toFixed(1)}s
            {m.treadmill ? ' · treadmill detected' : ''}
          </p>
          <h1 className="font-display text-5xl font-bold uppercase leading-none tracking-tight">
            Stride report
          </h1>
        </div>
        <div className="flex gap-5 font-data text-[13px]">
          <span className="text-warnc">{counts.warn} fix</span>
          <span className="text-info">{counts.info} watch</span>
          <span className="text-good">{counts.good} good</span>
        </div>
      </div>

      {m.warnings.map((w) => (
        <p
          key={w}
          className="mt-5 border-l-2 border-warnc pl-4 font-data text-[13px] text-warnc"
        >
          {w}
        </p>
      ))}

      {/* Data strip */}
      <div className="mt-10 grid grid-cols-2 gap-y-8 border-y border-line py-6 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Cadence" value={m.cadence.toFixed(0)} unit="spm" accent />
        <Stat
          label="Foot strike"
          value={m.foot_strike_type}
        />
        <Stat
          label="Trunk lean"
          value={`${m.trunk_lean_deg.toFixed(1)}°`}
        />
        <Stat
          label="Shin @ contact"
          value={`${m.shin_angle_deg.toFixed(0)}°`}
        />
        <Stat
          label="Bounce"
          value={
            m.vo_cm != null ? m.vo_cm.toFixed(1) : m.vo_pct_leg.toFixed(1)
          }
          unit={m.vo_cm != null ? 'cm est.' : '% leg'}
        />
        <Stat
          label="Symmetry Δ"
          value={m.symmetry_pct != null ? `${m.symmetry_pct.toFixed(0)}%` : '—'}
        />
      </div>

      {/* Video + findings side by side on wide screens */}
      <div className="mt-12 grid gap-12 lg:grid-cols-[6fr,6fr]">
        <section>
          <p className="microlabel mb-4">Annotated footage</p>
          <video
            src={`/video/${jobId}`}
            controls
            loop
            muted
            playsInline
            className="block w-full bg-black"
          />
          <p className="mt-3 font-data text-[12px] leading-relaxed text-steel">
            green skeleton = detected pose · yellow ring = foot strike
            <br />
            strike mix: {strikeDist}
          </p>
        </section>

        <section>
          <p className="microlabel mb-4">Findings — worst first</p>
          <div className="space-y-1">
            {feedback.map((f) => (
              <FindingRow key={f.title} f={f} />
            ))}
          </div>
        </section>
      </div>

      {/* Charts */}
      <section className="mt-14">
        <p className="microlabel mb-4">Telemetry</p>
        <div className="grid gap-10 lg:grid-cols-2">
          <StrideChart
            t={chart.t}
            series={[
              { data: chart.l_ankle_y, color: '#3ddc84', label: 'left ankle' },
              { data: chart.r_ankle_y, color: '#5ba8ff', label: 'right ankle' },
            ]}
            strikes={chart.strikes}
            caption="ankle height over time"
          />
          <StrideChart
            t={chart.t}
            series={[{ data: chart.lean, color: '#ffb020', label: 'trunk lean (° fwd)' }]}
            zeroLine
            caption="posture over time"
          />
        </div>
      </section>

      <div className="mt-14 flex items-center gap-6 border-t border-line pt-8">
        <Button
          onClick={() => navigate('/')}
          className="h-10 rounded-none bg-volt px-8 font-display text-base font-bold uppercase tracking-wide text-ink hover:bg-volt/85"
        >
          Analyze another video
        </Button>
        <p className="max-w-md text-[12px] leading-relaxed text-steel">
          Single-camera estimates are directional, not lab-grade. Compare clips
          filmed the same way, change one thing at a time — and see a
          professional if something hurts.
        </p>
      </div>
    </div>
  )
}
