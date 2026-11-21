/**
 * Market discovery for Polymarket "Bitcoin Up or Down" 5- and 15-minute markets.
 * Slugs look like `btc-updown-5m-<unix slot start>` / `btc-updown-15m-<unix slot start>`.
 * Uses only Polymarket's public Gamma API: no auth, no keys.
 */
import { WINDOW_SECONDS, type MarketWindow } from "./config.js";

export interface SlotMarket {
  slug: string;
  question: string;
  slotStart: number;
  slotEnd: number;
  upTokenId: string;
  downTokenId: string;
  /** Opening reference price published by the venue (Polymarket US), if any. */
  priceToBeat?: number;
  /**
   * 0: the price feed is raw and settles at slotEnd.
   * N: the feed is a trailing N-second average and settles at its value at slotEnd − 1s (US).
   */
  feedSmoothingSec: number;
}

export type Winner = "UP" | "DOWN";

export function slotStartFor(unixSec: number, slotSeconds = 300): number {
  return Math.floor(unixSec / slotSeconds) * slotSeconds;
}

export function slugFor(slotStart: number, window: MarketWindow = "5m"): string {
  return `btc-updown-${window}-${slotStart}`;
}

function parseList(raw: unknown): string[] {
  const value = typeof raw === "string" ? (JSON.parse(raw) as unknown) : raw;
  if (!Array.isArray(value)) throw new Error("expected a JSON array");
  return value.map(String);
}

/** Pure parser for a Gamma market record, kept separate so it can be unit-tested. */
export function parseGammaMarket(
  data: Record<string, unknown>,
  slotStart: number,
  window: MarketWindow = "5m",
): SlotMarket {
  const outcomes = parseList(data.outcomes).map((o) => o.toLowerCase());
  const tokens = parseList(data.clobTokenIds);
  const up = outcomes.indexOf("up");
  const down = outcomes.indexOf("down");
  if (up < 0 || down < 0 || !tokens[up] || !tokens[down]) {
    throw new Error(`unexpected outcomes ${JSON.stringify(outcomes)}`);
  }
  return {
    slug: slugFor(slotStart, window),
    question: String(data.question ?? slugFor(slotStart, window)),
    slotStart,
    slotEnd: slotStart + WINDOW_SECONDS[window],
    upTokenId: tokens[up],
    downTokenId: tokens[down],
    feedSmoothingSec: 0,
  };
}

/** Returns the winner once Gamma shows the market resolved, else null. */
export function parseResolution(data: Record<string, unknown>): Winner | null {
  if (!data.closed) return null;
  const outcomes = parseList(data.outcomes).map((o) => o.toLowerCase());
  const prices = parseList(data.outcomePrices).map(Number);
  const winIdx = prices.findIndex((p) => p >= 0.99);
  if (winIdx < 0) return null;
  const label = outcomes[winIdx];
  return label === "up" ? "UP" : label === "down" ? "DOWN" : null;
}

export class Gamma {
  constructor(
    private readonly host: string,
    private readonly window: MarketWindow = "5m",
  ) {}

  private async get(slug: string): Promise<Record<string, unknown> | null> {
    const resp = await fetch(`${this.host}/markets/slug/${encodeURIComponent(slug)}`, {
      signal: AbortSignal.timeout(8000),
    });
    if (resp.status === 404) return null;
    if (!resp.ok) throw new Error(`Gamma HTTP ${resp.status}`);
    return (await resp.json()) as Record<string, unknown>;
  }

  async market(slotStart: number): Promise<SlotMarket | null> {
    const data = await this.get(slugFor(slotStart, this.window));
    return data ? parseGammaMarket(data, slotStart, this.window) : null;
  }

  async resolution(slotStart: number): Promise<Winner | null> {
    const data = await this.get(slugFor(slotStart, this.window));
    return data ? parseResolution(data) : null;
  }
}
