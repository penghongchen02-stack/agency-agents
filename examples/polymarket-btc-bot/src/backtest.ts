/**
 * `npm run backtest -- --slots 1000`
 *
 * Replays the last N real Polymarket US BTC Up/Down markets through the REAL engine,
 * strategies, risk manager, paper broker (with US taker fees) and ledger.
 *
 * Real data used (all public, from gateway.polymarket.us):
 *  - every market's official priceToBeat, settlement and winner,
 *  - the BRTI feed the markets settle on, second by second,
 *  - the market's own displayed YES/NO prices (about one point per minute).
 *
 * What is NOT real, and how we stay conservative about it:
 *  - Historical order books aren't published. We build a book around the displayed
 *    price with HALF_SPREAD (default 1¢) on each side, so every trade pays a spread.
 *  - Prices are only known once a minute, so the bot can only act on those minutes.
 *    A history point stamped t is the price at the end of its minute (t+59s); we use that.
 *    It sees the BRTI feed LAG_SEC (default 2s) late, so it never sees "the future".
 *  - Fills assume enough size at the quoted price (fine at small stakes).
 * Treat a good result as "worth paper trading live", never as proof of profit.
 */
import { mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { PaperBroker } from "./broker.js";
import { WINDOW_SECONDS, loadConfig, loadDotEnv, type Config, type MarketWindow, type StrategyName } from "./config.js";
import { Engine, fairProbUp } from "./engine.js";
import { Ledger, setQuiet, type LedgerEntry } from "./log.js";
import { slotStartFor, type SlotMarket, type Winner } from "./markets.js";
import type { Quote } from "./model.js";
import { PriceTape } from "./priceFeed.js";
import { score } from "./report.js";
import { RiskManager } from "./risk.js";
import { strategyFor } from "./strategies.js";
import { US_FEED_SMOOTHING_SEC, UsGateway, parseUsResolution, usSlugFor } from "./usVenue.js";
import type { Venue } from "./venue.js";

/** Seconds to add to a price-history stamp to get the time the price was observed. */
export const POINT_TIME_OFFSET_SEC = 59;

export interface SlotData {
  slotStart: number;
  slug: string;
  priceToBeat: number;
  settlement: number;
  winner: Winner;
  points: { t: number; long: number; short: number }[];
}

export interface Dataset {
  window: MarketWindow;
  slots: SlotData[];
  brti: [number, number][]; // [unix sec, price]
}

// ── data download (cached) ────────────────────────────────────────────────────

async function pool<T, R>(items: T[], limit: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  await Promise.all(
    Array.from({ length: limit }, async () => {
      while (next < items.length) {
        const i = next++;
        out[i] = await fn(items[i]!);
        await new Promise((r) => setTimeout(r, 100)); // stay well under 25 req/s
      }
    }),
  );
  return out;
}

export async function fetchDataset(gw: UsGateway, window: MarketWindow, n: number): Promise<Dataset> {
  const len = WINDOW_SECONDS[window];
  const last = slotStartFor(Date.now() / 1000 - 3 * len - 120, len); // surely resolved
  const want = Math.ceil(n * 1.05) + 5; // a few windows are skipped for exchange maintenance
  const starts = Array.from({ length: want }, (_, i) => last - (want - 1 - i) * len);
  let done = 0;
  const rows = await pool(starts, 4, async (s): Promise<SlotData | null> => {
    const slug = usSlugFor(s, window);
    const m = await gw.marketBySlug(slug);
    if (++done % 100 === 0) process.stderr.write(`  markets ${done}/${starts.length}\n`);
    if (!m) return null;
    const winner = parseUsResolution(m);
    const terms = (m.assetPriceTerms ?? {}) as { priceToBeat?: { value: string }; settlementPrice?: { value: string } };
    if (!winner || !terms.priceToBeat || !terms.settlementPrice) return null;
    // A point stamped t is the price at the END of its minute bucket: checked by matching
    // against the BRTI-driven model (best agreement at +59s, far worse at +0s). Using the
    // raw stamp would let the "market" see up to a minute into the future.
    const points = (await gw.priceHistory(slug, s - 60, s + len)).map((p) => ({ ...p, t: p.t + POINT_TIME_OFFSET_SEC }));
    return {
      slotStart: s,
      slug,
      priceToBeat: Number(terms.priceToBeat.value),
      settlement: Number(terms.settlementPrice.value),
      winner,
      points: points.filter((p) => p.t >= s && p.t < s + len).sort((a, b) => a.t - b.t),
    };
  });
  const slots = rows.filter((r): r is SlotData => r !== null && r.points.length > 0).slice(-n);
  if (!slots.length) throw new Error("no resolved markets found");

  const from = slots[0]!.slotStart - 600;
  const to = slots[slots.length - 1]!.slotStart + len + 5;
  const brti: [number, number][] = [];
  const chunks: number[] = [];
  for (let t = from; t < to; t += 3500) chunks.push(t);
  process.stderr.write(`  BRTI: ${chunks.length} hour-chunks of 1-second data\n`);
  const parts = await pool(chunks, 3, (t) => gw.brti(t, Math.min(t + 3499, to)));
  const seen = new Set<number>();
  for (const part of parts)
    for (const tick of part) {
      const sec = tick.tsMs / 1000;
      if (!seen.has(sec)) {
        seen.add(sec);
        brti.push([sec, tick.price]);
      }
    }
  brti.sort((a, b) => a[0] - b[0]);
  return { window, slots, brti };
}

// ── replay ────────────────────────────────────────────────────────────────────

export interface ReplayOptions {
  halfSpread: number;
  lagSec: number;
  bankrollUsd: number;
}

class Clock {
  ms = 0;
}

/** Venue backed by recorded data, answering as of the replay clock. */
class ReplayVenue implements Venue {
  readonly name = "replay";
  private readonly bySlot = new Map<number, SlotData>();
  constructor(
    ds: Dataset,
    private readonly clock: Clock,
    private readonly halfSpread: number,
  ) {
    for (const s of ds.slots) this.bySlot.set(s.slotStart, s);
    this.len = WINDOW_SECONDS[ds.window];
  }
  private readonly len: number;

  async market(slotStart: number): Promise<SlotMarket | null> {
    const s = this.bySlot.get(slotStart);
    if (!s || this.clock.ms < slotStart * 1000 || this.clock.ms >= (slotStart + this.len) * 1000) return null;
    return {
      slug: s.slug,
      question: s.slug,
      slotStart,
      slotEnd: slotStart + this.len,
      upTokenId: `${s.slug}:YES`,
      downTokenId: `${s.slug}:NO`,
      priceToBeat: s.priceToBeat,
      feedSmoothingSec: US_FEED_SMOOTHING_SEC,
    };
  }

  async resolution(slotStart: number): Promise<Winner | null> {
    const s = this.bySlot.get(slotStart);
    return s && this.clock.ms >= (slotStart + this.len + 20) * 1000 ? s.winner : null;
  }

  async quotes(m: SlotMarket): Promise<Quote[]> {
    const s = this.bySlot.get(m.slotStart)!;
    const p = [...s.points].reverse().find((x) => x.t * 1000 <= this.clock.ms);
    return syntheticQuotes(m.slug, p ?? null, this.halfSpread);
  }
}

/** A conservative book around the displayed price: every trade pays `halfSpread`. */
export function syntheticQuotes(
  slug: string,
  p: { long: number; short: number } | null,
  halfSpread: number,
  size = 200,
): Quote[] {
  if (!p) {
    return [
      { side: "UP", tokenId: `${slug}:YES`, bestAsk: null, askSize: 0, bestBid: null, bidSize: 0 },
      { side: "DOWN", tokenId: `${slug}:NO`, bestAsk: null, askSize: 0, bestBid: null, bidSize: 0 },
    ];
  }
  const cent = (x: number) => Math.round(x * 100) / 100;
  const mid = Math.min(0.99, Math.max(0.01, (p.long + (1 - p.short)) / 2));
  const askUp = Math.min(0.99, cent(Math.ceil((mid + halfSpread) * 100 - 1e-9) / 100));
  const bidUp = Math.max(0.01, cent(Math.floor((mid - halfSpread) * 100 + 1e-9) / 100));
  return [
    { side: "UP", tokenId: `${slug}:YES`, bestAsk: askUp, askSize: size, bestBid: bidUp, bidSize: size },
    { side: "DOWN", tokenId: `${slug}:NO`, bestAsk: cent(1 - bidUp), askSize: size, bestBid: cent(1 - askUp), bidSize: size },
  ];
}

export interface StrategyResult {
  strategy: StrategyName;
  card: ReturnType<typeof score>;
  finalBankroll: number;
  maxDrawdownUsd: number;
  entries: number;
}

export interface Calibration {
  points: number;
  brierModel: number;
  brierMarket: number;
}

/** Model vs market on every decision point, with no trading involved. */
export function calibrate(ds: Dataset, cfg: Config, lagSec: number): Calibration {
  const len = WINDOW_SECONDS[ds.window];
  const tape = new PriceTape(30 * 60_000);
  let i = 0;
  let n = 0, bm = 0, bk = 0;
  for (const s of ds.slots) {
    const market: SlotMarket = {
      slug: s.slug, question: s.slug, slotStart: s.slotStart, slotEnd: s.slotStart + len,
      upTokenId: "", downTokenId: "", priceToBeat: s.priceToBeat, feedSmoothingSec: US_FEED_SMOOTHING_SEC,
    };
    const won = s.winner === "UP" ? 1 : 0;
    for (const p of s.points) {
      while (i < ds.brti.length && ds.brti[i]![0] <= p.t - lagSec) {
        tape.push({ tsMs: ds.brti[i]![0] * 1000, price: ds.brti[i]![1] });
        i++;
      }
      if (p.t - s.slotStart < 30) continue; // opening minute: book is still forming
      if (p.t > s.slotStart + len - 3) continue; // effectively settled; not a forecast
      const pm = fairProbUp(tape, market, s.priceToBeat, p.t * 1000, cfg, false);
      if (pm === null) continue;
      const mid = Math.min(0.99, Math.max(0.01, (p.long + (1 - p.short)) / 2));
      bm += (pm - won) ** 2;
      bk += (mid - won) ** 2;
      n++;
    }
  }
  return { points: n, brierModel: n ? bm / n : NaN, brierMarket: n ? bk / n : NaN };
}

export async function replay(
  ds: Dataset,
  baseCfg: Config,
  strategy: StrategyName,
  opts: ReplayOptions,
  stateDir: string,
): Promise<StrategyResult> {
  rmSync(stateDir, { recursive: true, force: true });
  const cfg: Config = { ...baseCfg, strategy, stateDir, mode: "paper" };
  const len = WINDOW_SECONDS[ds.window];
  const clock = new Clock();
  const tape = new PriceTape(30 * 60_000);
  const broker = new PaperBroker(opts.bankrollUsd, cfg.feeTheta);
  const ledger = new Ledger(stateDir);
  const engine = new Engine({
    cfg,
    tape,
    venue: new ReplayVenue(ds, clock, opts.halfSpread),
    broker,
    ledger,
    risk: new RiskManager(cfg, join(stateDir, "STOP-never"), () => clock.ms),
    strategy: strategyFor(strategy),
    now: () => clock.ms,
  });

  let i = 0;
  const feedTo = (sec: number) => {
    while (i < ds.brti.length && ds.brti[i]![0] <= sec - opts.lagSec) {
      tape.push({ tsMs: ds.brti[i]![0] * 1000, price: ds.brti[i]![1] });
      i++;
    }
  };
  for (const s of ds.slots) {
    // decision points: the minutes at which the market's real price is known
    for (const p of s.points) {
      if (p.t > s.slotStart + len - 3) continue;
      feedTo(p.t);
      clock.ms = p.t * 1000;
      await engine.tick();
    }
    // settlement check after the window closes
    feedTo(s.slotStart + len + 25);
    clock.ms = (s.slotStart + len + 25) * 1000;
    await engine.tick();
  }
  clock.ms += 60_000;
  await engine.tick();

  const entries = ledger.read();
  let equity = 0, peak = 0, maxDd = 0;
  for (const e of entries) {
    if (e.kind === "entry") continue;
    equity += e.pnlUsd;
    peak = Math.max(peak, equity);
    maxDd = Math.max(maxDd, peak - equity);
  }
  return {
    strategy,
    card: score(entries as LedgerEntry[], "paper", strategy),
    finalBankroll: await broker.bankrollUsd(),
    maxDrawdownUsd: maxDd,
    entries: entries.filter((e) => e.kind === "entry").length,
  };
}

// ── CLI ───────────────────────────────────────────────────────────────────────

function arg(name: string, fallback: string): string {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1]! : fallback;
}

