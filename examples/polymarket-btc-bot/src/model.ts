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
  /** Seconds until the settlement value is sampled. */
  secondsLeft: number;
  /** Volatility of the underlying (raw) price, in bps per sqrt(second). */
  volBpsPerSqrtSec: number;
  /**
   * 0 (global): the feed is the raw price and settlement is a single price.
   * N > 0 (Polymarket US): the feed is already a trailing N-second average of the raw index,
   * and settlement IS the feed's value at the sampling time. Verified: the published
   * priceToBeat/settlementPrice equal the feed's 1-second value at T−1s exactly.
   */
  smoothSec?: number;
  /** Recent slope of the smoothed feed, in price units per second (US only). */
  slopePerSec?: number;
}

/**
 * Probability that the slot resolves UP. Clamped to [0.01, 0.99] so it's never "certain".
 *
 * Point model (global): P(up) = Φ( ln(P/open) / (σ·√τ) ).
 *
 * Smoothed model (US): the feed S(t) is the mean of the last N raw prices, so it lags
 * the raw price. Assume the raw price moved roughly linearly over the last N seconds
 * with slope b (≈ the feed's own 1-second slope). Then:
 *   raw now            ≈ S + b·(N−1)/2
 *   E[S at settlement] = raw − b·k(k−1)/(2N)       (k = window points already in the past)
 *   Var                = σ²/N² · Σᵢ Σⱼ min(uᵢ, uⱼ) (uᵢ = how far ahead each future point is)
 * Ignoring the lag would make the bot "see edge" that is just the feed being 30s stale.
 */
export function probUp(i: FairValueInput): number {
  const sigma = i.volBpsPerSqrtSec / 10_000;
  const tau = Math.max(0, i.secondsLeft);
  const N = Math.max(0, Math.round(i.smoothSec ?? 0));
  let expected = i.currentPrice;
  let variance: number;
  if (N === 0) {
    variance = sigma * sigma * tau;
  } else {
    const b = i.slopePerSec ?? 0;
    const raw = i.currentPrice + (b * (N - 1)) / 2;
    const m = Math.min(N, Math.floor(tau)); // future points in the settlement window
    const k = N - m;
    expected = raw - (b * k * (k - 1)) / (2 * N);
    // ascending future offsets u_1..u_m = tau-m+1 .. tau ; ΣΣmin = Σ u_i·(2(m−i)+1)
    let sum = 0;
    for (let idx = 1; idx <= m; idx++) {
      const u = tau - m + idx;
      sum += u * (2 * (m - idx) + 1);
    }
    variance = (sigma * sigma * sum) / (N * N);
  }
  const d = Math.log(expected / i.openPrice);
  if (variance <= 0) return d >= 0 ? 0.99 : 0.01; // ties settle Up
  const z = d / Math.sqrt(variance);
  return Math.min(0.99, Math.max(0.01, normCdf(z)));
}

/** Taker fee per contract: θ × p × (1 − p) (Polymarket US formula). */
export function feePerContract(theta: number, price: number): number {
  return theta * price * (1 - price);
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
  /** Taker fee coefficient; the exact fee is subtracted from the edge. */
  feeTheta?: number;
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
    const edge = prob - q.bestAsk - feePerContract(p.feeTheta ?? 0, q.bestAsk) - p.feeBuffer;
    if (edge < p.minEdge) continue;
    if (!best || edge > best.edge) {
      best = { side: q.side, tokenId: q.tokenId, price: q.bestAsk, modelProb: prob, edge };
    }
  }
  return best;
}
