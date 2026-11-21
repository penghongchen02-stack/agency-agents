/**
 * BTC/USD price feed.
 *
 * Polymarket's 5-minute crypto markets settle on the Chainlink BTC/USD price,
 * and Polymarket streams that price on its public real-time data service (RTDS).
 * We subscribe with Polymarket's OFFICIAL client (@polymarket/real-time-data-client),
 * not a look-alike package.
 *
 * PriceTape is pure (no I/O) so its math is unit-testable.
 */
import { RealTimeDataClient, type Message } from "@polymarket/real-time-data-client";
import { log, warn } from "./log.js";
import type { Asset } from "./config.js";
import type { UsGateway } from "./usVenue.js";

export interface Tick {
  tsMs: number; // source timestamp
  price: number;
}

/** How close to the slot boundary a tick must be for us to trust it as the open price. */
export const OPEN_TOLERANCE_MS = 5_000;

export class PriceTape {
  private ticks: Tick[] = [];

  constructor(private readonly keepMs = 15 * 60_000) {}

  push(tick: Tick): void {
    if (!Number.isFinite(tick.price) || tick.price <= 0) return;
    const last = this.ticks[this.ticks.length - 1];
    if (last && tick.tsMs <= last.tsMs) return; // ignore out-of-order/duplicate
    this.ticks.push(tick);
    const cutoff = tick.tsMs - this.keepMs;
    while (this.ticks.length && this.ticks[0]!.tsMs < cutoff) this.ticks.shift();
  }

  latest(): Tick | null {
    return this.ticks[this.ticks.length - 1] ?? null;
  }

  /**
   * The price at the slot boundary: the first tick at or after it, accepted only
   * if it lands within OPEN_TOLERANCE_MS. Returns null when we can't be sure
   * (e.g. the bot started mid-slot), and in that case we skip the slot.
   */
  openPrice(slotStartSec: number): number | null {
    const boundary = slotStartSec * 1000;
    const tick = this.ticks.find((t) => t.tsMs >= boundary);
    if (!tick || tick.tsMs - boundary > OPEN_TOLERANCE_MS) return null;
    return tick.price;
  }

  /** Average change per second over the lookback (price units/second). */
  slopePerSec(lookbackMs = 10_000): number | null {
    const latest = this.latest();
    if (!latest) return null;
    const past = this.ticks.filter((t) => t.tsMs <= latest.tsMs - lookbackMs).pop();
    if (!past) return null;
    return (latest.price - past.price) / ((latest.tsMs - past.tsMs) / 1000);
  }

  /** Simple mean of tick prices with tsMs in [fromMs, toMs). Null if none. */
  mean(fromMs: number, toMs: number): number | null {
    let sum = 0;
    let n = 0;
    for (const t of this.ticks) {
      if (t.tsMs >= fromMs && t.tsMs < toMs) {
        sum += t.price;
        n++;
      }
    }
    return n ? sum / n : null;
  }

  /**
   * Time-weighted average price over the last `windowMs`, ending at the latest tick.
   * Each tick's price counts for as long as it was the current price. This smooths
   * single-tick noise; it is NOT claimed to be Polymarket's settlement rule.
   */
  twap(windowMs: number): number | null {
    const latest = this.latest();
    if (!latest) return null;
    const start = latest.tsMs - windowMs;
    let prev = this.ticks.filter((t) => t.tsMs <= start).pop();
    const inside = this.ticks.filter((t) => t.tsMs > start);
    let prevT = start;
    if (!prev) {
      prev = inside.shift();
      if (!prev) return latest.price;
      prevT = prev.tsMs;
    }
    const span = latest.tsMs - prevT;
    if (span <= 0) return latest.price;
    let area = 0;
    let prevP = prev.price;
    for (const t of inside) {
      area += prevP * (t.tsMs - prevT);
      prevT = t.tsMs;
      prevP = t.price;
    }
    return area / span;
  }

  /**
   * Realized volatility over the lookback, in basis points per sqrt(second).
   * Null if there isn't enough data.
   */
  volBpsPerSqrtSec(lookbackMs = 5 * 60_000): number | null {
    const latest = this.latest();
    if (!latest) return null;
    const window = this.ticks.filter((t) => t.tsMs >= latest.tsMs - lookbackMs);
    if (window.length < 10) return null;
    let sumSq = 0;
    for (let i = 1; i < window.length; i++) {
      const r = Math.log(window[i]!.price / window[i - 1]!.price);
      sumSq += r * r;
    }
    const elapsedSec = (window[window.length - 1]!.tsMs - window[0]!.tsMs) / 1000;
    if (elapsedSec < 30) return null;
    return Math.sqrt(sumSq / elapsedSec) * 10_000;
  }
}

/** Streams Chainlink BTC/USD from Polymarket RTDS into a PriceTape. */
export function startChainlinkFeed(tape: PriceTape): { stop: () => void } {
  const subscription = {
    subscriptions: [
      {
        topic: "crypto_prices_chainlink",
        type: "*",
        filters: JSON.stringify({ symbol: "btc/usd" }),
      },
    ],
  };

  const client = new RealTimeDataClient({
    autoReconnect: true,
    onConnect: (c) => {
      log("price feed connected (Chainlink BTC/USD via Polymarket RTDS)");
      c.subscribe(subscription);
    },
    onMessage: (_c, msg: Message) => {
      if (msg.topic !== "crypto_prices_chainlink") return;
      const p = msg.payload as { symbol?: string; timestamp?: number; value?: number | string };
      if (p.symbol && p.symbol.toLowerCase() !== "btc/usd") return;
      const price = Number(p.value);
      const tsMs = Number(p.timestamp ?? msg.timestamp);
      if (Number.isFinite(price) && Number.isFinite(tsMs)) tape.push({ tsMs, price });
    },
    onStatusChange: (s) => {
      if (s === "DISCONNECTED") warn("price feed disconnected, reconnecting");
    },
  });
  client.connect();
  return { stop: () => client.disconnect() };
}

/**
 * Polls CF Benchmarks BRTI (the index Polymarket US settles on) from Polymarket US's
 * public asset-prices endpoint, once a second. Only completed seconds are used.
 */
export function startBrtiFeed(tape: PriceTape, gw: UsGateway, asset: Asset = "btc", everyMs = 1000): { stop: () => void } {
  let stopped = false;
  let failures = 0;
  let announced = false;
  const loop = async () => {
    while (!stopped) {
      try {
        const nowSec = Math.floor(Date.now() / 1000);
        const ticks = await gw.brti(nowSec - 90, nowSec, asset);
        for (const t of ticks) if (t.tsMs < nowSec * 1000) tape.push(t);
        if (!announced && ticks.length) {
          log(`price feed connected (CF Benchmarks ${asset === "eth" ? "ETHUSD_RTI" : "BRTI"} via Polymarket US)`);
          announced = true;
        }
        failures = 0;
      } catch (err) {
        if (failures++ % 30 === 0) warn("BRTI poll failed", err);
      }
      await new Promise((r) => setTimeout(r, everyMs));
    }
  };
  void loop();
  return { stop: () => (stopped = true) };
}
