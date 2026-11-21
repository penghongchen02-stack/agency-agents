/**
 * The decision loop. Each tick:
 *   1. settles positions from finished slots (using Polymarket's own resolution), then
 *   2. asks the configured strategy for at most one action (buy a clip, or scratch-sell),
 *      and executes it only if the risk manager allows.
 *
 * Rules enforced here, whatever the strategy says:
 *   - one side per slot (never hold Up and Down together),
 *   - no re-entry into a slot after a scratch exit,
 *   - no trading on a stale feed or an untrusted open price,
 *   - every buy goes through RiskManager.canEnter.
 */
import type { Broker } from "./broker.js";
import type { Config } from "./config.js";
import { log, replayLedger, warn, type Ledger, type Position } from "./log.js";
import { slotStartFor, type SlotMarket } from "./markets.js";
import { probUp } from "./model.js";
import type { PriceTape } from "./priceFeed.js";
import type { RiskManager } from "./risk.js";
import { strategyFor, type Action, type Strategy } from "./strategies.js";
import type { Venue } from "./venue.js";

const SETTLE_DELAY_SEC = 20;
const SETTLE_RETRY_MS = 15_000;
const MAX_TICK_AGE_MS = 10_000;

/**
 * The model's P(up) for a market at `nowMs`, from the price tape. Shared by the engine
 * and the backtest so both use exactly the same calculation.
 */
export function fairProbUp(
  tape: PriceTape,
  market: SlotMarket,
  openPrice: number,
  nowMs: number,
  cfg: Config,
  useTwap: boolean,
): number | null {
  const latest = tape.latest();
  const measuredVol = tape.volBpsPerSqrtSec();
  if (!latest || measuredVol === null) return null;
  const N = market.feedSmoothingSec;
  // A smoothed feed (US) is already an average, so a TWAP on top would only add lag.
  const price = useTwap && N === 0 ? (tape.twap(cfg.twapWindowSec * 1000) ?? latest.price) : latest.price;
  // For a smoothed feed the measured 1s volatility is σ_raw/√N; scale it back up.
  const rawVol = N > 0 ? measuredVol * Math.sqrt(N) : measuredVol;
  const settleAtSec = market.slotEnd - (N > 0 ? 1 : 0);
  return probUp({
    openPrice,
    currentPrice: price,
    secondsLeft: settleAtSec - nowMs / 1000,
    volBpsPerSqrtSec: Math.max(rawVol, cfg.minVolBpsPerSqrtSec),
    smoothSec: N,
    slopePerSec: N > 0 ? (tape.slopePerSec(10_000) ?? 0) : 0,
  });
}

export interface EngineDeps {
  cfg: Config;
  tape: PriceTape;
  venue: Venue;
  broker: Broker;
  risk: RiskManager;
  ledger: Ledger;
  strategy?: Strategy;
  now?: () => number; // ms
}

export class Engine {
  private readonly positions: Map<number, Position>;
  private readonly lastSettleCheck = new Map<number, number>();
  private readonly markets = new Map<number, { market: SlotMarket | null; fetchedMs: number }>();
  private readonly closedSlots = new Set<number>(); // slots we will not enter again
  private readonly lastEval = new Map<number, number>();
  private busy = false;
  private lastStatusMs = 0;
  private readonly now: () => number;
  readonly strategy: Strategy;

  constructor(private readonly d: EngineDeps) {
    this.now = d.now ?? Date.now;
    this.strategy = d.strategy ?? strategyFor(d.cfg.strategy);
    const replay = replayLedger(d.ledger.read(), d.cfg.mode, this.now());
    this.positions = replay.positions;
    for (const e of replay.today.entries) d.risk.recordEntry(e.slotStart, e.costUsd);
    for (const c of replay.today.closes) d.risk.recordClose(c.costUsd, c.pnlUsd);
    for (const e of d.ledger.read()) if (e.kind === "exit") this.closedSlots.add(e.slotStart);
    if (this.positions.size) log(`restored ${this.positions.size} open position(s) from ledger`);
  }