async function main(): Promise<void> {
  loadDotEnv();
  const cfg = loadConfig({ ...process.env, MODE: "paper", VENUE: "us" });
  const slots = Number(arg("slots", "1000"));
  const window = arg("window", cfg.marketWindow) as MarketWindow;
  const opts: ReplayOptions = {
    halfSpread: Number(arg("half-spread", "0.01")),
    lagSec: Number(arg("lag", "2")),
    bankrollUsd: Number(arg("bankroll", String(cfg.paperBankrollUsd))),
  };
  const strategies = arg("strategies", "fair-value,twap-scratch,winner-lock").split(",") as StrategyName[];
  const base = join(cfg.stateDir, "backtest");
  mkdirSync(base, { recursive: true });
  const cacheFile = join(base, `dataset-us-${window}-${slots}.json`);

  let ds: Dataset;
  const fresh = process.argv.includes("--refresh");
  if (!fresh && existsSync(cacheFile)) {
    ds = JSON.parse(readFileSync(cacheFile, "utf8")) as Dataset;
    process.stderr.write(`using cached dataset ${cacheFile} (pass --refresh to re-download)\n`);
  } else {
    process.stderr.write(`downloading ${slots} resolved Polymarket US BTC ${window} markets...\n`);
    ds = await fetchDataset(new UsGateway(cfg.usGatewayHost), window, slots);
    writeFileSync(cacheFile, JSON.stringify(ds));
  }

  setQuiet(true);
  const first = new Date(ds.slots[0]!.slotStart * 1000).toISOString();
  const last = new Date(ds.slots[ds.slots.length - 1]!.slotStart * 1000).toISOString();
  const ups = ds.slots.filter((s) => s.winner === "UP").length;
  console.log(`\nPolymarket US BTC ${window} backtest: ${ds.slots.length} real markets, ${first} → ${last}`);
  console.log(`Up won ${ups} (${((ups / ds.slots.length) * 100).toFixed(1)}%), Down won ${ds.slots.length - ups}`);
  console.log(
    `Assumptions: book = displayed price ±${opts.halfSpread}, feed lag ${opts.lagSec}s, ` +
      `taker fee θ=${cfg.feeTheta} (no rebates), stake $${cfg.stakeUsd}, bankroll $${opts.bankrollUsd}, ` +
      `daily loss limit $${cfg.maxDailyLossUsd}`,
  );

  const cal = calibrate(ds, cfg, opts.lagSec);
  console.log(
    `\nModel vs market on ${cal.points} decision points (lower Brier = better forecasts):` +
      `\n  model  ${cal.brierModel.toFixed(4)}\n  market ${cal.brierMarket.toFixed(4)}` +
      (cal.brierModel < cal.brierMarket ? "  → model beat the market's own prices" : "  → market was better calibrated than the model"),
  );

  console.log("\nstrategy       buys  held  wins  scratches   staked      P&L     ROI   max DD  bankroll");
  for (const st of strategies) {
    const r = await replay(ds, cfg, st, opts, join(base, st));
    const c = r.card;
    const row = c
      ? [
          st.padEnd(13),
          String(r.entries).padStart(5),
          String(c.trades).padStart(5),
          String(c.wins).padStart(5),
          String(c.scratches).padStart(10),
          `$${c.costUsd.toFixed(2)}`.padStart(9),
          `$${c.pnlUsd.toFixed(2)}`.padStart(9),
          `${(c.roi * 100).toFixed(1)}%`.padStart(7),
          `$${r.maxDrawdownUsd.toFixed(2)}`.padStart(8),
          `$${r.finalBankroll.toFixed(2)}`.padStart(9),
        ].join(" ")
      : `${st.padEnd(13)} no trades (never found enough edge after fees)`;
    console.log(row);
  }
  console.log(`\nLedgers: ${base}/<strategy>/ledger.jsonl  (inspect with STATE_DIR=${base}/<strategy> npm run report)`);
}

if (process.argv[1]?.endsWith("backtest.ts")) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
