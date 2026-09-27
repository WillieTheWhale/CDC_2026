// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { backoffDelay, connectLivewire, type FeedStatus, type SocketLike } from "./livewire-connection";

test("backoff grows exponentially, is capped, and jitters below the ceiling", () => {
  const top = () => 1; // the ceiling itself
  assert.deepEqual(
    [0, 1, 2, 3, 4, 5, 6, 10].map((n) => backoffDelay(n, top, { baseMs: 1000, maxMs: 30_000 })),
    [1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000],
  );
  // Full jitter: a random point below the ceiling, floored at base / 4.
  assert.equal(backoffDelay(3, () => 0.5, { baseMs: 1000 }), 4000);
  assert.equal(backoffDelay(3, () => 0, { baseMs: 1000 }), 250);
  for (let i = 0; i < 200; i++) {
    const d = backoffDelay(4, Math.random, { baseMs: 1000, maxMs: 30_000 });
    assert.ok(d >= 250 && d <= 16000, String(d));
  }
  // Huge attempt counts never overflow.
  assert.equal(backoffDelay(5000, top, { baseMs: 1000, maxMs: 60_000 }), 60000);
});

// A hand-driven clock and socket factory.
function harness(pollResults: (() => Promise<string[]>)[] = []) {
  const timers: { fn: () => void; ms: number; id: number }[] = [];
  let nextId = 0;
  const sockets: SocketLike[] = [];
  const statuses: FeedStatus[] = [];
  const events: string[] = [];
  const logs: string[] = [];
  let polls = 0;
  const stop = connectLivewire<string>({
    openSocket: () => {
      const s: SocketLike = { onopen: null, onmessage: null, onclose: null, onerror: null, close() {} };
      sockets.push(s);
      return s;
    },
    poll: () => {
      const next = pollResults[polls++];
      return next ? next() : Promise.resolve([]);
    },
    parse: (data) => JSON.parse(String(data)),
    onEvents: (e) => events.push(...e),
    onStatus: (s) => statuses.push(s),
    log: (m) => logs.push(m),
    random: () => 1,
    backoff: { baseMs: 1000, maxMs: 8000 },
    pollMs: 20_000,
    setTimer: (fn, ms) => {
      const id = nextId++;
      timers.push({ fn, ms, id });
      return id;
    },
    clearTimer: (id) => {
      const i = timers.findIndex((t) => t.id === id);
      if (i >= 0) timers.splice(i, 1);
    },
  });
  const fire = async (ms: number) => {
    const i = timers.findIndex((t) => t.ms === ms);
    assert.ok(i >= 0, `no timer of ${ms} ms (have ${timers.map((t) => t.ms).join(", ")})`);
    const [t] = timers.splice(i, 1);
    t.fn();
    await new Promise((r) => setImmediate(r));
  };
  const settle = () => new Promise((r) => setImmediate(r));
  return { timers, sockets, statuses, events, logs, stop, fire, settle, polls: () => polls };
}

test("failed handshakes back off, poll REST quietly, and log once", async () => {
  const h = harness([() => Promise.reject(new Error("down")), () => Promise.resolve(["rest-1"])]);
  assert.deepEqual(h.statuses, ["connecting"]);
  h.sockets[0].onerror?.();
  h.sockets[0].onclose?.();
  await h.settle();
  assert.deepEqual(h.statuses, ["connecting", "reconnecting"]);
  assert.equal(h.logs.length, 1);
  assert.equal(h.polls(), 1); // first poll fails: API unreachable
  // Reconnect timer fires, but the API was unreachable: no new handshake yet.
  await h.fire(1000);
  assert.equal(h.sockets.length, 1);
  // Next poll reaches the API and delivers events; the next retry handshakes.
  await h.fire(20_000);
  assert.deepEqual(h.events, ["rest-1"]);
  await h.fire(2000);
  assert.equal(h.sockets.length, 2);
  // Still failing: the delay keeps doubling up to the cap, still one log line.
  h.sockets[1].onclose?.();
  await h.settle();
  assert.ok(h.timers.some((t) => t.ms === 4000));
  assert.equal(h.logs.length, 1);
  h.stop();
  assert.equal(h.timers.length, 0);
});

test("a successful connection resets the backoff, stops polling and parses frames", async () => {
  const h = harness();
  h.sockets[0].onopen?.();
  assert.deepEqual(h.statuses, ["connecting", "live"]);
  h.sockets[0].onmessage?.({ data: JSON.stringify(["a", "b"]) });
  h.sockets[0].onmessage?.({ data: "not json" }); // skipped, no throw
  assert.deepEqual(h.events, ["a", "b"]);
  h.sockets[0].onclose?.();
  await h.settle();
  assert.deepEqual(h.statuses, ["connecting", "live", "reconnecting"]);
  // A socket that had been live keeps the API reachable: retry after the base delay.
  await h.fire(1000);
  assert.equal(h.sockets.length, 2);
  h.sockets[1].onopen?.();
  assert.equal(h.statuses.at(-1), "live");
  assert.ok(!h.timers.some((t) => t.ms === 20_000), "polling stops once live");
  h.sockets[1].onclose?.();
  await h.settle();
  assert.ok(h.timers.some((t) => t.ms === 1000), "backoff restarted from the base");
  h.stop();
});

test("stopping ignores late socket callbacks", async () => {
  const h = harness();
  const s = h.sockets[0];
  h.stop();
  s.onopen?.();
  s.onclose?.();
  await h.settle();
  assert.deepEqual(h.statuses, ["connecting"]);
  assert.equal(h.timers.length, 0);
});
