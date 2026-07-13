import ReconnectingWebSocket from "reconnecting-websocket"

import type { StreamWsMessage } from "@/protocol/stream"

export type StreamMessageHandler = (msg: StreamWsMessage) => void

function wsUrl(): string {
  const base = import.meta.env.VITE_DASH_WS ?? import.meta.env.VITE_DASH_API ?? ""
  if (base.startsWith("http")) {
    return base.replace(/^http/, "ws") + "/ws/stream"
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${proto}//${window.location.host}/ws/stream`
}

export class StreamSocket {
  private ws: ReconnectingWebSocket
  private handlers = new Set<StreamMessageHandler>()

  constructor() {
    this.ws = new ReconnectingWebSocket(wsUrl(), [], {
      minReconnectionDelay: 500,
      maxReconnectionDelay: 10_000,
      reconnectionDelayGrowFactor: 1.5,
      maxRetries: Infinity,
    })
    this.ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(String(ev.data)) as StreamWsMessage
      for (const h of this.handlers) h(msg)
    })
  }

  subscribe(handler: StreamMessageHandler) {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  ping() {
    this.ws.send(JSON.stringify({ type: "ping" }))
  }

  close() {
    this.ws.close()
  }
}
