// Browser speech: text-to-speech for Alexa's replies and (where supported) speech-to-text
// for the microphone button. Both are optional; typing always works.

type RecognitionResultEvent = { results: ArrayLike<ArrayLike<{ transcript: string }>> }

type Recognition = {
  lang: string
  interimResults: boolean
  maxAlternatives: number
  onresult: ((event: RecognitionResultEvent) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
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

/** Listen once and resolve with what was heard. */
export function listenOnce(): { result: Promise<string>; stop: () => void } {
  const Recognition = recognitionClass()
  if (!Recognition) {
    return { result: Promise.reject(new Error('Speech recognition is not available in this browser.')), stop: () => {} }
  }
  const recognition = new Recognition()
  recognition.lang = 'en-IN'
  recognition.interimResults = false
  recognition.maxAlternatives = 1
  const result = new Promise<string>((resolve, reject) => {
    let heard = ''
    recognition.onresult = (event) => {
      heard = event.results[0]?.[0]?.transcript ?? ''
    }
    recognition.onerror = (event) => reject(new Error(event.error === 'not-allowed'
      ? 'Microphone access was blocked. Allow it in the browser, or type instead.'
      : `I couldn't hear that (${event.error}).`))
    recognition.onend = () => (heard ? resolve(heard) : reject(new Error("I didn't hear anything. Try again.")))
  })
  recognition.start()
  return { result, stop: () => recognition.stop() }
}

/** Speak a reply, preferring an Indian English voice. Rupee signs are read as "rupees". */
export function speak(text: string): void {
  if (!canSpeak) return
  window.speechSynthesis.cancel()
  const spoken = text.replace(/₹\s?([\d,]+(?:\.\d+)?)/g, '$1 rupees')
  const utterance = new SpeechSynthesisUtterance(spoken)
  const voices = window.speechSynthesis.getVoices()
  utterance.voice =
    voices.find((v) => v.lang === 'en-IN') ?? voices.find((v) => v.lang.startsWith('en')) ?? null
  utterance.rate = 1.02
  window.speechSynthesis.speak(utterance)
}

export function stopSpeaking(): void {
  if (canSpeak) window.speechSynthesis.cancel()
}
