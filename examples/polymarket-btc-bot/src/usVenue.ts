/**
 * Polymarket US (polymarket.us): public market data via gateway.polymarket.us.
 * No authentication is needed for anything in this file.
 *
 * Facts this relies on (docs.polymarket.us, checked against live responses):
 *  - BTC Up/Down market slugs: `cpc-btc-updown-5m-YYYY-MM-DD-HHMMz` (window start, UTC).
 *  - One instrument per market: YES = Up (long), NO = Down (short). The book is the
 *    YES book. Prices always refer to YES; NO price = 1 − YES price.
 *  - Settlement: CF Benchmarks BRTI, the average of the 60 one-second prices in [T−60s, T).
 *    `assetPriceTerms.priceToBeat` is that average at the window start.
 *  - /v1/asset-prices/history (1-second candles, public) serves that 60-second average
 *    already: every candle has tickCount 60, and the candle at T−1s equals priceToBeat
 *    (and at close−1s equals settlementPrice) exactly. Checked live on 2026-11-21.
 *    So the feed is a smoothed series, and settlement is its value at close − 1s.
 *  - Resolved markets have status MARKET_STATUS_RESOLVED and outcomePrices ["1","0"] (Up won)
 *    or ["0","1"] (Down won). Ties settle Up.
 */
import type { MarketWindow } from "./config.js";
import { WINDOW_SECONDS } from "./config.js";
import type { SlotMarket, Winner } from "./markets.js";
import type { Quote } from "./model.js";
import type { Tick } from "./priceFeed.js";
import type { Venue } from "./venue.js";

export const US_FEED_SMOOTHING_SEC = 60;

export function usSlugFor(slotStart: number, window: MarketWindow = "5m"): string {
  const d = new Date(slotStart * 1000).toISOString(); // 2026-11-21T12:05:00.000Z
  return `cpc-btc-updown-${window}-${d.slice(0, 10)}-${d.slice(11, 13)}${d.slice(14, 16)}z`;
}

type Json = Record<string, unknown>;
interface Px {
  value: string;
}
interface Level {
  px: Px;
  qty: string;
}

export function parseUsMarket(m: Json, slotStart: number, window: MarketWindow): SlotMarket {
  const terms = (m.assetPriceTerms ?? {}) as Json;
  const ptb = terms.priceToBeat as Px | null | undefined;
  const slug = String(m.slug);
  return {
    slug,
    question: String(m.question ?? slug),
    slotStart,
    slotEnd: slotStart + WINDOW_SECONDS[window],
    upTokenId: `${slug}:YES`,
    downTokenId: `${slug}:NO`,
    priceToBeat: ptb ? Number(ptb.value) : undefined,
    feedSmoothingSec: US_FEED_SMOOTHING_SEC,
  };
}

export function parseUsResolution(m: Json): Winner | null {
  if (m.status !== "MARKET_STATUS_RESOLVED") return null;
  const raw = m.outcomePrices;
  const prices = (typeof raw === "string" ? (JSON.parse(raw) as unknown[]) : (raw as unknown[]) ?? []).map(Number);
  if (prices[0] === 1) return "UP";
  if (prices[1] === 1) return "DOWN";
  return null;
}

/** Turn the YES order book into Up and Down quotes. */
export function quotesFromYesBook(slug: string, bids: Level[], offers: Level[]): Quote[] {
  const best = (levels: Level[], better: (a: number, b: number) => boolean) => {
    let px: number | null = null;
    let qty = 0;
    for (const l of levels) {
      const p = Number(l.px.value);
      if (!Number.isFinite(p)) continue;
      if (px === null || better(p, px)) {
        px = p;
        qty = Number(l.qty);
      }
    }
    return { px, qty };
  };
  const bid = best(bids, (a, b) => a > b);
  const ask = best(offers, (a, b) => a < b);
  const r = (x: number) => Math.round(x * 10_000) / 10_000;
  return [
    { side: "UP", tokenId: `${slug}:YES`, bestAsk: ask.px, askSize: ask.qty, bestBid: bid.px, bidSize: bid.qty },
    {
      side: "DOWN",
      tokenId: `${slug}:NO`,
      // Buying NO = selling YES into the YES bid; selling NO = buying YES from the YES ask.
      bestAsk: bid.px === null ? null : r(1 - bid.px),
      askSize: bid.qty,
      bestBid: ask.px === null ? null : r(1 - ask.px),
      bidSize: ask.qty,
    },
  ];
}

