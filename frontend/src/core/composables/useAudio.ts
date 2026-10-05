/**
 * Audio notification composable.
 *
 * Preloads sound files and provides a `play()` method.
 * Handles browser autoplay restrictions by unlocking on first user gesture.
 *
 * Usage:
 * ```ts
 * const audio = useAudio()
 * audio.play('chime')
 * ```
 */

const audioCache = new Map<string, HTMLAudioElement>()
let unlocked = false

function ensureUnlocked() {
  if (unlocked) return
  const handler = () => {
    unlocked = true
    document.removeEventListener('click', handler)
    document.removeEventListener('touchstart', handler)
    document.removeEventListener('keydown', handler)
  }
  document.addEventListener('click', handler, { once: false })
  document.addEventListener('touchstart', handler, { once: false })
  document.addEventListener('keydown', handler, { once: false })
}

// Initialize unlock listener on module load
ensureUnlocked()

function getAudio(name: string): HTMLAudioElement {
  if (audioCache.has(name)) {
    return audioCache.get(name)!
  }
  // Try .mp3 first, fall back to .wav
  const ext = name.includes('.') ? '' : '.mp3'
  const audio = new Audio(`/assets/sounds/${name}${ext}`)
  audio.addEventListener('error', () => {
    if (!name.includes('.') && ext === '.mp3') {
      audio.src = `/assets/sounds/${name}.wav`
    }
  }, { once: true })
  audio.preload = 'auto'
  audioCache.set(name, audio)
  return audio
}

export function useAudio() {
  function play(name: string = 'chime') {
    const audio = getAudio(name)
    audio.currentTime = 0
    audio.play().catch(() => {
      // Browser blocked autoplay - will work after user gesture
    })
  }

  function preload(...names: string[]) {
    for (const name of names) {
      getAudio(name)
    }
  }

  return { play, preload }
}
