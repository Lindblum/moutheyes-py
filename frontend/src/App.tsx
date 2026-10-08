import { useCallback, useEffect, useState } from 'react'
import { createJob, deleteItem, getGallery, getJob, type Item, type Job } from './api'
import Dropzone from './components/Dropzone'
import Gallery from './components/Gallery'
import Viewer from './components/Viewer'

const STILL = /\.(jpe?g|png|webp|bmp)$/i
const REACTIONS = ['random', 'gasp', 'scream', 'chatter', 'double-take']
const STAGE_LABEL = {
  animating: 'Animating reaction from still',
  tracking: 'Tracking face',
  compositing: 'Swapping eyes for mouths',
  encoding: 'Encoding GIF',
}

const POLL_MS = 400

function formatEta(seconds: number) {
  if (seconds < 1) return 'almost done'
  if (seconds < 60) return `~${Math.ceil(seconds)}s left`
  return `~${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s left`
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [mouthScale, setMouthScale] = useState(1.35)
  const [reaction, setReaction] = useState('random')
  const [seed, setSeed] = useState('')
  const [job, setJob] = useState<Job | null>(null)
  const [selected, setSelected] = useState<Item | null>(null)
  const [gallery, setGallery] = useState<Item[]>([])
  const [error, setError] = useState<string | null>(null)

  const busy = job?.status === 'queued' || job?.status === 'running'
  const isStill = file !== null && STILL.test(file.name)

  const refreshGallery = useCallback(
    () => getGallery().then(setGallery, (e) => setError(message(e))),
    [],
  )

  useEffect(() => {
    refreshGallery()
  }, [refreshGallery])

  // poll the running job
  useEffect(() => {
    if (!job || !busy) return
    const timer = setTimeout(async () => {
      try {
        const next = await getJob(job.id)
        setJob(next)
        if (next.status === 'done' && next.result) {
          setSelected(next.result)
          refreshGallery()
        } else if (next.status === 'error') {
          setError(next.error)
        }
      } catch (e) {
        setJob(null)
        setError(message(e))
      }
    }, POLL_MS)
    return () => clearTimeout(timer)
  }, [job, busy, refreshGallery])

  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const pasted = e.clipboardData?.files[0]
      if (pasted && !busy) setFile(pasted)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [busy])

  async function start() {
    if (!file) return
    setError(null)
    try {
      setJob(await createJob(file, { mouthScale, reaction, seed }))
    } catch (e) {
      setError(message(e))
    }
  }

  async function remove(item: Item) {
    if (!window.confirm(`Delete ${item.name}?`)) return
    try {
      await deleteItem(item.name)
      if (selected?.name === item.name) setSelected(null)
      await refreshGallery()
    } catch (e) {
      setError(message(e))
    }
  }

  return (
    <div className="app">
      <header className="header">
        <svg className="logo" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M6 12q4-4 8 0q-4 4-8 0zM18 12q4-4 8 0q-4 4-8 0zM9 20q7 7 14 0q-7 3-14 0z" fill="currentColor" />
        </svg>
        <div>
          <h1>Moutheyes</h1>
          <p className="muted">Replace a face's eyes with its own mouth.</p>
        </div>
      </header>

      {error && (
        <div className="error" role="alert">
          <span>{error}</span>
          <button className="icon-button" onClick={() => setError(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}

      <main className="workspace">
        <section className="card controls">
          <Dropzone file={file} disabled={busy} onFile={setFile} />

          <label className="field">
            <span className="field-head">
              Mouth size <output>{mouthScale.toFixed(2)}×</output>
            </span>
            <input
              type="range"
              min={0.8}
              max={2.2}
              step={0.05}
              value={mouthScale}
              onChange={(e) => setMouthScale(Number(e.target.value))}
            />
          </label>

          {isStill && (
            <div className="field-row">
              <label className="field">
                <span className="field-head">Reaction</span>
                <select value={reaction} onChange={(e) => setReaction(e.target.value)}>
                  {REACTIONS.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="field-head">Seed</span>
                <input
                  type="number"
                  min={0}
                  placeholder="random"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                />
              </label>
            </div>
          )}
          {isStill && (
            <p className="hint">Photos get a short reaction animation first, so the mouths have something to do.</p>
          )}

          <button className="button primary big" disabled={!file || busy} onClick={start}>
            {busy ? 'Working…' : 'Make moutheyes'}
          </button>
        </section>

        <section className="card stage">
          {busy && job ? (
            <div className="progress">
              <p className="progress-label">
                {job.status === 'queued' || !job.stage ? 'Waiting in the queue' : STAGE_LABEL[job.stage]}
              </p>
              <div
                className="progress-track"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(job.progress * 100)}
              >
                <div style={{ width: `${job.progress * 100}%` }} />
              </div>
              <p className="muted">
                {job.filename}
                {job.reaction && ` · ${job.reaction}`} · {Math.round(job.progress * 100)}%
                {job.eta !== null && ` · ${formatEta(job.eta)}`}
              </p>
            </div>
          ) : selected ? (
            <Viewer item={selected} />
          ) : (
            <div className="placeholder muted">
              <p>Your GIF shows up here.</p>
            </div>
          )}
        </section>
      </main>

      <section className="gallery-section">
        <h2>
          Gallery <span className="muted">{gallery.length || ''}</span>
        </h2>
        <Gallery items={gallery} selected={selected} onSelect={setSelected} onDelete={remove} />
      </section>
    </div>
  )
}
