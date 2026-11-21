/**
 * The decision loop. Each tick:
 *   1. settles positions from finished slots (using Polymarket's own resolution), then
 *   2. inside the entry window, prices the current slot and maybe buys one side.
 *
 * Positions are always held to resolution. There are no "scratch" trades, no
 * martingale and no averaging down.
 */
import type { ClobClient } from "@polymarket/clob-client-v2";
import { quoteFor, type Broker } from "./broker.js";
import type { Config } from "./config.js";
import { log, warn, type Ledger, type LedgerEntry } from "./log.js";
import { slotStartFor, type Gamma, type SlotMarket } from "./markets.js";
import { decide, probUp } from "./model.js";
import type { PriceTape } from "./priceFeed.js";
import type { RiskManager } from "./risk.js";

interface Position {
  slug: string;
  slotStart: number;
  side: "UP" | "DOWN";
  shares: number;
  costUsd: number;
  modelProb: number;
  lastCheckMs: number;
}

const SETTLE_DELAY_SEC = 20;
const SETTLE_RETRY_MS = 15_000;
const MAX_TICK_AGE_MS = 10_000;

export interface EngineDeps {
  cfg: Config;
  tape: PriceTape;
  gamma: Gamma;
  clob: ClobClient;
  broker: Broker;
  risk: RiskManager;
  ledger: Ledger;
  now?: () => number; // ms
}

export class Engine {
  private readonly open: Position[] = [];
  private readonly markets = new Map<number, { market: SlotMarket | null; fetchedMs: number }>();
  private readonly skipped = new Set<number>();
  private busy = false;
  private lastStatusMs = 0;
  private readonly now: () => number;

  constructor(private readonly d: EngineDeps) {
    this.now = d.now ?? Date.now;
    this.restore(d.ledger.read());
  }

  /** Rebuild open positions and today's risk counters from the ledger after a restart. */
  private restore(entries: LedgerEntry[]): void {
    const settled = new Set(
      entries.filter((e) => e.kind === "settle").map((e) => `${e.slug}:${e.side}`),
    );
    const today = new Date(this.now()).toISOString().slice(0, 10);
    for (const e of entries) {
      if (e.mode !== this.d.cfg.mode) continue;
      const isToday = new Date(e.ts).toISOString().slice(0, 10) === today;
      if (e.kind === "entry") {
        if (isToday) this.d.risk.recordEntry(e.slotStart, e.costUsd);
        if (!settled.has(`${e.slug}:${e.side}`)) {
          this.open.push({ ...e, lastCheckMs: 0 });
        }
      } else if (isToday) {
        this.d.risk.recordSettle(e.costUsd, e.pnlUsd);
      }
    }
    if (this.open.length) log(`restored ${this.open.length} unsettled position(s) from ledger`);
  }

