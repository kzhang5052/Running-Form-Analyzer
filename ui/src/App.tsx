import { useEffect, useState } from 'react'
import UploadView from '@/components/UploadView'
import ProcessingView from '@/components/ProcessingView'
import ReportView from '@/components/ReportView'

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return hash
}

export function navigate(to: string) {
  window.location.hash = to
}

export default function App() {
  const hash = useHashRoute()
  const jobMatch = hash.match(/^#\/job\/([a-z0-9]+)/)
  const resultMatch = hash.match(/^#\/result\/([a-z0-9]+)/)

  return (
    <div className="min-h-screen bg-ink">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl items-baseline gap-4 px-6 py-4">
          <a
            href="#/"
            className="font-display text-xl font-bold uppercase tracking-wide text-fog no-underline"
          >
            Form<span className="text-volt">/</span>Check
          </a>
          <span className="microlabel hidden sm:inline">
            running gait analysis · on-device
          </span>
          <span className="ml-auto font-data text-[11px] text-steel">
            127.0.0.1:5177
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 pb-24 pt-10">
        {jobMatch ? (
          <ProcessingView jobId={jobMatch[1]} />
        ) : resultMatch ? (
          <ReportView jobId={resultMatch[1]} />
        ) : (
          <UploadView />
        )}
      </main>
    </div>
  )
}
