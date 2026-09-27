// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
// Live Wire connection: WebSocket first, exponential backoff with full jitter
// between reconnects, and quiet REST polling (/api/livewire) while the socket
// is down (for example the few seconds after an API redeploy). The browser
// itself logs every failed WebSocket handshake, so the only way to keep the
// console quiet is to try less often: attempts back off to `maxMs`, a new
// attempt waits until a REST poll has reached the API, and the page logs at
// most one info line per session. Timers and the socket are injected so the
// schedule can be tested without a network.

export type FeedStatus = "connecting" | "live" | "reconnecting";

export interface BackoffOptions {
  baseMs?: number;
  maxMs?: number;
}
/**
 * Delay before reconnect attempt `attempt` (0-based): "full jitter", a random
 * point in [0, min(max, base * 2^attempt)], floored at a quarter of the base so
 * a tight loop is impossible.
 */
export function backoffDelay(attempt: number, random: () => number = Math.random, options: BackoffOptions = {}): number {
  const base = options.baseMs ?? 1000;
  const max = options.maxMs ?? 30_000;
  const ceiling = Math.min(max, base * 2 ** Math.max(0, Math.min(30, attempt)));
  return Math.max(base / 4, Math.round(random() * ceiling));
}

export interface SocketLike {
  onopen: ((ev?: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev?: unknown) => void) | null;
  onerror: ((ev?: unknown) => void) | null;
  close(): void;
}
export interface ConnectionDeps<E> {
  openSocket: () => SocketLike;
  /** REST fallback: resolves with the latest events, rejects when the API is unreachable. */
  poll: () => Promise<E[]>;
  onEvents: (events: E[]) => void;
  onStatus: (status: FeedStatus) => void;
  /** Parse one socket frame into events (may throw on malformed frames; those are skipped). */
  parse: (data: unknown) => E[];
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
  random?: () => number;
  log?: (message: string) => void;
  backoff?: BackoffOptions;
  pollMs?: number;
}

export function connectLivewire<E>(deps: ConnectionDeps<E>): () => void {
  const setTimer = deps.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
  const clearTimer = deps.clearTimer ?? ((h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>));
  const random = deps.random ?? Math.random;
  const pollMs = deps.pollMs ?? 20_000;
  let socket: SocketLike | undefined;
  let attempt = 0;
  let stopped = false;
  let reconnectTimer: unknown;
  let pollTimer: unknown;
  let status: FeedStatus | undefined;
  let logged = false;
  // True once a REST poll reached the API since the socket dropped; the next
  // socket attempt waits for it so a redeploy does not produce a burst of
  // failed handshakes.
  let reachable = true;

  const setStatus = (next: FeedStatus) => {
    if (next !== status) deps.onStatus((status = next));
  };
  // One polling loop at a time (a request in flight counts as running).
  let polling = false;
  const stopPolling = () => {
    if (pollTimer !== undefined) clearTimer(pollTimer);
    pollTimer = undefined;
    polling = false;
  };
  const pollLoop = () => {
    if (stopped || polling) return;
    polling = true;
    const tick = () => {
      pollTimer = undefined;
      if (stopped || !polling || status === "live") {
        polling = false;
        return;
      }
      deps
        .poll()
        .then((events) => {
          reachable = true;
          if (!stopped && status !== "live" && events.length) deps.onEvents(events);
        })
        .catch(() => {
          reachable = false;
        })
        .finally(() => {
          if (stopped || !polling || status === "live") polling = false;
          else pollTimer = setTimer(tick, pollMs);
        });
    };
    tick();
  };
  const scheduleReconnect = () => {
    if (stopped || reconnectTimer !== undefined) return;
    const delay = backoffDelay(attempt++, random, deps.backoff);
    reconnectTimer = setTimer(() => {
      reconnectTimer = undefined;
      if (stopped) return;
      // API still unreachable: wait for polling to find it before handshaking.
      if (!reachable) scheduleReconnect();
      else open();
    }, delay);
  };
  const dropped = () => {
    if (stopped) return;
    socket = undefined;
    if (!logged && deps.log) {
      logged = true;
      deps.log("Live wire: socket unavailable, retrying with backoff and polling /api/livewire meanwhile.");
    }
    setStatus("reconnecting");
    pollLoop();
    scheduleReconnect();
  };
  const open = () => {
    if (stopped) return;
    if (status === undefined) setStatus("connecting");
    let s: SocketLike;
    try {
      s = deps.openSocket();
    } catch {
      dropped();
      return;
    }
    socket = s;
    s.onopen = () => {
      if (stopped || socket !== s) return;
      attempt = 0;
      reachable = true;
      stopPolling();
      setStatus("live");
    };
    s.onmessage = ({ data }) => {
      if (stopped || socket !== s) return;
      try {
        const events = deps.parse(data);
        if (events.length) deps.onEvents(events);
      } catch {
        /* Keep malformed frames from interrupting the feed. */
      }
    };
    s.onerror = () => {
      // onclose follows; nothing to report here (no console noise).
    };
    s.onclose = () => {
      if (socket !== s) return;
      // A handshake that never opened counts as unreachable until a poll says otherwise.
      if (status !== "live") reachable = false;
      dropped();
    };
  };
  open();
  return () => {
    stopped = true;
    if (reconnectTimer !== undefined) clearTimer(reconnectTimer);
    stopPolling();
    const s = socket;
    socket = undefined;
    if (s) {
      s.onclose = s.onerror = s.onmessage = s.onopen = null;
      s.close();
    }
  };
}