  async tick(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      await this.settle();
      await this.evaluate();
      this.status();
    } catch (err) {
      warn("tick failed", err);
    } finally {
      this.busy = false;
    }
  }

  private async settle(): Promise<void> {
    const nowMs = this.now();
    for (const pos of [...this.positions.values()]) {
      if (nowMs / 1000 < pos.slotEnd + SETTLE_DELAY_SEC) continue;
      if (nowMs - (this.lastSettleCheck.get(pos.slotStart) ?? 0) < SETTLE_RETRY_MS) continue;
      this.lastSettleCheck.set(pos.slotStart, nowMs);
      const winner = await this.d.venue.resolution(pos.slotStart);
      if (!winner) continue;

      const payoutUsd = pos.side === winner ? pos.shares : 0;
      const pnlUsd = payoutUsd - pos.costUsd;
      this.d.broker.credit(payoutUsd);
      this.d.risk.recordClose(pos.costUsd, pnlUsd);
      this.d.ledger.append({
        kind: "settle",
        ts: nowMs,
        mode: this.d.broker.mode,
        strategy: this.strategy.name,
        slug: pos.slug,
        slotStart: pos.slotStart,
        slotEnd: pos.slotEnd,
        side: pos.side,
        winner,
        shares: pos.shares,
        costUsd: pos.costUsd,
        payoutUsd,
        pnlUsd,
        modelProb: pos.modelProb,
      });
      this.positions.delete(pos.slotStart);
      log(`SETTLED ${pos.slug} held=${pos.side} winner=${winner} pnl=$${pnlUsd.toFixed(2)}`);
    }
  }

  private async marketFor(slotStart: number): Promise<SlotMarket | null> {
    const cached = this.markets.get(slotStart);
    if (cached && (cached.market || this.now() - cached.fetchedMs < 10_000)) return cached.market;
    const market = await this.d.venue.market(slotStart);
    this.markets.set(slotStart, { market, fetchedMs: this.now() });
    for (const key of this.markets.keys()) if (key < slotStart - 3600) this.markets.delete(key);
    return market;
  }

  private skip(slotStart: number, reason: string): void {
    if (this.closedSlots.has(slotStart)) return;
    this.closedSlots.add(slotStart);
    log(`skip slot ${slotStart}: ${reason}`);
  }

  private async evaluate(): Promise<void> {
    const { cfg, tape } = this.d;
    const s = this.strategy;
    const nowMs = this.now();
    const slotStart = slotStartFor(nowMs / 1000, cfg.slotSeconds);
    const secIn = nowMs / 1000 - slotStart;
    const secLeft = cfg.slotSeconds - secIn;
    const position = this.positions.get(slotStart) ?? null;

    const [winStart, winEnd] = s.entryWindow(cfg);
    const canBuy = secIn >= winStart && secIn <= winEnd && !this.closedSlots.has(slotStart);
    const canSell = !!position && s.exits && secLeft > 5;
    if (!canBuy && !canSell) return;

    const last = this.lastEval.get(slotStart) ?? 0;
    if (nowMs - last < s.evalEveryMs(cfg)) return;

    const latest = tape.latest();
    if (!latest || nowMs - latest.tsMs > MAX_TICK_AGE_MS) return; // stale feed: wait, don't guess
    if (tape.volBpsPerSqrtSec() === null) return;
    const market = await this.marketFor(slotStart);
    if (!market) return;
    // Polymarket US publishes the official open (priceToBeat); otherwise we must have seen it.
    const openPrice = market.priceToBeat ?? tape.openPrice(slotStart);
    if (openPrice === undefined || openPrice === null || !(openPrice > 0)) {
      if (!position) this.skip(slotStart, "no trustworthy open price (joined mid-slot?)");
      return;
    }

    this.lastEval.set(slotStart, nowMs);
    for (const k of this.lastEval.keys()) if (k < slotStart) this.lastEval.delete(k);

    const pUp = fairProbUp(tape, market, openPrice, nowMs, cfg, s.useTwap);
    if (pUp === null) return;
    const quotes = await this.d.venue.quotes(market);

    const action = s.act({ cfg, secIn, secLeft, pUp, quotes, position });
    if (!action) return;
    const quote = quotes.find((q) => q.side === action.side)!;
    if (action.kind === "buy") {
      if (!canBuy || (position && position.side !== action.side)) return;
      await this.buy(market, action, quote, position);
    } else if (canSell && position) {
      await this.sell(market, action, quote, position);
    }
  }

  private async buy(
    market: SlotMarket,
    a: Extract<Action, { kind: "buy" }>,
    quote: Parameters<Broker["buy"]>[3],
    position: Position | null,
  ): Promise<void> {
    const { risk, broker } = this.d;
    const verdict = risk.canEnter(market.slotStart, await broker.bankrollUsd(), a.usd);
    if (!verdict.ok) {
      if (!position) this.skip(market.slotStart, verdict.reason);
      return;
    }
    const fill = await broker.buy(market, a, a.usd, quote);
    if (!fill) return;
    risk.recordEntry(market.slotStart, fill.costUsd);
    if (position) {
      position.shares += fill.shares;
      position.costUsd += fill.costUsd;
      position.clips += 1;
    } else {
      this.positions.set(market.slotStart, {
        slug: market.slug,
        slotStart: market.slotStart,
        slotEnd: market.slotEnd,
        side: a.side,
        tokenId: a.tokenId,
        shares: fill.shares,
        costUsd: fill.costUsd,
        modelProb: a.modelProb,
        clips: 1,
      });
    }
    this.d.ledger.append({
      kind: "entry",
      ts: this.now(),
      mode: broker.mode,
      strategy: this.strategy.name,
      slug: market.slug,
      slotStart: market.slotStart,
      slotEnd: market.slotEnd,
      side: a.side,
      tokenId: a.tokenId,
      price: fill.price,
      shares: fill.shares,
      costUsd: fill.costUsd,
      modelProb: a.modelProb,
      edge: a.edge,
      orderId: fill.orderId,
    });
    log(
      `${broker.mode.toUpperCase()} BUY ${a.side} ${market.slug} ` +
        `${fill.shares} @ ${fill.price.toFixed(3)} ($${fill.costUsd.toFixed(2)}) ` +
        `model=${a.modelProb.toFixed(3)} edge=${a.edge.toFixed(3)} [${this.strategy.name}]`,
    );
  }

  private async sell(
    market: SlotMarket,
    a: Extract<Action, { kind: "sell" }>,
    quote: Parameters<Broker["sell"]>[1],
    position: Position,
  ): Promise<void> {
    const shares = Math.min(a.shares, position.shares);
    const fill = await this.d.broker.sell(
      { side: position.side, marketSlug: market.slug, tokenId: position.tokenId, shares, price: a.price },
      quote,
    );
    if (!fill) return;
    const basis = position.costUsd * (fill.shares / position.shares);
    const pnlUsd = fill.proceedsUsd - basis;
    position.shares -= fill.shares;
    position.costUsd -= basis;
    if (position.shares <= 1e-9) this.positions.delete(market.slotStart);
    this.closedSlots.add(market.slotStart);
    this.d.risk.recordClose(basis, pnlUsd);
    this.d.ledger.append({
      kind: "exit",
      ts: this.now(),
      mode: this.d.broker.mode,
      strategy: this.strategy.name,
      slug: market.slug,
      slotStart: market.slotStart,
      slotEnd: market.slotEnd,
      side: position.side,
      tokenId: position.tokenId,
      price: fill.price,
      shares: fill.shares,
      proceedsUsd: fill.proceedsUsd,
      costUsd: basis,
      pnlUsd,
      modelProb: a.modelProb,
      reason: a.reason,
      orderId: fill.orderId,
    });
    log(
      `${this.d.broker.mode.toUpperCase()} SCRATCH ${position.side} ${market.slug} ` +
        `${fill.shares} @ ${fill.price.toFixed(3)} pnl=$${pnlUsd.toFixed(2)} (${a.reason})`,
    );
  }

  private status(): void {
    const nowMs = this.now();
    if (nowMs - this.lastStatusMs < 60_000) return;
    this.lastStatusMs = nowMs;
    const latest = this.d.tape.latest();
    log("status", {
      strategy: this.strategy.name,
      btc: latest?.price ?? null,
      volBps: this.d.tape.volBpsPerSqrtSec()?.toFixed(2) ?? null,
      openPositions: this.positions.size,
      ...this.d.risk.snapshot(),
    });
  }
}
