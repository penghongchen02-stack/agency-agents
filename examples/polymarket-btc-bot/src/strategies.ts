/**
 * Strategies. Each one is a pure function from market state to at most one action.
 * The engine owns execution, risk checks and bookkeeping, so a strategy can't
 * bypass the safety rails.
 *
 *  fair-value    Our default. Buy once per slot when the ask is below fair value.
 *  twap-scratch  The style the original repo's README described: TWAP-anchored signal,
 *                entries only in the ~50¢ band, several small clips per slot, re-scored
 *                every RESCORE_SEC, and a "scratch" sell when the signal turns against us.
 *  winner-lock   What the original .exe actually ran (found in its bundled code): in the
 *                final seconds, buy the >90¢ favourite. We add one rule it didn't have:
 *                our own model must agree the favourite is still underpriced.
 */
import type { Config, StrategyName } from "./config.js";
import type { Position } from "./log.js";
import { decide, feePerContract, type Quote } from "./model.js";

export type Action =
  | {
      kind: "buy";
      side: "UP" | "DOWN";
      tokenId: string;
      price: number; // limit: never pay more than this
      usd: number;
      modelProb: number;
      edge: number;
    }
  | {
      kind: "sell";
      side: "UP" | "DOWN";
      tokenId: string;
      shares: number;
      price: number; // limit: never sell for less than this
      modelProb: number;
      reason: string;
    };

export interface StrategyCtx {
  cfg: Config;
  secIn: number;
  secLeft: number;
  pUp: number;
  quotes: Quote[];
  position: Position | null;
}

export interface Strategy {
  readonly name: StrategyName;
  /** Seconds into the slot during which new buys are considered. */
  entryWindow(cfg: Config): [number, number];
  /** Whether this strategy may sell before resolution. */
  readonly exits: boolean;
  /** Price input for the model: the latest tick, or a short TWAP. */
  readonly useTwap: boolean;
  evalEveryMs(cfg: Config): number;
  act(ctx: StrategyCtx): Action | null;
}

function inWindow(s: Strategy, ctx: StrategyCtx): boolean {
  const [a, b] = s.entryWindow(ctx.cfg);
  return ctx.secIn >= a && ctx.secIn <= b;
}

function buyFrom(
  ctx: StrategyCtx,
  p: { minEdge: number; feeBuffer: number; lo: number; hi: number; onlySide?: "UP" | "DOWN" },
): Action | null {
  const d = decide({
    pUp: ctx.pUp,
    quotes: ctx.quotes,
    minEdge: p.minEdge,
    feeBuffer: p.feeBuffer,
    feeTheta: ctx.cfg.feeTheta,
    minEntryPrice: p.lo,
    maxEntryPrice: p.hi,
    onlySide: p.onlySide,
  });
  if (!d) return null;
  return { kind: "buy", ...d, usd: ctx.cfg.stakeUsd };
}

export const fairValue: Strategy = {
  name: "fair-value",
  exits: false,
  useTwap: false,
  entryWindow: (cfg) => [cfg.entryStartSec, cfg.entryEndSec],
  evalEveryMs: (cfg) => cfg.pollMs,
  act(ctx) {
    if (ctx.position || !inWindow(this, ctx)) return null;
    const { cfg } = ctx;
    return buyFrom(ctx, {
      minEdge: cfg.minEdge,
      feeBuffer: cfg.feeBuffer,
      lo: cfg.minEntryPrice,
      hi: cfg.maxEntryPrice,
    });
  },
};

export const twapScratch: Strategy = {
  name: "twap-scratch",
  exits: true,
  useTwap: true,
  entryWindow: (cfg) => [cfg.scratchEntryStartSec, cfg.scratchEntryEndSec],
  evalEveryMs: (cfg) => cfg.rescoreSec * 1000,
  act(ctx) {
    const { cfg, position } = ctx;
    if (position) {
      const q = ctx.quotes.find((x) => x.side === position.side);
      const prob = position.side === "UP" ? ctx.pUp : 1 - ctx.pUp;
      // Scratch if the signal flipped against us, or the market now pays more than
      // our model thinks the shares are worth. Never sell into a 5s-to-close book.
      if (q?.bestBid != null && q.bidSize > 0 && ctx.secLeft > 5) {
        const flipped = prob < cfg.scratchExitProb;
        const overpaid = q.bestBid - feePerContract(cfg.feeTheta, q.bestBid) >= prob;
        if (flipped || overpaid) {
          return {
            kind: "sell",
            side: position.side,
            tokenId: position.tokenId,
            shares: position.shares,
            price: q.bestBid,
            modelProb: prob,
            reason: flipped ? `signal decayed (p=${prob.toFixed(3)})` : `bid ${q.bestBid} >= model ${prob.toFixed(3)}`,
          };
        }
      }
    }
    if (!inWindow(this, ctx)) return null;
    // Add a clip only on the side already held (never hedge both sides).
    return buyFrom(ctx, {
      minEdge: cfg.minEdge,
      feeBuffer: cfg.feeBuffer,
      lo: cfg.scratchMinPrice,
      hi: cfg.scratchMaxPrice,
      onlySide: position?.side,
    });
  },
};

export const winnerLock: Strategy = {
  name: "winner-lock",
  exits: false,
  useTwap: false,
  entryWindow: (cfg) => [cfg.slotSeconds - cfg.wlLastSec, cfg.slotSeconds - 3],
  evalEveryMs: (cfg) => cfg.pollMs,
  act(ctx) {
    if (ctx.position || !inWindow(this, ctx)) return null;
    const { cfg } = ctx;
    return buyFrom(ctx, {
      minEdge: cfg.wlMinEdge,
      feeBuffer: cfg.wlFeeBuffer,
      lo: cfg.wlMinPrice,
      hi: cfg.wlMaxPrice,
    });
  },
};

export function strategyFor(name: StrategyName): Strategy {
  return name === "twap-scratch" ? twapScratch : name === "winner-lock" ? winnerLock : fairValue;
}
