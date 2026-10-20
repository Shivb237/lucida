// Small page helpers shared by several components (kept out of component files so fast refresh keeps working).

/** Scroll an element into view; instant for people who asked for less motion. */
export function scrollToId(id: string, block: ScrollLogicalPosition = 'start') {
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document.getElementById(id)?.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block })
}

export const MODEL_DIALOG_EVENT = 'lucida-open-model'
/** Opens the "AI model" dialog in the header from anywhere on the page (the "change" link beside the search box). */
export function openModelDialog() {
  window.dispatchEvent(new Event(MODEL_DIALOG_EVENT))
}

/** A number of seconds (or any measured value) to fixed digits; a dash when there is none. */
export const fmt = (s: number | null | undefined, digits = 2) => (s == null ? '—' : s.toFixed(digits))
