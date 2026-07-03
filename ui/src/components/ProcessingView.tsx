import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { getJob } from '@/lib/api'
import { navigate } from '@/App'

const STAGES: [number, string][] = [
  [0, 'Reading frames'],
  [0.05, 'Detecting pose, frame by frame'],
  [0.75, 'Measuring stride mechanics'],
  [0.78, 'Rendering annotated video'],
]

export default function ProcessingView({ jobId }: { jobId: string }) {
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const stopped = useRef(false)

  useEffect(() => {
    stopped.current = false
    async function poll() {
      if (stopped.current) return
      try {
        const j = await getJob(jobId)
        if (j.status === 'done') {
          navigate(`/result/${jobId}`)
          return
        }
        if (j.status === 'error') {
          setError(j.error || 'Unknown error')
          return
        }
        if (j.status === 'unknown') {
          setError('This job no longer exists — the server may have restarted.')
          return
        }
        setProgress(j.progress ?? 0)
      } catch {
        /* transient — keep polling */
      }
      setTimeout(poll, 600)
    }
    poll()
    return () => {
      stopped.current = true
    }
  }, [jobId])

  const stage =
    STAGES.filter(([at]) => progress >= at).slice(-1)[0]?.[1] ?? STAGES[0][1]
  const pct = Math.round(progress * 100)

  if (error) {
    return (
      <div className="max-w-xl">
        <p className="microlabel mb-3 text-bad">Analysis failed</p>
        <h1 className="font-display text-4xl font-bold uppercase tracking-tight">
          Couldn't read that run
        </h1>
        <p className="mt-4 border-l-2 border-bad pl-4 text-[15px] leading-relaxed text-fog">
          {error}
        </p>
        <p className="mt-4 text-sm leading-relaxed text-steel">
          Best results: 5–15 s side view, whole body in frame, good light,
          steady camera.
        </p>
        <Button
          onClick={() => navigate('/')}
          className="mt-8 h-10 rounded-none bg-volt px-8 font-display text-base font-bold uppercase tracking-wide text-ink hover:bg-volt/85"
        >
          Try another video
        </Button>
      </div>
    )
  }

  return (
    <div className="max-w-xl pt-10">
      <p className="microlabel mb-3">
        Job <span className="text-fog">{jobId}</span>
      </p>
      <h1 className="font-display text-4xl font-bold uppercase tracking-tight">
        Analyzing your run
      </h1>
      <div className="mt-10 flex items-baseline justify-between">
        <span className="font-data text-sm text-steel">{stage}</span>
        <span className="font-data text-3xl text-volt">{pct}%</span>
      </div>
      <div className="mt-3 h-1 w-full bg-well">
        <div
          className="h-full bg-volt transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <ol className="mt-8 space-y-2">
        {STAGES.map(([at, label]) => (
          <li key={label} className="flex items-center gap-3 font-data text-[13px]">
            <span className={progress >= at ? 'text-volt' : 'text-line'}>
              {progress >= at ? '■' : '□'}
            </span>
            <span className={progress >= at ? 'text-fog' : 'text-steel'}>
              {label}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
