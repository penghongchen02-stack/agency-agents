import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { PaperBroker } from "../src/broker.js";
import { LIVE_CONFIRM_PHRASE, describeConfig, loadConfig } from "../src/config.js";
import { Engine } from "../src/engine.js";
import { Ledger, redact, replayLedger } from "../src/log.js";
import { parseGammaMarket, parseResolution, slotStartFor, slugFor } from "../src/markets.js";
import { decide, normCdf, probUp, type Quote } from "../src/model.js";
import { PriceTape } from "../src/priceFeed.js";
import { score } from "../src/report.js";
import { RiskManager } from "../src/risk.js";
import { twapScratch, winnerLock } from "../src/strategies.js";

const FAKE_KEY = "0x" + "ab".repeat(32);
const SLOT = 1_800_000_000;

function q(side: "UP" | "DOWN", ask: number | null, bid: number | null = null, size = 500): Quote {
  return { side, tokenId: side === "UP" ? "U" : "D", bestAsk: ask, askSize: size, bestBid: bid, bidSize: size };
}

test("slot math for 5m and 15m", () => {
  assert.equal(slotStartFor(1_800_000_123), 1_800_000_000);
  assert.equal(slotStartFor(1_800_000_123, 900), 1_800_000_000);
  assert.equal(slotStartFor(1_800_001_000, 900), 1_800_000_900);
  assert.equal(slugFor(SLOT), "btc-updown-5m-1800000000");
  assert.equal(slugFor(SLOT, "15m"), "btc-updown-15m-1800000000");
  assert.equal(parseGammaMarket({ outcomes: '["Up","Down"]', clobTokenIds: '["a","b"]' }, SLOT, "15m").slotEnd, SLOT + 900);
});

test("normCdf matches known values", () => {
  assert.ok(Math.abs(normCdf(0) - 0.5) < 1e-7);
  assert.ok(Math.abs(normCdf(1.96) - 0.975) < 1e-3);
  assert.ok(Math.abs(normCdf(-1.96) - 0.025) < 1e-3);
});

test("probUp: flat is 50/50, moves push it the right way, never certain", () => {
  const base = { openPrice: 100_000, secondsLeft: 120, volBpsPerSqrtSec: 1 };
  assert.ok(Math.abs(probUp({ ...base, currentPrice: 100_000 }) - 0.5) < 1e-6);
  assert.ok(probUp({ ...base, currentPrice: 100_100 }) > 0.8);
  assert.ok(probUp({ ...base, currentPrice: 99_900 }) < 0.2);
  assert.equal(probUp({ ...base, currentPrice: 200_000 }), 0.99);
  assert.equal(probUp({ ...base, currentPrice: 100_001, secondsLeft: 0 }), 0.99);
});

test("decide: needs edge after fees, respects price band and side filter", () => {
  const params = { minEdge: 0.05, feeBuffer: 0.02, minEntryPrice: 0.2, maxEntryPrice: 0.8 };
  const quotes = [q("UP", 0.6), q("DOWN", 0.42)];
  assert.equal(decide({ ...params, pUp: 0.65, quotes }), null); // 0.65-0.60-0.02 = 0.03 < 0.05
  const d = decide({ ...params, pUp: 0.7, quotes });
  assert.equal(d?.side, "UP");
  assert.ok(Math.abs(d!.edge - 0.08) < 1e-9);
  assert.equal(decide({ ...params, pUp: 0.95, quotes: [q("UP", 0.85)] }), null);
  assert.equal(decide({ ...params, pUp: 0.7, quotes: [q("UP", null)] }), null);
  assert.equal(decide({ ...params, pUp: 0.7, quotes, onlySide: "DOWN" }), null);
});

test("PriceTape: open price only trusted near the boundary; vol and TWAP", () => {
  const tape = new PriceTape();
  tape.push({ tsMs: SLOT * 1000 + 12_000, price: 100_000 });
  assert.equal(tape.openPrice(SLOT), null); // first tick 12s late: untrusted

  const t2 = new PriceTape();
  for (let i = -60; i <= 60; i++) t2.push({ tsMs: (SLOT + i) * 1000, price: 100_000 + (i % 2) * 10 });
  assert.equal(t2.openPrice(SLOT), 100_000);
  const vol = t2.volBpsPerSqrtSec();
  assert.ok(vol !== null && vol > 0.5 && vol < 2, `vol=${vol}`);

  // 20s at 100, then 10s at 130 → 30s TWAP = 110
  const t3 = new PriceTape();
  t3.push({ tsMs: 0, price: 100 });
  t3.push({ tsMs: 20_000, price: 130 });
  t3.push({ tsMs: 30_000, price: 130 });
  assert.equal(t3.twap(30_000), 110);
});

