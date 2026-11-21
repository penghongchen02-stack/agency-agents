/**
 * The pricing model, written out in full. There is no hidden or "private" signal.
 *
 * The question each slot asks is: will BTC at slot end be >= BTC at slot open?
 * If price follows a random walk with volatility σ (per sqrt second), then with the
 * current move d (as a log return since open) and τ seconds left:
 *
 *     P(up) = Φ( d / (σ · sqrt(τ)) )
 *
 * where Φ is the standard normal CDF. This is a *fair value*, not a prediction of
 * the future. We only trade when the order book's ask is cheaper than this fair
 * value by at least MIN_EDGE after an allowance for fees and slippage.
 *
 * Be honest with yourself: if the market already prices this in (it usually
 * does), the bot will rarely trade, and that is the correct behaviour.
 */

/** Standard normal CDF (Abramowitz–Stegun 7.1.26, |error| < 1.5e-7). */
export function normCdf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const z = Math.abs(x) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * z);
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) *
      t *
      Math.exp(-z * z);
  return 0.5 * (1 + sign * y);
}

export interface FairValueInput {
  openPrice: number;
  currentPrice: number;
  secondsLeft: number;
  volBpsPerSqrtSec: number;
}

/** Probability that the slot resolves UP. Clamped to [0.01, 0.99] so it's never "certain". */
export function probUp(i: FairValueInput): number {
  const d = Math.log(i.currentPrice / i.openPrice);
  if (i.secondsLeft <= 0) return d >= 0 ? 0.99 : 0.01;
  const sigma = i.volBpsPerSqrtSec / 10_000;
  const z = d / (sigma * Math.sqrt(i.secondsLeft));
  return Math.min(0.99, Math.max(0.01, normCdf(z)));
}

export interface Quote {
  side: "UP" | "DOWN";
  tokenId: string;
  bestAsk: number | null;
  askSize: number;
  bestBid: number | null;
  bidSize: number;
}

export interface Decision {
  side: "UP" | "DOWN";
  tokenId: string;
  price: number;
  modelProb: number;
  edge: number;
}

export interface DecideParams {
  pUp: number;
  quotes: Quote[];
  minEdge: number;
  feeBuffer: number;
  minEntryPrice: number;
  maxEntryPrice: number;
  /** Restrict to one side (e.g. when adding to an existing position). */
  onlySide?: "UP" | "DOWN";
}

/** Choose the side with the best edge, or nothing. Pure function. */
export function decide(p: DecideParams): Decision | null {
  let best: Decision | null = null;
  for (const q of p.quotes) {
    if (p.onlySide && q.side !== p.onlySide) continue;
    if (q.bestAsk === null || q.askSize <= 0) continue;
    if (q.bestAsk < p.minEntryPrice || q.bestAsk > p.maxEntryPrice) continue;
    const prob = q.side === "UP" ? p.pUp : 1 - p.pUp;
    const edge = prob - q.bestAsk - p.feeBuffer;
    if (edge < p.minEdge) continue;
    if (!best || edge > best.edge) {
      best = { side: q.side, tokenId: q.tokenId, price: q.bestAsk, modelProb: prob, edge };
    }
  }
  return best;
}
