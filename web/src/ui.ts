// Small page helpers shared by several components (kept out of component files so fast refresh keeps working).

/** Scroll an element into view; instant for people who asked for less motion. */
export function scrollToId(id: string, block: ScrollLogicalPosition = 'start') {
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document.getElementById(id)?.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block })
}

export const MODEL_DIALOG_EVENT = 'lucida-open-model'
export type ModelDialogOpen = { opener: HTMLElement | null; kind?: 'key' | 'device' }
/** Opens the "AI model" dialog in the header from anywhere on the page, optionally already on the key or the device option. */
export function openModelDialog(kind?: 'key' | 'device') {
  window.dispatchEvent(new CustomEvent<ModelDialogOpen>(MODEL_DIALOG_EVENT, { detail: { opener: document.activeElement instanceof HTMLElement ? document.activeElement : null, kind } }))
}

/** A number of seconds (or any measured value) to fixed digits; a dash when there is none. */
export const fmt = (s: number | null | undefined, digits = 2) => (s == null ? '—' : s.toFixed(digits))
