/**
 * `npm run report`: an honest scorecard from the local ledger.
 *
 * Win rate alone means nothing at variable prices. What matters is whether the
 * model's probabilities are better calibrated than the prices you paid. The
 * Brier score compares the two: lower is better, and if the model's score is
 * not clearly below the market's, there is no edge.
 */
import { pathToFileURL } from "node:url";
import { loadConfig, loadDotEnv } from "./config.js";
import { Ledger } from "./log.js";

export interface Scorecard {
  trades: number;
  wins: number;
  costUsd: number;
  pnlUsd: number;
  roi: number;
  brierModel: number;
  brierMarket: number;
}

export function score(entries: ReturnType<Ledger["read"]>, mode: "paper" | "live"): Scorecard | null {
  const prices = new Map<string, number>();
  for (const e of entries) if (e.kind === "entry" && e.mode === mode) prices.set(`${e.slug}:${e.side}`, e.price);
  const settles = entries.filter((e) => e.kind === "settle" && e.mode === mode);
  if (!settles.length) return null;

  let wins = 0, cost = 0, pnl = 0, bModel = 0, bMarket = 0;
  for (const s of settles) {
    if (s.kind !== "settle") continue;
    const won = s.side === s.winner ? 1 : 0;
    const paid = prices.get(`${s.slug}:${s.side}`) ?? s.costUsd / s.shares;
    wins += won;
    cost += s.costUsd;
    pnl += s.pnlUsd;
    bModel += (s.modelProb - won) ** 2;
    bMarket += (paid - won) ** 2;
  }
  const n = settles.length;
  return {
    trades: n,
    wins,
    costUsd: cost,
    pnlUsd: pnl,
    roi: cost ? pnl / cost : 0,
    brierModel: bModel / n,
    brierMarket: bMarket / n,
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  loadDotEnv();
  const cfg = loadConfig({ ...process.env, MODE: "paper" });
  const entries = new Ledger(cfg.stateDir).read();
  if (!entries.some((e) => e.kind === "settle")) console.log("No settled trades yet. Run `npm start` first.");
  for (const mode of ["paper", "live"] as const) {
    const s = score(entries, mode);
    if (!s) continue;
    console.log(`\n== ${mode} ==`);
    console.log(`settled trades : ${s.trades}  (wins ${s.wins}, ${((s.wins / s.trades) * 100).toFixed(1)}%)`);
    console.log(`staked / P&L   : $${s.costUsd.toFixed(2)} / $${s.pnlUsd.toFixed(2)}  (ROI ${(s.roi * 100).toFixed(1)}%)`);
    console.log(`Brier model    : ${s.brierModel.toFixed(4)}`);
    console.log(`Brier market   : ${s.brierMarket.toFixed(4)}  (model must beat this to have an edge)`);
    if (s.trades < 200) console.log("note: under ~200 trades this is mostly noise. Keep paper trading.");
  }
}
