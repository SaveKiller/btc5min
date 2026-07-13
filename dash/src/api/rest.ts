import type { RoundHeader, SessionPayload } from "@/protocol/stream"

const API_BASE = import.meta.env.VITE_DASH_API ?? ""

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${path} failed: ${res.status} ${text}`)
  }
  return res.json() as Promise<T>
}

export function getHealth() {
  return api<{ ok: boolean }>("/health")
}

export function listRounds(limit = 50) {
  return api<Array<{ market_start_ts: number; market_end_ts: number; outcome: string; tick_count: number; bin_path: string }>>(
    `/rounds?limit=${limit}`,
  )
}

export function getRoundHeader(market_start_ts: number) {
  return api<RoundHeader>(`/rounds/${market_start_ts}/header`)
}

export function getSession() {
  return api<{ active: boolean } & Partial<SessionPayload>>("/session")
}

export function startReplay(market_start_ts: number, start_sec = 300) {
  return api<{ active: boolean } & SessionPayload>("/session/replay", {
    method: "POST",
    body: JSON.stringify({ market_start_ts, start_sec }),
  })
}

export function startLive() {
  return api<{ active: boolean } & SessionPayload>("/session/live", { method: "POST" })
}

export function seek(sec: number) {
  return api<{ active: boolean } & SessionPayload>("/session/seek", {
    method: "POST",
    body: JSON.stringify({ sec }),
  })
}

export function play() {
  return api<{ active: boolean } & SessionPayload>("/session/play", { method: "POST" })
}

export function pause() {
  return api<{ active: boolean } & SessionPayload>("/session/pause", { method: "POST" })
}

export function stopSession() {
  return api<{ active: boolean }>("/session/stop", { method: "POST" })
}
