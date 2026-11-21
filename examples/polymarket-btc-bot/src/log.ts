/**
 * Logging and the trade ledger.
 *
 * Everything that is written passes through `redact`, so a private key can't
 * leak into logs even by accident. The ledger is append-only JSON lines and
 * never leaves your machine.
 */
import { appendFileSync, mkdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const HEX_KEY = /0x[0-9a-fA-F]{64}\b|\b[0-9a-fA-F]{64}\b/g;
// base64 of a 32- or 64-byte secret (Polymarket US Ed25519 keys)
const B64_KEY = /(?<![A-Za-z0-9+/])(?:[A-Za-z0-9+/]{43}=|[A-Za-z0-9+/]{86}==)(?![A-Za-z0-9+/=])/g;

export function redact(text: string): string {
  return text.replace(HEX_KEY, "[redacted-key]").replace(B64_KEY, "[redacted-key]");
}

let quiet = false;
/** Silence routine logs (used by the backtest). Warnings still print. */
export function setQuiet(q: boolean): void {
  quiet = q;
}

export function log(msg: string, data?: Record<string, unknown>): void {
  if (quiet) return;
  const line = data ? `${msg} ${JSON.stringify(data)}` : msg;
  console.log(`${new Date().toISOString()} ${redact(line)}`);
}

export function warn(msg: string, err?: unknown): void {
  const detail = err instanceof Error ? err.message : err === undefined ? "" : String(err);
  console.warn(`${new Date().toISOString()} WARN ${redact(`${msg} ${detail}`.trim())}`);
}

type Side = "UP" | "DOWN";
interface Base {
  ts: number;
  mode: "paper" | "live";
  strategy?: string;
  slug: string;
  slotStart: number;
  /** Absent in ledgers written by v0.1 (5-minute only). */
  slotEnd?: number;
  side: Side;
}

export type LedgerEntry =
  | (Base & {
      kind: "entry";
      tokenId: string;
      price: number;
      shares: number;
      costUsd: number;
      modelProb: number;
      edge: number;
      orderId?: string;
    })
  | (Base & {
      /** A scratch: position sold before resolution. */
      kind: "exit";
      tokenId: string;
      price: number;
      shares: number;
      proceedsUsd: number;
      costUsd: number; // cost basis of the shares sold
      pnlUsd: number;
      modelProb: number;
      reason: string;
      orderId?: string;
    })
  | (Base & {
      kind: "settle";
      winner: Side;
      shares: number;
      costUsd: number;
      payoutUsd: number;
      pnlUsd: number;
      modelProb: number;
    });

export class Ledger {
  private readonly file: string;

  constructor(stateDir: string) {
    mkdirSync(stateDir, { recursive: true });
    this.file = join(stateDir, "ledger.jsonl");
  }

  append(entry: LedgerEntry): void {
    appendFileSync(this.file, redact(JSON.stringify(entry)) + "\n", "utf8");
  }

  read(): LedgerEntry[] {
    if (!existsSync(this.file)) return [];
    return readFileSync(this.file, "utf8")
      .split("\n")
      .filter((l) => l.trim())
      .flatMap((l) => {
        try {
          return [JSON.parse(l) as LedgerEntry];
        } catch {
          return [];
        }
      });
  }
}

export interface Position {
  slug: string;
  slotStart: number;
  slotEnd: number;
  side: Side;
  tokenId: string;
  shares: number;
  costUsd: number;
  modelProb: number;
  clips: number;
}

export interface Replay {
  positions: Map<number, Position>;
  /** Net cash change from all activity (negative = money in positions or lost). */
  cashDeltaUsd: number;
  /** Today's (UTC) activity, used to rebuild risk counters. */
  today: { entries: { slotStart: number; costUsd: number }[]; closes: { costUsd: number; pnlUsd: number }[] };
}

/** Rebuild open positions and cash flows by replaying the ledger in order. */
export function replayLedger(entries: LedgerEntry[], mode: "paper" | "live", nowMs: number): Replay {
  const day = new Date(nowMs).toISOString().slice(0, 10);
  const positions = new Map<number, Position>();
  const r: Replay = { positions, cashDeltaUsd: 0, today: { entries: [], closes: [] } };
  for (const e of entries) {
    if (e.mode !== mode) continue;
    const isToday = new Date(e.ts).toISOString().slice(0, 10) === day;
    const slotEnd = e.slotEnd ?? e.slotStart + 300;
    if (e.kind === "entry") {
      r.cashDeltaUsd -= e.costUsd;
      if (isToday) r.today.entries.push({ slotStart: e.slotStart, costUsd: e.costUsd });
      const p = positions.get(e.slotStart);
      if (p && p.side === e.side) {
        p.shares += e.shares;
        p.costUsd += e.costUsd;
        p.clips += 1;
      } else {
        positions.set(e.slotStart, {
          slug: e.slug,
          slotStart: e.slotStart,
          slotEnd,
          side: e.side,
          tokenId: e.tokenId,
          shares: e.shares,
          costUsd: e.costUsd,
          modelProb: e.modelProb,
          clips: 1,
        });
      }
    } else if (e.kind === "exit") {
      r.cashDeltaUsd += e.proceedsUsd;
      if (isToday) r.today.closes.push({ costUsd: e.costUsd, pnlUsd: e.pnlUsd });
      const p = positions.get(e.slotStart);
      if (p) {
        p.shares -= e.shares;
        p.costUsd -= e.costUsd;
        if (p.shares <= 1e-9) positions.delete(e.slotStart);
      }
    } else {
      r.cashDeltaUsd += e.payoutUsd;
      if (isToday) r.today.closes.push({ costUsd: e.costUsd, pnlUsd: e.pnlUsd });
      positions.delete(e.slotStart);
    }
  }
  return r;
}
