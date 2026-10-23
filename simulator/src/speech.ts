// Browser speech for the simulated Echo: text-to-speech for Alexa's replies and speech-to-text for
// commands, with Alexa-style timing. Everything is optional; typing always works.
//
// Timing:
// - After the mic button, Alexa waits about 8 seconds for you to start talking.
// - In Follow-Up Mode, after Alexa replies, it listens again for about 5 seconds.
// - Once you're talking, a pause of up to 3 seconds doesn't end your turn, so you can hesitate
//   mid-sentence ("I paid… um… 2,400 for groceries"). A longer silence sends what you said.

export const COMMAND_TIMEOUT_MS = 8000
export const FOLLOW_UP_TIMEOUT_MS = 5000
export const PAUSE_TOLERANCE_MS = 3000
const MAX_LISTEN_MS = 30000

type RecognitionResultEvent = {
  results: ArrayLike<ArrayLike<{ transcript: string }>>
}

type Recognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  onresult: ((event: RecognitionResultEvent) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  onaudiostart: (() => void) | null
  onsoundstart: (() => void) | null
  onspeechstart: (() => void) | null
  start: () => void
  stop: () => void
}

type RecognitionConstructor = new () => Recognition

function recognitionClass(): RecognitionConstructor | undefined {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionConstructor
    webkitSpeechRecognition?: RecognitionConstructor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

export const canListen = typeof window !== 'undefined' && recognitionClass() !== undefined
export const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window

/** Nobody started talking before the timeout. Not an error worth showing. */
export class NoSpeechError extends Error {
  constructor() {
    super("I didn't hear anything.")
  }
}

const BLOCKED = 'Microphone access was blocked. Allow it in the browser, or type instead.'

/**
 * Listen for one command.
 *
 * Rejects with NoSpeechError if nobody starts talking within `startTimeoutMs`. Once speech
 * starts, the turn ends after PAUSE_TOLERANCE_MS of silence (we decide this, rather than the
 * browser's ~1 s default, so short hesitations don't cut you off). `onPartial` receives the words
 * recognised so far, for showing on screen.
 */
export function listenOnce(
  startTimeoutMs = COMMAND_TIMEOUT_MS,
  onPartial?: (text: string) => void,
): { result: Promise<string>; stop: () => void } {
  const Recognition = recognitionClass()
  if (!Recognition) {
    return { result: Promise.reject(new Error('Speech recognition is not available in this browser.')), stop: () => {} }
  }
  const recognition = new Recognition()
  recognition.lang = 'en-IN'
  recognition.continuous = true // keep listening through pauses; we decide when the turn ends
  recognition.interimResults = true
  recognition.maxAlternatives = 1

  let silenceTimer: ReturnType<typeof setTimeout> | undefined
  // The "start talking" window begins once the mic is actually open (audiostart); the extra
  // second here only covers browsers that never report audiostart.
  let startTimer = setTimeout(() => recognition.stop(), startTimeoutMs + 1000)
  const capTimer = setTimeout(() => recognition.stop(), MAX_LISTEN_MS)
  let speechStarted = false
  const clearTimers = () => {
    clearTimeout(startTimer)
    clearTimeout(capTimer)
    clearTimeout(silenceTimer)
  }
  const userStartedTalking = () => {
    speechStarted = true
    clearTimeout(startTimer)
  }

  const result = new Promise<string>((resolve, reject) => {
    let heard = ''
    let failure: Error | null = null
    recognition.onaudiostart = () => {
      debug('mic open')
      if (speechStarted) return
      clearTimeout(startTimer)
      startTimer = setTimeout(() => recognition.stop(), startTimeoutMs)
    }
    recognition.onsoundstart = () => debug('sound')
    recognition.onspeechstart = () => {
      debug('speech started')
      userStartedTalking()
    }
    recognition.onresult = (event) => {
      heard = Array.from(event.results, (r) => r[0]?.transcript ?? '').join(' ').replace(/\s+/g, ' ').trim()
      if (!heard) return
      userStartedTalking()
      clearTimeout(silenceTimer)
      silenceTimer = setTimeout(() => recognition.stop(), PAUSE_TOLERANCE_MS)
      onPartial?.(heard)
    }
    recognition.onerror = (event) => {
      debug(`error: ${event.error}`)
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') failure = new Error(BLOCKED)
      else if (event.error !== 'no-speech' && event.error !== 'aborted') failure = new Error(`I couldn't hear that (${event.error}).`)
    }
    recognition.onend = () => {
      debug(`ended, heard: "${heard}"`)
      clearTimers()
      if (heard) resolve(heard)
      else reject(failure ?? new NoSpeechError())
    }
  })
  try {
    recognition.start()
  } catch (err) {
    clearTimers()
    return { result: Promise.reject(err instanceof Error ? err : new Error(String(err))), stop: () => {} }
  }
  return {
    result,
    stop: () => {
      clearTimers()
      recognition.stop()
    },
  }
}

// Chrome can garbage-collect an utterance mid-speech and then never fire its `end` event, so keep
// a reference to the one being spoken.
let currentUtterance: SpeechSynthesisUtterance | null = null

/** Speak a reply, preferring an Indian English voice. Calls onDone when finished (or skipped). */
export function speak(text: string, onDone?: () => void): void {
  if (!canSpeak) {
    onDone?.()
    return
  }
  window.speechSynthesis.cancel()
  const spoken = text.replace(/₹\s?([\d,]+(?:\.\d+)?)/g, '$1 rupees')
  const utterance = new SpeechSynthesisUtterance(spoken)
  currentUtterance = utterance
  const voices = window.speechSynthesis.getVoices()
  utterance.voice =
    voices.find((v) => v.lang === 'en-IN') ?? voices.find((v) => v.lang.startsWith('en')) ?? null
  utterance.rate = 1.02
  let finished = false
  const synth = window.speechSynthesis
  const isSpeaking = () => synth.speaking || synth.pending
  // Don't guess how long speech takes (numbers like "₹18,940.33" take far longer than their
  // length suggests). Instead, finish only when the browser says nothing is being spoken. This
  // also covers browsers that never fire `end`.
  let quietChecks = 0
  const watchdog = setInterval(() => {
    quietChecks = isSpeaking() ? 0 : quietChecks + 1
    if (quietChecks >= 2) done() // quiet for two checks in a row (~0.5 s)
  }, 250)
  const cap = setTimeout(() => done(), 60000)
  const done = () => {
    if (finished) return
    finished = true
    clearInterval(watchdog)
    clearTimeout(cap)
    if (currentUtterance === utterance) currentUtterance = null
    debug('finished speaking')
    onDone?.()
  }
  // `end` can arrive a moment before the audio actually stops; confirm it's quiet first.
  utterance.onend = () => {
    if (!isSpeaking()) done()
  }
  utterance.onerror = done
  synth.speak(utterance)
}

export function stopSpeaking(): void {
  if (canSpeak) window.speechSynthesis.cancel()
}

/** Voice timing log, visible in the browser console (F12) to diagnose microphone issues. */
function debug(message: string): void {
  console.debug(`[voice] ${message}`)
}

/** A short two-note chime, like an Echo's "listening" sound. */
export function chime(): void {
  try {
    const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) return
    const ctx = new AudioCtx()
    ;[660, 880].forEach((frequency, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      const start = ctx.currentTime + i * 0.09
      osc.frequency.value = frequency
      osc.type = 'sine'
      gain.gain.setValueAtTime(0.0001, start)
      gain.gain.exponentialRampToValueAtTime(0.18, start + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16)
      osc.connect(gain).connect(ctx.destination)
      osc.start(start)
      osc.stop(start + 0.18)
    })
    setTimeout(() => void ctx.close(), 500)
  } catch {
    // audio is a nicety; ignore failures
  }
}
