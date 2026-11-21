/**
 * Market discovery for Polymarket "Bitcoin Up or Down" 5-minute markets.
 * Slugs look like `btc-updown-5m-<unix slot start>`, with slots on 300-second boundaries.
 * Uses only Polymarket's public Gamma API: no auth, no keys.
 */
export const SLOT_SECONDS = 300;

export interface SlotMarket {
  slug: string;
  question: string;
  slotStart: number;
  slotEnd: number;
  upTokenId: string;
  downTokenId: string;
}

export type Winner = "UP" | "DOWN";

export function slotStartFor(unixSec: number): number {
  return Math.floor(unixSec / SLOT_SECONDS) * SLOT_SECONDS;
}

export function slugFor(slotStart: number): string {
  return `btc-updown-5m-${slotStart}`;
}

function parseList(raw: unknown): string[] {
  const value = typeof raw === "string" ? (JSON.parse(raw) as unknown) : raw;
  if (!Array.isArray(value)) throw new Error("expected a JSON array");
  return value.map(String);
}

/** Pure parser for a Gamma market record, kept separate so it can be unit-tested. */
export function parseGammaMarket(data: Record<string, unknown>, slotStart: number): SlotMarket {
  const outcomes = parseList(data.outcomes).map((o) => o.toLowerCase());
  const tokens = parseList(data.clobTokenIds);
  const up = outcomes.indexOf("up");
  const down = outcomes.indexOf("down");
  if (up < 0 || down < 0 || !tokens[up] || !tokens[down]) {
    throw new Error(`unexpected outcomes ${JSON.stringify(outcomes)}`);
  }
  return {
    slug: slugFor(slotStart),
    question: String(data.question ?? slugFor(slotStart)),
    slotStart,
    slotEnd: slotStart + SLOT_SECONDS,
    upTokenId: tokens[up],
    downTokenId: tokens[down],
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
  constructor(private readonly host: string) {}

  private async get(slug: string): Promise<Record<string, unknown> | null> {
    const resp = await fetch(`${this.host}/markets/slug/${encodeURIComponent(slug)}`, {
      signal: AbortSignal.timeout(8000),
    });
    if (resp.status === 404) return null;
    if (!resp.ok) throw new Error(`Gamma HTTP ${resp.status}`);
    return (await resp.json()) as Record<string, unknown>;
  }

  async market(slotStart: number): Promise<SlotMarket | null> {
    const data = await this.get(slugFor(slotStart));
    return data ? parseGammaMarket(data, slotStart) : null;
  }

  async resolution(slotStart: number): Promise<Winner | null> {
    const data = await this.get(slugFor(slotStart));
    return data ? parseResolution(data) : null;
  }
}
