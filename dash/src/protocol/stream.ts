/** Protocollo streaming unificato replay/live — allineato a dash-api/protocol.py */

export type StreamMode = "replay" | "live"

export type WsMessageType = "session" | "tick" | "state" | "error" | "pong"

export type StateReason = "seek" | "play" | "pause" | "stop" | "round_end" | "session_start"

export interface WsEnvelope<T = unknown> {
  type: WsMessageType
  payload: T
}

export interface RoundHeader {
  market_start_ts: number
  market_end_ts: number
  outcome: string
  tick_count: number
  ptb_chainlink: number
  ptb_gamma: number | null
  final_chainlink: number
  final_gamma: number | null
}

export interface SessionPayload {
  mode: StreamMode
  market_start_ts: number
  market_end_ts: number
  ptb_chainlink: number
  outcome: string
  playing: boolean
  sec: number
}

export interface TickPayload {
  seq: number
  sec: number
  recv_ts_ms: number
  chainlink_btc: number | null
  chainlink_stale: boolean
  up_bid: number | null
  up_ask: number | null
  down_bid: number | null
  down_ask: number | null
  delta_usd: number | null
  majority_gain: number | null
  partial: boolean
}

export interface StatePayload {
  playing: boolean
  sec: number
  reason: StateReason
}

export interface ErrorPayload {
  message: string
}

export type StreamWsMessage =
  | WsEnvelope<SessionPayload>
  | WsEnvelope<TickPayload>
  | WsEnvelope<StatePayload>
  | WsEnvelope<ErrorPayload>
  | WsEnvelope<Record<string, never>>
