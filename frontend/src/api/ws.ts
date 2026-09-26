/**
 * WebSocket client — the console's single real-time channel (/ws).
 * Dispatches typed events (feed_event, alert_event) to subscribers and
 * reconnects automatically with exponential backoff on disconnect.
 */
import type { WsMessage } from '@/types'

type MessageHandler = (msg: WsMessage) => void

class WebSocketClient {
  private ws: WebSocket | null = null
  private handlers: Set<MessageHandler> = new Set()
  private retryDelay = 1000
  private maxRetryDelay = 30_000
  private shouldReconnect = false

  connect(token: string): void {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return // already connecting/open
    this.shouldReconnect = true
    // Same-origin by default (/ws is proxied to the gateway); override for CDN hosting
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsBase = import.meta.env.VITE_WS_URL ?? `${scheme}://${window.location.host}`
    const url = `${wsBase}/ws?token=${encodeURIComponent(token)}`
    this._open(url)
  }

  disconnect(): void {
    this.shouldReconnect = false
    this.ws?.close()
    this.ws = null
    this.retryDelay = 1000
  }

  subscribe(handler: MessageHandler): () => void {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  send(msg: WsMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  private _open(url: string): void {
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this.retryDelay = 1000 // reset on successful connect
    }

    this.ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data as string)
        if (msg.type === 'ping') {
          this.send({ type: 'pong' })
          return
        }
        this.handlers.forEach((h) => h(msg))
      } catch {
        // ignore malformed messages
      }
    }

    this.ws.onclose = () => {
      if (!this.shouldReconnect) return
      setTimeout(() => {
        this.retryDelay = Math.min(this.retryDelay * 2, this.maxRetryDelay)
        this._open(url)
      }, this.retryDelay)
    }
  }
}

export const wsClient = new WebSocketClient()
