export interface Item {
  name: string
  url: string
  source_url: string | null
  /** GIF with the same frames as `url` but the original eyes; null if the source is gone */
  eyes_url: string | null
  size: number
  created: number
}

export interface Job {
  id: string
  filename: string
  status: 'queued' | 'running' | 'done' | 'error'
  stage: 'animating' | 'tracking' | 'compositing' | 'encoding' | null
  progress: number
  reaction: string | null
  error: string | null
  result: Item | null
}

export interface JobOptions {
  mouthScale: number
  reaction: string
  seed: string
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch {
    throw new Error('Could not reach the backend. Is it running?')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    throw new Error(
      typeof detail === 'string' ? detail : detail?.[0]?.msg ?? `Request failed (${res.status})`,
    )
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export function createJob(file: File, opts: JobOptions) {
  const form = new FormData()
  form.append('file', file)
  form.append('mouth_scale', String(opts.mouthScale))
  form.append('reaction', opts.reaction)
  if (opts.seed.trim()) form.append('seed', opts.seed.trim())
  return request<Job>('/api/jobs', { method: 'POST', body: form })
}

export const getJob = (id: string) => request<Job>(`/api/jobs/${id}`)
export const getGallery = () => request<Item[]>('/api/gallery')
export const deleteItem = (name: string) =>
  request<void>(`/api/gallery/${encodeURIComponent(name)}`, { method: 'DELETE' })
