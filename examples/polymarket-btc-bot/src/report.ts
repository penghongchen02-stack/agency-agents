/**
 * `npm run report`: an honest scorecard from the local ledger, per mode and strategy.
 *
 * Win rate alone means nothing at variable prices, and scratch exits can make a
 * win rate look better than it is. So the report shows:
 *  - total P&L including scratches,
 *  - Brier score of the model vs the price paid, on positions held to resolution.
 *    Lower is better; if the model's isn't clearly below the market's, there's no edge.
 */
import { pathToFileURL } from "node:url";
import { loadConfig, loadDotEnv } from "./config.js";
import { Ledger, type LedgerEntry } from "./log.js";

export interface Scorecard {
  trades: number; // positions held to resolution
  wins: number;
  scratches: number;
  scratchPnlUsd: number;
  costUsd: number; // total bought
  pnlUsd: number; // settles + scratches
  roi: number;
  brierModel: number;
  brierMarket: number;
}

export function score(entries: LedgerEntry[], mode: "paper" | "live", strategy?: string): Scorecard | null {
  const mine = entries.filter(
    (e) => e.mode === mode && (strategy === undefined || (e.strategy ?? "fair-value") === strategy),
  );
  // Average price paid per slot (positions can be built from several clips).
  const paid = new Map<number, { cost: number; shares: number }>();
  let cost = 0;
  for (const e of mine) {
    if (e.kind !== "entry") continue;
    cost += e.costUsd;
    const p = paid.get(e.slotStart) ?? { cost: 0, shares: 0 };
    p.cost += e.price * e.shares; // trade price, excluding fees
    p.shares += e.shares;
    paid.set(e.slotStart, p);
  }
  const settles = mine.filter((e) => e.kind === "settle");
  const exits = mine.filter((e) => e.kind === "exit");
  if (!settles.length && !exits.length) return null;

  let wins = 0, pnl = 0, bModel = 0, bMarket = 0, scratchPnl = 0;
  for (const s of settles) {
    if (s.kind !== "settle") continue;
    const won = s.side === s.winner ? 1 : 0;
    const p = paid.get(s.slotStart);
    const avg = p && p.shares ? p.cost / p.shares : s.costUsd / s.shares;
    wins += won;
    pnl += s.pnlUsd;
    bModel += (s.modelProb - won) ** 2;
    bMarket += (avg - won) ** 2;
  }
  for (const x of exits) if (x.kind === "exit") scratchPnl += x.pnlUsd;
  pnl += scratchPnl;
  const n = settles.length;
  return {
    trades: n,
    wins,
    scratches: exits.length,
    scratchPnlUsd: scratchPnl,
    costUsd: cost,
    pnlUsd: pnl,
    roi: cost ? pnl / cost : 0,
    brierModel: n ? bModel / n : NaN,
    brierMarket: n ? bMarket / n : NaN,
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  loadDotEnv();
  const cfg = loadConfig({ ...process.env, MODE: "paper" });
  const entries = new Ledger(cfg.stateDir).read();
  if (!entries.some((e) => e.kind !== "entry")) console.log("No closed trades yet. Run `npm start` first.");
  const strategies = [...new Set(entries.map((e) => e.strategy ?? "fair-value"))];
  for (const mode of ["paper", "live"] as const) {
    for (const strat of strategies) {
      const s = score(entries, mode, strat);
      if (!s) continue;
      console.log(`\n== ${mode} / ${strat} ==`);
      if (s.trades) {
        console.log(`held to resolution : ${s.trades}  (wins ${s.wins}, ${((s.wins / s.trades) * 100).toFixed(1)}%)`);
      }
      if (s.scratches) console.log(`scratch exits      : ${s.scratches}  (P&L $${s.scratchPnlUsd.toFixed(2)})`);
      console.log(`bought / total P&L : $${s.costUsd.toFixed(2)} / $${s.pnlUsd.toFixed(2)}  (ROI ${(s.roi * 100).toFixed(1)}%)`);
      if (s.trades) {
        console.log(`Brier model        : ${s.brierModel.toFixed(4)}`);
        console.log(`Brier market       : ${s.brierMarket.toFixed(4)}  (model must beat this to have an edge)`);
      }
      if (s.trades + s.scratches < 200) console.log("note: under ~200 trades this is mostly noise. Keep paper trading.");
    }
  }
}
