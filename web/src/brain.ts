// The visitor's own model for the understand step. Held in memory only (never localStorage, never a cookie, never the URL): reloading the page forgets it.
// The server speaks two kinds: Anthropic's own API, and "openai" = any provider with an OpenAI-style /chat/completions address (most of them).
export type BrainKind = 'local' | 'anthropic' | 'openai' | 'device'   // device: a model already running on the visitor's own device; the page asks it directly
export type BrainSetting = { kind: BrainKind; provider: string; key: string; model: string; baseUrl: string; priceIn: string; priceOut: string }   // prices: dollars per million tokens, optional, only to show money

export type Provider = { id: string; label: string; kind: Exclude<BrainKind, 'local'>; baseUrl: string; modelHint: string }
// Addresses are the providers' documented OpenAI-compatible ones. Model names are only examples: type the one from your provider's own list.
export const PROVIDERS: Provider[] = [
  { id: 'anthropic', label: 'Anthropic (Claude)', kind: 'anthropic', baseUrl: '', modelHint: 'claude-haiku-5-5' },
  { id: 'openai', label: 'OpenAI', kind: 'openai', baseUrl: 'https://api.openai.com/v1', modelHint: 'gpt-4o-mini' },
  { id: 'gemini', label: 'Google Gemini', kind: 'openai', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai', modelHint: 'a Gemini model name from Google AI Studio' },
  { id: 'deepseek', label: 'DeepSeek', kind: 'openai', baseUrl: 'https://api.deepseek.com/v1', modelHint: 'deepseek-chat' },
  { id: 'groq', label: 'Groq', kind: 'openai', baseUrl: 'https://api.groq.com/openai/v1', modelHint: 'a model id from console.groq.com' },
  { id: 'mistral', label: 'Mistral', kind: 'openai', baseUrl: 'https://api.mistral.ai/v1', modelHint: 'a model name from Mistral' },
  { id: 'openrouter', label: 'OpenRouter (hundreds of models)', kind: 'openai', baseUrl: 'https://openrouter.ai/api/v1', modelHint: 'a model id from openrouter.ai/models' },
  { id: 'together', label: 'Together AI', kind: 'openai', baseUrl: 'https://api.together.xyz/v1', modelHint: 'a model id from Together' },
  { id: 'custom', label: 'Another OpenAI-compatible server (type its address)', kind: 'openai', baseUrl: '', modelHint: 'the model name your server uses' },
]
// Apps that run a model on the visitor's own device, at their documented OpenAI-compatible local addresses.
export const DEVICE_APPS: Provider[] = [
  { id: 'ollama', label: 'Ollama', kind: 'device', baseUrl: 'http://localhost:11434/v1', modelHint: 'e.g. qwen3:4b-instruct' },
  { id: 'lmstudio', label: 'LM Studio', kind: 'device', baseUrl: 'http://localhost:1234/v1', modelHint: 'the model loaded in LM Studio' },
  { id: 'device-custom', label: 'Another OpenAI-compatible local server', kind: 'device', baseUrl: '', modelHint: 'the model name your server uses' },
]
export const providerOf = (id: string): Provider => PROVIDERS.find((p) => p.id === id) ?? DEVICE_APPS.find((p) => p.id === id) ?? PROVIDERS[PROVIDERS.length - 1]

export const LOCAL: BrainSetting = { kind: 'local', provider: 'local', key: '', model: '', baseUrl: '', priceIn: '', priceOut: '' }
// Anthropic's published prices in dollars per million tokens (input, output), read 2026-10-14 (the same table as src/genkart/claude_client.py). Any other model: the person enters theirs.
export const KNOWN_PRICES: Record<string, [number, number]> = { 'claude-sonnet-5-5': [2, 10], 'claude-haiku-5-5': [0.1, 0.5] }
export const withProvider = (b: BrainSetting, id: string): BrainSetting => {
  const p = providerOf(id)
  return { ...b, kind: p.kind, provider: id, baseUrl: p.baseUrl, model: b.provider === id ? b.model : '' }
}
/** A key can be used once it looks like one, and a model name is given (only Anthropic has a default), and a custom provider has an address. */
export const usable = (b: BrainSetting): boolean =>
  b.kind === 'local' || (b.kind === 'device' ? b.model.trim().length > 0 && /^https?:\/\//.test(b.baseUrl.trim()) : (b.key.trim().length >= 8 && (b.kind === 'anthropic' || b.model.trim().length > 0) && (b.provider !== 'custom' || /^https?:\/\//.test(b.baseUrl.trim()))))

/** What the page tells the person is in use, without ever showing the key. */
export const describe = (b: BrainSetting): string =>
  b.kind === 'local' ? 'the model on this computer (Ollama)' : b.kind === 'device' ? `${b.model || 'a model'} on your device (${providerOf(b.provider).label.replace(/ \(.*\)$/, '')})` : `${b.model || providerOf(b.provider).modelHint} on your ${providerOf(b.provider).label.replace(/ \(.*\)$/, '')} key`

/** The body sent to your own server. The key travels in this POST body only, never in an address. */
export const toBody = (q: string, b: BrainSetting) => ({ q, brain: { kind: b.kind, key: b.key, model: b.model || undefined, base_url: b.baseUrl || undefined } })