test("config: paper by default, live demands confirmation and valid key", () => {
  const def = loadConfig({});
  assert.equal(def.mode, "paper");
  assert.equal(def.strategy, "fair-value");
  assert.equal(def.slotSeconds, 300);
  assert.equal(loadConfig({ MARKET_WINDOW: "15m" }).slotSeconds, 900);
  assert.throws(() => loadConfig({ STRATEGY: "martingale" }), /STRATEGY/);
  assert.throws(() => loadConfig({ MODE: "live", PRIVATE_KEY: FAKE_KEY }), /LIVE_CONFIRM/);
  assert.throws(
    () => loadConfig({ MODE: "live", LIVE_CONFIRM: LIVE_CONFIRM_PHRASE, PRIVATE_KEY: "0x123" }),
    /PRIVATE_KEY/,
  );
  const live = loadConfig({
    MODE: "live",
    LIVE_CONFIRM: LIVE_CONFIRM_PHRASE,
    PRIVATE_KEY: FAKE_KEY,
    FUNDER_ADDRESS: "0x" + "1".repeat(40),
  });
  assert.equal(live.privateKey, FAKE_KEY);
  assert.ok(!JSON.stringify(describeConfig(live)).includes("abab"));
  assert.throws(() => loadConfig({ MIN_EDGE: "nope" }), /MIN_EDGE/);
  assert.throws(() => loadConfig({ STAKE_USD: "10", MAX_SLOT_USD: "5" }), /MAX_SLOT_USD/);
});

test("paper mode ignores a key even if one is set", () => {
  assert.equal(loadConfig({ PRIVATE_KEY: FAKE_KEY }).privateKey, "");
});

test("redact removes private keys from any text", () => {
  assert.ok(!redact(`key=${FAKE_KEY}`).includes("abab"));
  assert.ok(!redact(`key=${"cd".repeat(32)}`).includes("cdcd"));
  assert.equal(redact("price=0.52"), "price=0.52");
});

test("gamma parsing", () => {
  const m = parseGammaMarket(
    { question: "BTC up?", outcomes: '["Up","Down"]', clobTokenIds: '["111","222"]' },
    SLOT,
  );
  assert.equal(m.upTokenId, "111");
  assert.equal(m.downTokenId, "222");
  assert.equal(parseResolution({ closed: false, outcomes: '["Up","Down"]', outcomePrices: '["1","0"]' }), null);
  assert.equal(parseResolution({ closed: true, outcomes: '["Up","Down"]', outcomePrices: '["0","1"]' }), "DOWN");
});

test("risk: per-slot trade and USD caps, loss limit counts open exposure, STOP file", () => {
  const dir = mkdtempSync(join(tmpdir(), "risk-"));
  const stop = join(dir, "STOP");
  const limits = { stakeUsd: 10, maxTradesPerSlot: 1, maxSlotUsd: 30, maxDailyLossUsd: 25, maxDailyTrades: 99 };
  const r = new RiskManager(limits, stop);
  assert.deepEqual(r.canEnter(1, 100), { ok: true });
  r.recordEntry(1, 10);
  assert.equal(r.canEnter(1, 100).ok, false); // same slot
  r.recordEntry(2, 10); // exposure 20, next stake would make worst case -30
  assert.equal(r.canEnter(3, 100).ok, false);
  r.recordClose(10, 9); // one win
  assert.equal(r.canEnter(3, 100).ok, true);
  writeFileSync(stop, "");
  assert.deepEqual(r.canEnter(4, 100), { ok: false, reason: "STOP file present" });

  const r2 = new RiskManager({ ...limits, maxTradesPerSlot: 5, maxDailyLossUsd: 1000 }, join(dir, "none"));
  r2.recordEntry(7, 10);
  r2.recordEntry(7, 10);
  assert.equal(r2.canEnter(7, 100, 10).ok, true); // 30 total = cap
  r2.recordEntry(7, 10);
  assert.deepEqual(r2.canEnter(7, 100, 10), { ok: false, reason: "max USD for this slot" });
});

