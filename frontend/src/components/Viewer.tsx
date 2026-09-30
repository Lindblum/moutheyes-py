import type { Item } from '../api'

const VIDEO = /\.(mp4|webm|mov)(\?|$)/i

export default function Viewer({ item }: { item: Item }) {
  return (
    <div className="viewer">
      <div className={`viewer-panes${item.source_url ? '' : ' single'}`}>
        {item.source_url && (
          <figure>
            {VIDEO.test(item.source_url) ? (
              <video src={item.source_url} autoPlay loop muted playsInline />
            ) : (
              <img src={item.source_url} alt="Original" />
            )}
            <figcaption>Original</figcaption>
          </figure>
        )}
        <figure>
          <img src={item.url} alt="Moutheyes result" />
          <figcaption className="accent">Moutheyes</figcaption>
        </figure>
      </div>
      <div className="viewer-bar">
        <span className="viewer-name" title={item.name}>
          {item.name}
        </span>
        <span className="muted">{formatSize(item.size)}</span>
        <a className="button primary" href={item.url} download={item.name}>
          Download GIF
        </a>
      </div>
    </div>
  )
}

export function formatSize(bytes: number) {
  return bytes >= 1 << 20 ? `${(bytes / (1 << 20)).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`
}
