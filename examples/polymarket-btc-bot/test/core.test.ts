import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { PaperBroker } from "../src/broker.js";
import { LIVE_CONFIRM_PHRASE, describeConfig, loadConfig } from "../src/config.js";
import { Engine } from "../src/engine.js";
import { Ledger, redact } from "../src/log.js";
import { parseGammaMarket, parseResolution, slotStartFor, slugFor } from "../src/markets.js";
import { decide, normCdf, probUp } from "../src/model.js";
import { PriceTape } from "../src/priceFeed.js";
import { score } from "../src/report.js";
import { RiskManager } from "../src/risk.js";

const FAKE_KEY = "0x" + "ab".repeat(32);

test("slot math", () => {
  assert.equal(slotStartFor(1_800_000_123), 1_800_000_000);
  assert.equal(slugFor(1_800_000_000), "btc-updown-5m-1800000000");
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

test("decide: needs edge after fees and respects price band", () => {
  const params = { minEdge: 0.05, feeBuffer: 0.02, minEntryPrice: 0.2, maxEntryPrice: 0.8 };
  const quotes = [
    { side: "UP" as const, tokenId: "u", bestAsk: 0.6, askSize: 100 },
    { side: "DOWN" as const, tokenId: "d", bestAsk: 0.42, askSize: 100 },
  ];
  assert.equal(decide({ ...params, pUp: 0.65, quotes }), null); // 0.65-0.60-0.02 = 0.03 < 0.05
  const d = decide({ ...params, pUp: 0.7, quotes });
  assert.equal(d?.side, "UP");
  assert.ok(Math.abs(d!.edge - 0.08) < 1e-9);
  assert.equal(decide({ ...params, pUp: 0.95, quotes: [{ ...quotes[0]!, bestAsk: 0.85 }] }), null);
  assert.equal(decide({ ...params, pUp: 0.7, quotes: [{ ...quotes[0]!, bestAsk: null }] }), null);
});

test("PriceTape: open price only trusted near the boundary; vol is computed", () => {
  const tape = new PriceTape();
  const slot = 1_800_000_000;
  tape.push({ tsMs: slot * 1000 + 12_000, price: 100_000 });
  assert.equal(tape.openPrice(slot), null); // first tick 12s late: untrusted

  const t2 = new PriceTape();
  for (let i = -60; i <= 60; i++) t2.push({ tsMs: (slot + i) * 1000, price: 100_000 + (i % 2) * 10 });
  assert.equal(t2.openPrice(slot), 100_000);
  const vol = t2.volBpsPerSqrtSec();
  assert.ok(vol !== null && vol > 0.5 && vol < 2, `vol=${vol}`);
});

test("config: paper by default, live demands confirmation and valid key", () => {
  assert.equal(loadConfig({}).mode, "paper");
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
    1_800_000_000,
  );
  assert.equal(m.upTokenId, "111");
  assert.equal(m.downTokenId, "222");
  assert.equal(parseResolution({ closed: false, outcomes: '["Up","Down"]', outcomePrices: '["1","0"]' }), null);
  assert.equal(parseResolution({ closed: true, outcomes: '["Up","Down"]', outcomePrices: '["0","1"]' }), "DOWN");
});

test("risk: per-slot cap, daily loss limit counts open exposure, STOP file", () => {
  const dir = mkdtempSync(join(tmpdir(), "risk-"));
  const stop = join(dir, "STOP");
  const r = new RiskManager({ stakeUsd: 10, maxTradesPerSlot: 1, maxDailyLossUsd: 25, maxDailyTrades: 99 }, stop);
  assert.deepEqual(r.canEnter(1, 100), { ok: true });
  r.recordEntry(1, 10);
  assert.equal(r.canEnter(1, 100).ok, false); // same slot
  r.recordEntry(2, 10); // exposure 20, next stake would make worst case -30
  assert.equal(r.canEnter(3, 100).ok, false);
  r.recordSettle(10, 9); // one win
  assert.equal(r.canEnter(3, 100).ok, true);
  writeFileSync(stop, "");
  assert.deepEqual(r.canEnter(4, 100), { ok: false, reason: "STOP file present" });
});

test("engine: enters on edge in paper mode, settles from resolution, restores after restart", async () => {
  const dir = mkdtempSync(join(tmpdir(), "engine-"));
  const cfg = loadConfig({ STATE_DIR: dir, STAKE_USD: "10" });
  const slot = 1_800_000_000;
  let nowMs = (slot + 120) * 1000;

  const tape = new PriceTape();
  for (let i = -300; i <= 120; i++) {
    // gentle noise, then BTC up 0.1% since open
    const drift = i > 0 ? 100 : 0;
    tape.push({ tsMs: (slot + i) * 1000, price: 100_000 + drift + (i % 2) * 5 });
  }

  let resolved: "UP" | "DOWN" | null = null;
  const gamma = {
    market: async (s: number) =>
      parseGammaMarket({ outcomes: '["Up","Down"]', clobTokenIds: '["U","D"]' }, s),
    resolution: async () => resolved,
  };
  const books: Record<string, { asks: { price: string; size: string }[] }> = {
    U: { asks: [{ price: "0.60", size: "500" }] },
    D: { asks: [{ price: "0.45", size: "500" }] },
  };
  const clob = { getOrderBook: async (id: string) => books[id] };
  const broker = new PaperBroker(100);
  const ledger = new Ledger(dir);
  const deps = {
    cfg,
    tape,
    gamma: gamma as never,
    clob: clob as never,
    broker,
    ledger,
    now: () => nowMs,
  };

  const engine = new Engine({ ...deps, risk: new RiskManager(cfg, join(dir, "STOP"), () => nowMs) });
  await engine.tick();
  let entries = ledger.read();
  assert.equal(entries.length, 1);
  assert.equal(entries[0]!.kind, "entry");
  assert.equal((entries[0] as { side: string }).side, "UP");
  assert.ok(Math.abs((await broker.bankrollUsd()) - 90.004) < 1e-9); // 16.66 shares * 0.60

  await engine.tick(); // same slot: no second entry
  assert.equal(ledger.read().length, 1);

  // Restart before resolution: the position must be restored, not forgotten.
  nowMs = (slot + 400) * 1000;
  const restarted = new Engine({ ...deps, risk: new RiskManager(cfg, join(dir, "STOP"), () => nowMs) });
  await restarted.tick(); // unresolved yet
  assert.equal(ledger.read().length, 1);
  resolved = "UP";
  nowMs += 20_000;
  await restarted.tick();
  entries = ledger.read();
  const settle = entries.find((e) => e.kind === "settle");
  assert.ok(settle && settle.kind === "settle");
  assert.equal(settle.winner, "UP");
  assert.ok(Math.abs(settle.pnlUsd - (16.66 - 9.996)) < 1e-6);

  const card = score(entries, "paper")!;
  assert.equal(card.trades, 1);
  assert.equal(card.wins, 1);
});
