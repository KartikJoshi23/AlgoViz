/**
 * WebSocket client (module-level singleton, outside React).
 *
 * - jittered exponential backoff (1 s → 30 s), automatic resubscribe
 * - heartbeat ping every 15 s → latency estimate; missed pongs force a reconnect
 * - every server frame is handed to the store's `applyFrame`
 * - `hello` + `snapshot` hydrate on (re)connect; symbol switches re-hydrate
 */
import { WS_URL } from "@/lib/api/client";
import { useStore, type ConnectionState, type ConnectionStatus } from "@/lib/store";
import type { Channel, ClientMessage, ServerMessage } from "@/lib/ws/types";

const BACKOFF_MIN_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;
const PING_INTERVAL_MS = 15_000;
const PONG_TIMEOUT_MS = 10_000;

class WsClient {
  private ws: WebSocket | null = null;
  private url = WS_URL;
  private symbol: string | null = null;
  private channels: Channel[] | null = null;
  private attempt = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private pongTimer: ReturnType<typeof setTimeout> | null = null;
  private pingSentAt = 0;
  private wanted = false;
  private queue: ClientMessage[] = [];

  start(opts: { url?: string; symbol?: string | null; channels?: Channel[] } = {}): void {
    if (typeof window === "undefined") return;
    this.url = opts.url ?? this.url;
    if (opts.symbol !== undefined) this.symbol = opts.symbol;
    if (opts.channels) this.channels = opts.channels;
    this.wanted = true;
    // Defer the actual socket by a tick: React StrictMode mounts, unmounts and
    // remounts effects synchronously in development, and opening a socket only
    // to close it before it connects logs a browser warning.
    if (!this.ws && !this.retryTimer) this.retryTimer = setTimeout(() => this.connect(), 0);
  }

  stop(): void {
    this.wanted = false;
    this.clearTimers();
    const ws = this.ws;
    this.ws = null; // detach first so the late onclose is ignored
    ws?.close(1000, "client stop");
    this.setStatus("closed", { nextRetryAt: null });
  }

  /** Switch symbol (the server re-sends a snapshot; the store resets rings). */
  setSymbol(symbol: string): void {
    if (symbol === this.symbol) return;
    this.symbol = symbol;
    useStore.getState().resetMarket();
    this.send({ op: "subscribe", symbol });
  }

  subscribe(channels: Channel[]): void {
    this.channels = channels;
    this.send({ op: "subscribe", channels });
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // ── internals ────────────────────────────────────────────────

  private connect(): void {
    this.clearTimers();
    const url = this.symbol ? `${this.url}?symbol=${encodeURIComponent(this.symbol)}` : this.url;
    this.setStatus(this.attempt === 0 ? "connecting" : "reconnecting", { attempt: this.attempt, nextRetryAt: null });
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      this.scheduleRetry();
      return;
    }
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    // Every handler checks it still belongs to the current socket: React StrictMode
    // (and fast stop/start) can leave a closing socket whose late `onclose` would
    // otherwise clobber the new connection and schedule a duplicate one.
    const stale = () => this.ws !== ws;

    ws.onopen = () => {
      if (stale()) return;
      this.attempt = 0;
      this.setStatus("open", { attempt: 0, nextRetryAt: null });
      if (this.channels) this.send({ op: "subscribe", channels: this.channels });
      for (const m of this.queue.splice(0)) this.send(m);
      this.startHeartbeat();
    };

    ws.onmessage = (ev: MessageEvent<string | ArrayBuffer>) => {
      if (stale()) return;
      let msg: ServerMessage;
      try {
        const text = typeof ev.data === "string" ? ev.data : new TextDecoder().decode(ev.data);
        msg = JSON.parse(text) as ServerMessage;
      } catch {
        return;
      }
      if (msg.type === "pong") {
        const rtt = performance.now() - this.pingSentAt;
        if (this.pongTimer) clearTimeout(this.pongTimer);
        this.pongTimer = null;
        useStore.getState().setConnection({ latencyMs: Math.round(rtt) });
        return;
      }
      useStore.getState().applyFrame(msg);
    };

    ws.onerror = () => {
      /* onclose follows */
    };

    ws.onclose = () => {
      if (stale()) return;
      this.ws = null;
      this.clearTimers();
      if (this.wanted) this.scheduleRetry();
      else this.setStatus("closed", { nextRetryAt: null });
    };
  }

  private scheduleRetry(): void {
    this.attempt += 1;
    const base = Math.min(BACKOFF_MIN_MS * 2 ** (this.attempt - 1), BACKOFF_MAX_MS);
    const jitter = base * (0.8 + Math.random() * 0.4);
    const at = Date.now() + jitter;
    this.setStatus("reconnecting", { attempt: this.attempt, nextRetryAt: at });
    this.retryTimer = setTimeout(() => this.connect(), jitter);
  }

  private startHeartbeat(): void {
    this.pingTimer = setInterval(() => {
      if (!this.isOpen) return;
      this.pingSentAt = performance.now();
      this.send({ op: "ping", ts: Date.now() });
      this.pongTimer = setTimeout(() => {
        // missed pong → the socket is dead even if the OS hasn't noticed
        this.ws?.close(4000, "pong timeout");
      }, PONG_TIMEOUT_MS);
    }, PING_INTERVAL_MS);
  }

  private clearTimers(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    if (this.pongTimer) clearTimeout(this.pongTimer);
    this.retryTimer = this.pingTimer = this.pongTimer = null;
  }

  private send(m: ClientMessage): void {
    if (this.isOpen) this.ws!.send(JSON.stringify(m));
    else if (m.op !== "ping") this.queue.push(m);
  }

  private setStatus(status: ConnectionStatus, patch: Partial<ConnectionState> = {}): void {
    useStore.getState().setConnection({ status, ...patch });
  }
}

export const wsClient = new WsClient();
