import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { uploadVideo } from '@/lib/api'
import { navigate } from '@/App'

const ACCEPTED = ['.mp4', '.mov', '.m4v', '.avi', '.webm', '.mkv']

const METRICS = [
  ['Cadence', 'steps per minute'],
  ['Overstride', 'shin angle at contact'],
  ['Foot strike', 'Altman–Davis angle'],
  ['Trunk lean', 'degrees off vertical'],
  ['Knee at landing', 'stiff-leg check'],
  ['Pelvic drop', 'front/rear · Bramah'],
  ['Crossover', 'front/rear · stride width'],
  ['Bounce', 'vertical oscillation'],
  ['Symmetry', 'left vs right timing'],
  ['Arm carry', 'elbow angle'],
]

export default function UploadView() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [height, setHeight] = useState('')
  const [drag, setDrag] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadPct, setUploadPct] = useState(0)

  function pick(f: File | undefined) {
    if (!f) return
    const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
    if (!ACCEPTED.includes(ext)) {
      setError(`Unsupported file type ${ext} — use ${ACCEPTED.join(', ')}`)
      return
    }
    setError(null)
    setFile(f)
  }

  async function submit() {
    if (!file || uploading) return
    setUploading(true)
    setError(null)
    try {
      const { job_id } = await uploadVideo(file, height, setUploadPct)
      navigate(`/job/${job_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
      setUploading(false)
    }
  }

  return (
    <div className="grid gap-12 md:grid-cols-[7fr,5fr]">
      <section>
        <p className="microlabel mb-3">New analysis</p>
        <h1 className="font-display text-5xl font-bold uppercase leading-none tracking-tight">
          Film the side.
          <br />
          <span className="text-volt">See the stride.</span>
        </h1>
        <p className="mt-5 max-w-md text-[15px] leading-relaxed text-steel">
          Upload 5–15 seconds of continuous running, whole body in frame,
          camera steady. A <strong className="text-fog">side view</strong>{' '}
          reads stride, foot strike and posture; a{' '}
          <strong className="text-fog">front or rear view</strong> reads pelvic
          drop and crossover. The angle is detected automatically. Everything
          runs on this Mac; the video never leaves it.
        </p>

        <div
          className={`mt-8 cursor-pointer border px-6 py-10 transition-colors ${
            drag
              ? 'border-volt bg-well'
              : file
                ? 'border-line bg-panel'
                : 'border-dashed border-line bg-panel hover:border-steel'
          }`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDrag(true)
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDrag(false)
            pick(e.dataTransfer.files[0])
          }}
        >
          {file ? (
            <div className="flex items-baseline gap-3">
              <span className="font-data text-sm text-volt">▸</span>
              <div>
                <div className="font-data text-sm text-fog">{file.name}</div>
                <div className="microlabel mt-1">
                  {(file.size / 1024 / 1024).toFixed(1)} MB · click to change
                </div>
              </div>
            </div>
          ) : (
            <div>
              <div className="text-[15px] text-fog">
                Drop a video here or{' '}
                <span className="text-volt underline underline-offset-4">
                  browse
                </span>
              </div>
              <div className="microlabel mt-2">
                mp4 · mov · m4v · avi · webm · mkv — up to 500 MB
              </div>
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="video/*"
            hidden
            onChange={(e) => pick(e.target.files?.[0])}
          />
        </div>

        <div className="mt-6 flex flex-wrap items-end gap-4">
          <label className="block">
            <span className="microlabel">Height (cm, optional)</span>
            <Input
              type="number"
              min={100}
              max={230}
              placeholder="183"
              value={height}
              onChange={(e) => setHeight(e.target.value)}
              className="mt-2 w-28 border-line bg-well font-data"
            />
          </label>
          <Button
            onClick={submit}
            disabled={!file || uploading}
            className="h-10 rounded-none bg-volt px-8 font-display text-base font-bold uppercase tracking-wide text-ink hover:bg-volt/85"
          >
            {uploading
              ? uploadPct < 1
                ? `Uploading ${Math.round(uploadPct * 100)}%`
                : 'Starting…'
              : 'Analyze'}
          </Button>
        </div>
        <p className="microlabel mt-2">
          height unlocks the bounce estimate in cm
        </p>

        {error && (
          <p className="mt-4 border-l-2 border-bad pl-3 font-data text-sm text-bad">
            {error}
          </p>
        )}
      </section>

      <aside className="border-l border-line pl-8 pt-1 md:mt-16">
        <p className="microlabel mb-4">What gets measured</p>
        <ul>
          {METRICS.map(([name, sub]) => (
            <li
              key={name}
              className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 last:border-b-0"
            >
              <span className="text-sm text-fog">{name}</span>
              <span className="font-data text-[11px] text-steel">{sub}</span>
            </li>
          ))}
        </ul>
        <p className="mt-6 text-[13px] leading-relaxed text-steel">
          You get an annotated video with your skeleton and every foot strike
          marked, plus prioritized coaching notes for each metric.
        </p>
      </aside>
    </div>
  )
}