test("twap-scratch: buys only in the 45–55¢ band, adds on same side, scratches on flip", () => {
  const cfg = loadConfig({ STRATEGY: "twap-scratch" });
  const base = { cfg, secIn: 60, secLeft: 240, position: null };
  // Strong UP signal but ask outside band → nothing
  assert.equal(twapScratch.act({ ...base, pUp: 0.7, quotes: [q("UP", 0.62), q("DOWN", 0.4)] }), null);
  const buy = twapScratch.act({ ...base, pUp: 0.6, quotes: [q("UP", 0.5, 0.49), q("DOWN", 0.51, 0.5)] });
  assert.equal(buy?.kind, "buy");
  assert.equal(buy?.side, "UP");

  const position = {
    slug: "s", slotStart: SLOT, slotEnd: SLOT + 300, side: "UP" as const, tokenId: "U",
    shares: 10, costUsd: 5, modelProb: 0.6, clips: 1,
  };
  // Signal now favours DOWN strongly: no hedge buy of DOWN, scratch the UP instead.
  const flip = twapScratch.act({ ...base, position, pUp: 0.4, quotes: [q("UP", 0.45, 0.44), q("DOWN", 0.5, 0.49)] });
  assert.equal(flip?.kind, "sell");
  assert.equal(flip?.side, "UP");
  // Outside entry window but still holding: exits allowed, buys not.
  const late = twapScratch.act({ ...base, secIn: 200, secLeft: 100, position, pUp: 0.62, quotes: [q("UP", 0.5, 0.49), q("DOWN", 0.5, 0.49)] });
  assert.equal(late, null);
});

test("winner-lock: only in the last 60s, only 90–96¢, only if the model agrees", () => {
  const cfg = loadConfig({ STRATEGY: "winner-lock" });
  const quotes = [q("UP", 0.93), q("DOWN", 0.08)];
  const ctx = { cfg, position: null, quotes };
  assert.equal(winnerLock.act({ ...ctx, secIn: 200, secLeft: 100, pUp: 0.99 }), null); // too early
  assert.equal(winnerLock.act({ ...ctx, secIn: 260, secLeft: 40, pUp: 0.93 }), null); // model doesn't agree
  const a = winnerLock.act({ ...ctx, secIn: 260, secLeft: 40, pUp: 0.99 });
  assert.equal(a?.kind, "buy");
  assert.equal(a?.side, "UP");
  assert.equal(winnerLock.act({ ...ctx, quotes: [q("UP", 0.98)], secIn: 260, secLeft: 40, pUp: 0.99 }), null);
});

test("replayLedger rebuilds clips, scratches and settles", () => {
  const base = { mode: "paper" as const, slug: "s", tokenId: "U", side: "UP" as const, modelProb: 0.6, ts: Date.now() };
  const entries = [
    { ...base, kind: "entry" as const, slotStart: 1, price: 0.5, shares: 10, costUsd: 5, edge: 0.05 },
    { ...base, kind: "entry" as const, slotStart: 1, price: 0.5, shares: 10, costUsd: 5, edge: 0.05 },
    { ...base, kind: "entry" as const, slotStart: 2, price: 0.5, shares: 10, costUsd: 5, edge: 0.05 },
    { ...base, kind: "exit" as const, slotStart: 2, price: 0.5, shares: 10, proceedsUsd: 5, costUsd: 5, pnlUsd: 0, reason: "x" },
  ];
  const r = replayLedger(entries, "paper", Date.now());
  assert.equal(r.positions.size, 1);
  assert.equal(r.positions.get(1)?.shares, 20);
  assert.equal(r.positions.get(1)?.clips, 2);
  assert.equal(r.cashDeltaUsd, -10);
  assert.equal(replayLedger(entries, "live", Date.now()).positions.size, 0);
});

function engineHarness(env: Record<string, string>, books: Record<string, { asks: object[]; bids: object[] }>) {
  const dir = mkdtempSync(join(tmpdir(), "engine-"));
  const cfg = loadConfig({ STATE_DIR: dir, ...env });
  const clock = { nowMs: (SLOT + 120) * 1000 };
  const tape = new PriceTape();
  let resolved: "UP" | "DOWN" | null = null;
  const gamma = {
    market: async (s: number) => parseGammaMarket({ outcomes: '["Up","Down"]', clobTokenIds: '["U","D"]' }, s),
    resolution: async () => resolved,
  };
  const clob = { getOrderBook: async (id: string) => books[id] };
  const broker = new PaperBroker(100);
  const ledger = new Ledger(dir);
  const make = () =>
    new Engine({
      cfg, tape, gamma: gamma as never, clob: clob as never, broker, ledger,
      risk: new RiskManager(cfg, join(dir, "STOP"), () => clock.nowMs),
      now: () => clock.nowMs,
    });
  return { cfg, clock, tape, broker, ledger, make, resolve: (w: "UP" | "DOWN") => (resolved = w) };
}

