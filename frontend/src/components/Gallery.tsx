import { useEffect, useState } from 'react'
import type { Item } from '../api'
import GifPlayer from './GifPlayer'
import { formatSize } from './Viewer'

interface Props {
  items: Item[]
  selected: Item | null
  onSelect: (item: Item) => void
  onDelete: (item: Item) => void
}

export default function Gallery({ items, selected, onSelect, onDelete }: Props) {
  // names of the items currently showing their original eyes
  const [eyed, setEyed] = useState<ReadonlySet<string>>(new Set())

  // the card the arrow keys act on: the last one hovered or focused
  const [current, setCurrent] = useState<string | null>(null)

  // ← shows eyes, → shows mouths (matching the toggle's button order) on the current card;
  // with Shift, on every card at once
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      if (e.altKey || e.ctrlKey || e.metaKey) return
      // leave the arrows alone where they already mean something (slider, select, number field)
      if (e.target instanceof Element && e.target.closest('input, select, textarea')) return
      e.preventDefault()
      const show = e.key === 'ArrowLeft'
      if (e.shiftKey) {
        setEyed(new Set(show ? items.filter((i) => i.eyes_url).map((i) => i.name) : []))
      } else if (items.some((i) => i.name === current && i.eyes_url)) {
        setShowEyes(current!, show)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [items, current])

  function setShowEyes(name: string, show: boolean) {
    setEyed((prev) => {
      const next = new Set(prev)
      if (show) next.add(name)
      else next.delete(name)
      return next
    })
  }

  if (items.length === 0) {
    return <p className="muted gallery-empty">Nothing here yet. Finished GIFs will collect below.</p>
  }
  return (
    <ul className="gallery">
      {items.map((item) => (
        <GalleryCard
          key={item.name}
          item={item}
          active={item.name === selected?.name}
          current={item.name === current}
          onCurrent={() => setCurrent(item.name)}
          showEyes={eyed.has(item.name)}
          setShowEyes={(show) => setShowEyes(item.name, show)}
          onSelect={onSelect}
          onDelete={onDelete}
        />
      ))}
    </ul>
  )
}

interface CardProps {
  item: Item
  active: boolean
  current: boolean
  onCurrent: () => void
  showEyes: boolean
  setShowEyes: (show: boolean) => void
  onSelect: (item: Item) => void
  onDelete: (item: Item) => void
}

function GalleryCard({ item, active, current, onCurrent, showEyes, setShowEyes, onSelect, onDelete }: CardProps) {
  const hasEyes = item.eyes_url !== null

  return (
    <li
      className={`${active ? 'active' : ''}${current ? ' current' : ''}`}
      onPointerEnter={onCurrent}
      onFocus={onCurrent}
    >
      <button className="gallery-thumb" onClick={() => onSelect(item)} title={item.name}>
        <GifPlayer mouthUrl={item.url} eyesUrl={item.eyes_url} showEyes={showEyes} alt={item.name} />
      </button>
      <div className="gallery-meta">
        <div
          className="version-toggle"
          role="group"
          aria-label="Version"
          title={hasEyes ? undefined : 'The original is no longer in inputs/'}
        >
          <button
            aria-pressed={showEyes}
            aria-label="Show original eyes"
            title={hasEyes ? 'Original eyes (←, Shift+← for all)' : undefined}
            disabled={!hasEyes}
            onClick={() => setShowEyes(true)}
          >
            👁️
          </button>
          <button
            aria-pressed={!showEyes}
            aria-label="Show moutheyes"
            title={hasEyes ? 'Moutheyes (→, Shift+→ for all)' : undefined}
            disabled={!hasEyes}
            onClick={() => setShowEyes(false)}
          >
            👄
          </button>
        </div>
        <span className="muted gallery-info">
          {formatSize(item.size)}
        </span>
        <a
          className="icon-button"
          href={item.url}
          download={item.name}
          aria-label={`Download ${item.name}`}
          title="Download GIF"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path
              d="M12 5v11m0 0-4.5-4.5M12 16l4.5-4.5M5 19h14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </a>
        <button
          className="icon-button"
          onClick={() => onDelete(item)}
          aria-label={`Delete ${item.name}`}
          title="Delete"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path
              d="M5 7h14M10 7V5h4v2m-7 0 1 12h8l1-12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </li>
  )
}
