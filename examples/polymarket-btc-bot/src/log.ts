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

export function redact(text: string): string {
  return text.replace(HEX_KEY, "[redacted-key]");
}

export function log(msg: string, data?: Record<string, unknown>): void {
  const line = data ? `${msg} ${JSON.stringify(data)}` : msg;
  console.log(`${new Date().toISOString()} ${redact(line)}`);
}

export function warn(msg: string, err?: unknown): void {
  const detail = err instanceof Error ? err.message : err === undefined ? "" : String(err);
  console.warn(`${new Date().toISOString()} WARN ${redact(`${msg} ${detail}`.trim())}`);
}

export type LedgerEntry =
  | {
      kind: "entry";
      ts: number;
      mode: "paper" | "live";
      slug: string;
      slotStart: number;
      side: "UP" | "DOWN";
      tokenId: string;
      price: number;
      shares: number;
      costUsd: number;
      modelProb: number;
      edge: number;
      orderId?: string;
    }
  | {
      kind: "settle";
      ts: number;
      mode: "paper" | "live";
      slug: string;
      slotStart: number;
      side: "UP" | "DOWN";
      winner: "UP" | "DOWN";
      shares: number;
      costUsd: number;
      payoutUsd: number;
      pnlUsd: number;
      modelProb: number;
    };

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
