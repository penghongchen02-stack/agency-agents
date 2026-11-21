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
