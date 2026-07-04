export type Source = { cite: string; note: string; url: string }

export type Feedback = {
  status: 'good' | 'info' | 'warn'
  title: string
  value: string
  message: string
  source: Source | null
}

export type ChartData = {
  t: number[]
  l_ankle_y: number[]
  r_ankle_y: number[]
  lean: number[]
  pelvis_obliq: number[]
  strikes: { t: number; side: 'L' | 'R' }[]
}

export type Metrics = {
  n_frames: number
  fps: number
  duration_s: number
  treadmill: boolean
  view: 'sagittal' | 'frontal'
  n_steps: number
  cadence: number
  symmetry_pct: number | null
  trunk_lean_deg: number
  shin_angle_deg: number
  foot_reach_legs: number
  knee_angle_at_strike: number
  foot_strike_type: string
  foot_strike_counts: Record<string, number>
  foot_strike_angle_deg: number
  pelvic_drop_deg: number
  stride_width_ratio: number
  vo_pct_leg: number
  vo_cm: number | null
  elbow_angle: number | null
  warnings: string[]
}

export type Result = {
  metrics: Metrics
  feedback: Feedback[]
  chart: ChartData
  references: Source[]
}

export type JobStatus = {
  status: 'processing' | 'done' | 'error' | 'unknown'
  progress?: number
  error?: string | null
}

export function uploadVideo(
  file: File,
  height: string,
  onProgress: (frac: number) => void,
): Promise<{ job_id: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/upload')
    const fd = new FormData()
    fd.append('video', file)
    if (height.trim()) fd.append('height', height.trim())
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total)
    }
    xhr.onload = () => {
      try {
        const j = JSON.parse(xhr.responseText)
        if (xhr.status < 400 && j.job_id) resolve(j)
        else reject(new Error(j.error || `Upload failed (${xhr.status})`))
      } catch {
        reject(new Error(`Upload failed (${xhr.status})`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(fd)
  })
}

export async function getJob(id: string): Promise<JobStatus> {
  const r = await fetch(`/api/job/${id}`)
  return r.json()
}

export async function getResult(id: string): Promise<Result> {
  const r = await fetch(`/api/result/${id}`)
  if (!r.ok) throw new Error('Result not found')
  return r.json()
}
