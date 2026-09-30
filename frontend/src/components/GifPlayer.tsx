import { useEffect, useRef, useState } from 'react'

interface Props {
  mouthUrl: string
  eyesUrl: string | null
  showEyes: boolean
  alt: string
}

interface Gif {
  decoder: ImageDecoder
  count: number
}

const canDecode = typeof ImageDecoder !== 'undefined'

/**
 * Plays the moutheyes GIF on a canvas, one frame at a time, so that switching to the
 * eyes version (and back) carries on from the same frame number instead of restarting.
 * The mouth GIF's frame timing is the clock for both versions.
 */
export default function GifPlayer({ mouthUrl, eyesUrl, showEyes, alt }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const showEyesRef = useRef(showEyes)
  const wakeRef = useRef(() => {})
  const [failed, setFailed] = useState(!canDecode)

  useEffect(() => {
    showEyesRef.current = showEyes
    wakeRef.current() // repaint the current frame from the other version right away
  }, [showEyes])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !canDecode) return
    const ctx = canvas.getContext('2d')!
    const opened: ImageDecoder[] = []
    let cancelled = false
    let visible = true

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      wakeRef.current()
    })
    observer.observe(canvas)

    async function open(url: string): Promise<Gif> {
      const data = await (await fetch(url)).arrayBuffer()
      const decoder = new ImageDecoder({ data, type: 'image/gif' })
      if (cancelled) {
        decoder.close()
        throw new Error('cancelled')
      }
      opened.push(decoder)
      await Promise.all([decoder.tracks.ready, decoder.completed])
      return { decoder, count: decoder.tracks.selectedTrack!.frameCount }
    }

    // resolves after `ms`, or earlier if something calls wakeRef.current()
    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        const timer = ms === Infinity ? 0 : setTimeout(resolve, ms)
        wakeRef.current = () => {
          clearTimeout(timer)
          resolve()
        }
      })

    async function play() {
      const mouth = await open(mouthUrl)
      let eyes: Gif | null = null
      const mouthMs: number[] = [] // per-frame durations of the mouth GIF, learned as they are decoded
      let sized = false
      let frame = 0
      let next = 0
      let redraw = false // repaint `frame` without restarting its timer

      while (!cancelled) {
        if (!visible) {
          await sleep(Infinity)
          continue
        }
        const started = performance.now()
        const eyesMode = showEyesRef.current && eyesUrl !== null
        let gif = mouth
        let index = frame
        if (eyesMode && eyesUrl) {
          eyes ??= await open(eyesUrl)
          gif = eyes
          // same frame number; scaled only if the two files somehow differ in length
          index = Math.min(eyes.count - 1, Math.floor((frame * eyes.count) / mouth.count))
        }
        const { image } = await gif.decoder.decode({ frameIndex: index })
        if (cancelled) return image.close()
        if (!sized) {
          canvas!.width = image.displayWidth
          canvas!.height = image.displayHeight
          sized = true
        }
        ctx.drawImage(image, 0, 0, canvas!.width, canvas!.height)
        const ownMs = (image.duration ?? 0) / 1000 || 100
        image.close()
        if (!eyesMode) mouthMs[frame] = ownMs

        if (!redraw) next = started + (mouthMs[frame] ?? mouthMs[0] ?? ownMs)
        await sleep(Math.max(0, next - performance.now()))
        // woken early (toggle or scroll): show the same frame again, from whichever version is now wanted
        redraw = performance.now() < next - 2
        if (!redraw) frame = (frame + 1) % mouth.count
      }
    }

    play().catch((e) => {
      if (cancelled) return
      console.warn('GIF frame playback failed, falling back to <img>', e)
      setFailed(true)
    })

    return () => {
      cancelled = true
      observer.disconnect()
      wakeRef.current()
      for (const decoder of opened) decoder.close()
    }
  }, [mouthUrl, eyesUrl])

  // no ImageDecoder (or it choked): plain GIFs, which restart when swapped
  if (failed) return <img src={showEyes && eyesUrl ? eyesUrl : mouthUrl} alt={alt} loading="lazy" />
  return <canvas ref={canvasRef} role="img" aria-label={alt} />
}