export class UsGateway {
  constructor(private readonly host = "https://gateway.polymarket.us") {}

  async get(path: string): Promise<Json | null> {
    for (let attempt = 0; attempt < 4; attempt++) {
      const resp = await fetch(`${this.host}${path}`, { signal: AbortSignal.timeout(10_000) });
      if (resp.status === 429) {
        await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
        continue;
      }
      if (resp.status === 404) return null;
      if (!resp.ok) throw new Error(`Polymarket US gateway HTTP ${resp.status} for ${path.split("?")[0]}`);
      return (await resp.json()) as Json;
    }
    throw new Error("Polymarket US gateway rate limit (429) persisted");
  }

  async marketBySlug(slug: string): Promise<Json | null> {
    const r = await this.get(`/v1/market/slug/${encodeURIComponent(slug)}`);
    return (r?.market as Json) ?? null;
  }

  async book(slug: string): Promise<{ bids: Level[]; offers: Level[] }> {
    const r = await this.get(`/v1/markets/${encodeURIComponent(slug)}/book`);
    const md = (r?.marketData ?? {}) as { bids?: Level[]; offers?: Level[] };
    return { bids: md.bids ?? [], offers: md.offers ?? [] };
  }

  /** BRTI one-second prices in [fromSec, toSec]. Skips gap-filled seconds. */
  async brti(fromSec: number, toSec: number): Promise<Tick[]> {
    const r = await this.get(
      `/v1/asset-prices/history?assets=crypto:btc&bucket=ASSET_PRICE_BUCKET_1S&from=${fromSec}&to=${toSec}`,
    );
    const series = ((r?.series ?? []) as Json[]).find(
      (s) => ((s.asset ?? {}) as Json).symbol === "btc",
    );
    const candles = (series?.candles ?? []) as { timestamp: number | string; close: string; tickCount?: number }[];
    return candles
      .filter((c) => (c.tickCount ?? 1) > 0)
      .map((c) => ({ tsMs: Number(c.timestamp) * 1000, price: Number(c.close) }));
  }

  /** Displayed YES/NO prices of a market over a time range (about one point a minute). */
  async priceHistory(slug: string, fromSec: number, toSec: number): Promise<{ t: number; long: number; short: number }[]> {
    const r = await this.get(
      `/v1/price-history?symbol=${encodeURIComponent(slug)}&timestamp.startTimestamp=${fromSec}&timestamp.endTimestamp=${toSec}&fidelity=1`,
    );
    const h = (r?.history ?? []) as { timestamp: number | string; longPrice: number; shortPrice: number }[];
    return h.map((p) => ({ t: Number(p.timestamp), long: Number(p.longPrice), short: Number(p.shortPrice) }));
  }
}

export class UsVenue implements Venue {
  readonly name = "us";
  constructor(
    private readonly gw: UsGateway,
    private readonly window: MarketWindow = "5m",
  ) {}

  async market(slotStart: number): Promise<SlotMarket | null> {
    const m = await this.gw.marketBySlug(usSlugFor(slotStart, this.window));
    if (!m || m.closed || m.status === "MARKET_STATUS_RESOLVED") return null;
    return parseUsMarket(m, slotStart, this.window);
  }

  async resolution(slotStart: number): Promise<Winner | null> {
    const m = await this.gw.marketBySlug(usSlugFor(slotStart, this.window));
    return m ? parseUsResolution(m) : null;
  }

  async quotes(market: SlotMarket): Promise<Quote[]> {
    const b = await this.gw.book(market.slug);
    return quotesFromYesBook(market.slug, b.bids, b.offers);
  }
}
