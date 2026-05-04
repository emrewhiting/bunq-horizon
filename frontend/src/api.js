// thin wrapper around the backend. set VITE_API_URL for prod, localhost otherwise.

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function jsonFetch(path, opts = {}) {
  const res = await fetch(`${API_URL}${path}`, opts)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${text || 'request failed'}`)
  }
  return res.json()
}

export function getContext() {
  return jsonFetch('/context')
}

export function getBalance() {
  return jsonFetch('/balance')
}

export async function classifyImage(file) {
  const fd = new FormData()
  fd.append('image', file)
  return jsonFetch('/classify', { method: 'POST', body: fd })
}

export async function getPerspective({ price, category, item }) {
  return jsonFetch('/perspective', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ price, category, item }),
  })
}

export async function analyze({ file, price }) {
  const fd = new FormData()
  fd.append('image', file)
  fd.append('price', String(price))
  return jsonFetch('/analyze', { method: 'POST', body: fd })
}

export { API_URL }
