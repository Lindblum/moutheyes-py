import { useEffect, useState, type DragEvent } from 'react'

export const ACCEPT = '.jpg,.jpeg,.png,.webp,.bmp,.gif,.mp4,.webm,.mov'
const VIDEO = /\.(mp4|webm|mov)$/i

interface Props {
  file: File | null
  disabled: boolean
  onFile: (file: File) => void
}

export default function Dropzone({ file, disabled, onFile }: Props) {
  const [over, setOver] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)

  useEffect(() => {
    if (!file) return setPreview(null)
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped && !disabled) onFile(dropped)
  }

  return (
    <label
      className={`dropzone${over ? ' over' : ''}${file ? ' filled' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <input
        type="file"
        accept={ACCEPT}
        disabled={disabled}
        onChange={(e) => {
          const picked = e.target.files?.[0]
          if (picked) onFile(picked)
          e.target.value = ''
        }}
      />
      {file && preview ? (
        <>
          {VIDEO.test(file.name) ? (
            <video src={preview} autoPlay loop muted playsInline />
          ) : (
            <img src={preview} alt="" />
          )}
          <span className="dropzone-name">{file.name}</span>
        </>
      ) : (
        <div className="dropzone-empty">
          <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
            <path
              d="M12 16V5m0 0L7.5 9.5M12 5l4.5 4.5M5 19h14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <strong>Drop a face here</strong>
          <span>or click to browse, or paste an image</span>
          <span className="dropzone-types">JPG · PNG · WebP · GIF · MP4 · WebM · MOV</span>
        </div>
      )}
    </label>
  )
}