  async tick(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      await this.settle();
      await this.maybeEnter();
      this.status();
    } catch (err) {
      warn("tick failed", err);
    } finally {
      this.busy = false;
    }
  }

  private async settle(): Promise<void> {
    const nowMs = this.now();
    for (const pos of [...this.open]) {
      if (nowMs / 1000 < pos.slotStart + 300 + SETTLE_DELAY_SEC) continue;
      if (nowMs - pos.lastCheckMs < SETTLE_RETRY_MS) continue;
      pos.lastCheckMs = nowMs;
      const winner = await this.d.gamma.resolution(pos.slotStart);
      if (!winner) continue;

      const payoutUsd = pos.side === winner ? pos.shares : 0;
      const pnlUsd = payoutUsd - pos.costUsd;
      this.d.broker.credit(payoutUsd);
      this.d.risk.recordSettle(pos.costUsd, pnlUsd);
      this.d.ledger.append({
        kind: "settle",
        ts: nowMs,
        mode: this.d.broker.mode,
        slug: pos.slug,
        slotStart: pos.slotStart,
        side: pos.side,
        winner,
        shares: pos.shares,
        costUsd: pos.costUsd,
        payoutUsd,
        pnlUsd,
        modelProb: pos.modelProb,
      });
      this.open.splice(this.open.indexOf(pos), 1);
      log(`SETTLED ${pos.slug} held=${pos.side} winner=${winner} pnl=$${pnlUsd.toFixed(2)}`);
    }
  }

  private async marketFor(slotStart: number): Promise<SlotMarket | null> {
    const cached = this.markets.get(slotStart);
    if (cached && (cached.market || this.now() - cached.fetchedMs < 10_000)) return cached.market;
    const market = await this.d.gamma.market(slotStart);
    this.markets.set(slotStart, { market, fetchedMs: this.now() });
    for (const key of this.markets.keys()) if (key < slotStart - 3600) this.markets.delete(key);
    return market;
  }

  private skip(slotStart: number, reason: string): void {
    if (this.skipped.has(slotStart)) return;
    this.skipped.add(slotStart);
    log(`skip slot ${slotStart}: ${reason}`);
  }

  private async maybeEnter(): Promise<void> {
    const { cfg, tape, risk, broker } = this.d;
    const nowMs = this.now();
    const slotStart = slotStartFor(nowMs / 1000);
    const secIn = nowMs / 1000 - slotStart;
    if (secIn < cfg.entryStartSec || secIn > cfg.entryEndSec) return;
    if (this.skipped.has(slotStart)) return;

    const verdict = risk.canEnter(slotStart, await broker.bankrollUsd());
    if (!verdict.ok) return this.skip(slotStart, verdict.reason);

    const openPrice = tape.openPrice(slotStart);
    if (openPrice === null) return this.skip(slotStart, "no trustworthy open price (joined mid-slot?)");

    const latest = tape.latest();
    if (!latest || nowMs - latest.tsMs > MAX_TICK_AGE_MS) return; // stale feed: wait, don't guess
    const measuredVol = tape.volBpsPerSqrtSec();
    if (measuredVol === null) return;

    const market = await this.marketFor(slotStart);
    if (!market) return;

    const pUp = probUp({
      openPrice,
      currentPrice: latest.price,
      secondsLeft: market.slotEnd - nowMs / 1000,
      volBpsPerSqrtSec: Math.max(measuredVol, cfg.minVolBpsPerSqrtSec),
    });

    const quotes = await Promise.all([
      quoteFor(this.d.clob, "UP", market.upTokenId),
      quoteFor(this.d.clob, "DOWN", market.downTokenId),
    ]);
    const decision = decide({
      pUp,
      quotes,
      minEdge: cfg.minEdge,
      feeBuffer: cfg.feeBuffer,
      minEntryPrice: cfg.minEntryPrice,
      maxEntryPrice: cfg.maxEntryPrice,
    });
    if (!decision) return;

    const quote = quotes.find((q) => q.side === decision.side)!;
    const fill = await broker.buy(market, decision, cfg.stakeUsd, quote);
    if (!fill) return;

    risk.recordEntry(slotStart, fill.costUsd);
    this.open.push({
      slug: market.slug,
      slotStart,
      side: decision.side,
      shares: fill.shares,
      costUsd: fill.costUsd,
      modelProb: decision.modelProb,
      lastCheckMs: 0,
    });
    this.d.ledger.append({
      kind: "entry",
      ts: nowMs,
      mode: broker.mode,
      slug: market.slug,
      slotStart,
      side: decision.side,
      tokenId: decision.tokenId,
      price: fill.price,
      shares: fill.shares,
      costUsd: fill.costUsd,
      modelProb: decision.modelProb,
      edge: decision.edge,
      orderId: fill.orderId,
    });
    log(
      `${broker.mode.toUpperCase()} BUY ${decision.side} ${market.slug} ` +
        `${fill.shares} @ ${fill.price.toFixed(3)} ($${fill.costUsd.toFixed(2)}) ` +
        `model=${decision.modelProb.toFixed(3)} edge=${decision.edge.toFixed(3)}`,
    );
  }

  private status(): void {
    const nowMs = this.now();
    if (nowMs - this.lastStatusMs < 60_000) return;
    this.lastStatusMs = nowMs;
    const latest = this.d.tape.latest();
    log("status", {
      btc: latest?.price ?? null,
      volBps: this.d.tape.volBpsPerSqrtSec()?.toFixed(2) ?? null,
      openPositions: this.open.length,
      ...this.d.risk.snapshot(),
    });
  }
}