function feed(tape: PriceTape, from: number, to: number, priceAt: (i: number) => number): void {
  for (let i = from; i <= to; i++) tape.push({ tsMs: (SLOT + i) * 1000, price: priceAt(i) + (i % 2) * 5 });
}

test("engine (fair-value): enters on edge, settles from resolution, restores after restart", async () => {
  const h = engineHarness({ STAKE_USD: "10" }, {
    U: { asks: [{ price: "0.60", size: "500" }], bids: [] },
    D: { asks: [{ price: "0.45", size: "500" }], bids: [] },
  });
  feed(h.tape, -300, 120, (i) => (i > 0 ? 100_100 : 100_000));
  const engine = h.make();
  await engine.tick();
  let entries = h.ledger.read();
  assert.equal(entries.length, 1);
  assert.equal(entries[0]!.kind, "entry");
  assert.equal(entries[0]!.side, "UP");
  assert.ok(Math.abs((await h.broker.bankrollUsd()) - 90.004) < 1e-9); // 16.66 shares * 0.60

  h.clock.nowMs += 5_000;
  await engine.tick(); // same slot: no second entry
  assert.equal(h.ledger.read().length, 1);

  // Restart before resolution: the position must be restored, not forgotten.
  h.clock.nowMs = (SLOT + 400) * 1000;
  const restarted = h.make();
  await restarted.tick();
  assert.equal(h.ledger.read().length, 1);
  h.resolve("UP");
  h.clock.nowMs += 20_000;
  await restarted.tick();
  entries = h.ledger.read();
  const settle = entries.find((e) => e.kind === "settle");
  assert.ok(settle && settle.kind === "settle");
  assert.equal(settle.winner, "UP");
  assert.ok(Math.abs(settle.pnlUsd - (16.66 - 9.996)) < 1e-6);

  const card = score(entries, "paper")!;
  assert.equal(card.trades, 1);
  assert.equal(card.wins, 1);
});

test("engine (twap-scratch): builds clips under the slot cap, then scratches and never re-enters", async () => {
  const books = {
    U: { asks: [{ price: "0.50", size: "500" }], bids: [{ price: "0.49", size: "500" }] },
    D: { asks: [{ price: "0.51", size: "500" }], bids: [{ price: "0.50", size: "500" }] },
  };
  const h = engineHarness(
    { STRATEGY: "twap-scratch", STAKE_USD: "5", MAX_TRADES_PER_SLOT: "3", MAX_SLOT_USD: "10", MIN_EDGE: "0.03" },
    books,
  );
  h.clock.nowMs = (SLOT + 40) * 1000;
  feed(h.tape, -300, 40, (i) => (i > 0 ? 100_060 : 100_000));
  const engine = h.make();

  for (let k = 0; k < 4; k++) {
    await engine.tick();
    h.clock.nowMs += 15_000;
    feed(h.tape, 41 + k * 15, 40 + (k + 1) * 15, () => 100_060);
  }
  let entries = h.ledger.read().filter((e) => e.kind === "entry");
  assert.equal(entries.length, 2, "two $5 clips, then the $10 slot cap stops it");

  // BTC drops back below the open: signal flips, position is scratched at the bid.
  const t = Math.floor(h.clock.nowMs / 1000) - SLOT;
  feed(h.tape, t - 60 + 1, t, () => 99_900);
  h.clock.nowMs += 15_000;
  feed(h.tape, t + 1, t + 15, () => 99_900);
  await engine.tick();
  const exit = h.ledger.read().find((e) => e.kind === "exit");
  assert.ok(exit && exit.kind === "exit", "expected a scratch exit");
  assert.equal(exit.price, 0.49);

  // Signal recovers, but the slot is closed for new entries.
  h.clock.nowMs += 15_000;
  await engine.tick();
  entries = h.ledger.read().filter((e) => e.kind === "entry");
  assert.equal(entries.length, 2);
  const card = score(h.ledger.read(), "paper", "twap-scratch")!;
  assert.equal(card.scratches, 1);
  assert.ok(card.pnlUsd < 0 && card.pnlUsd > -0.5, `scratch should cost ~1¢/share, got ${card.pnlUsd}`);
});
