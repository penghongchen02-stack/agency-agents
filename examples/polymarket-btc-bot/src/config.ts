/**
 * Configuration: read from environment (and an optional local .env file),
 * validated up front so the bot fails fast instead of trading on bad input.
 */
import { existsSync } from "node:fs";

export const LIVE_CONFIRM_PHRASE = "I accept the risk of losing this money";

export type Mode = "paper" | "live";

export interface Config {
  mode: Mode;
  privateKey: string; // only populated in live mode
  funderAddress: string;
  signatureType: 0 | 1 | 2;

  minEdge: number;
  feeBuffer: number;
  maxEntryPrice: number;
  minEntryPrice: number;
  entryStartSec: number;
  entryEndSec: number;
  minVolBpsPerSqrtSec: number;
  pollMs: number;

  stakeUsd: number;
  maxTradesPerSlot: number;
  maxDailyLossUsd: number;
  maxDailyTrades: number;
  paperBankrollUsd: number;

  stateDir: string;
  clobHost: string;
  gammaHost: string;
}

type Env = Record<string, string | undefined>;

function num(env: Env, key: string, fallback: number, min: number, max: number): number {
  const raw = env[key];
  const value = raw === undefined || raw.trim() === "" ? fallback : Number(raw);
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new Error(`${key} must be a number in [${min}, ${max}] (got "${raw}")`);
  }
  return value;
}

export function loadConfig(env: Env = process.env): Config {
  const mode = (env.MODE ?? "paper").trim().toLowerCase();
  if (mode !== "paper" && mode !== "live") {
    throw new Error(`MODE must be "paper" or "live" (got "${env.MODE}")`);
  }

  const cfg: Config = {
    mode,
    privateKey: "",
    funderAddress: (env.FUNDER_ADDRESS ?? "").trim(),
    signatureType: num(env, "SIGNATURE_TYPE", 1, 0, 2) as 0 | 1 | 2,

    minEdge: num(env, "MIN_EDGE", 0.05, 0, 0.5),
    feeBuffer: num(env, "FEE_BUFFER", 0.02, 0, 0.2),
    maxEntryPrice: num(env, "MAX_ENTRY_PRICE", 0.8, 0.01, 0.99),
    minEntryPrice: num(env, "MIN_ENTRY_PRICE", 0.2, 0.01, 0.99),
    entryStartSec: num(env, "ENTRY_START_SEC", 30, 0, 299),
    entryEndSec: num(env, "ENTRY_END_SEC", 240, 1, 299),
    minVolBpsPerSqrtSec: num(env, "MIN_VOL_BPS_PER_SQRT_SEC", 0.8, 0.01, 100),
    pollMs: num(env, "POLL_MS", 2000, 250, 60_000),

    stakeUsd: num(env, "STAKE_USD", 5, 1, 10_000),
    maxTradesPerSlot: num(env, "MAX_TRADES_PER_SLOT", 1, 1, 10),
    maxDailyLossUsd: num(env, "MAX_DAILY_LOSS_USD", 25, 1, 1_000_000),
    maxDailyTrades: num(env, "MAX_DAILY_TRADES", 60, 1, 10_000),
    paperBankrollUsd: num(env, "PAPER_BANKROLL_USD", 100, 1, 10_000_000),

    stateDir: env.STATE_DIR ?? "state",
    clobHost: env.CLOB_HOST ?? "https://clob.polymarket.com",
    gammaHost: env.GAMMA_HOST ?? "https://gamma-api.polymarket.com",
  };

  if (cfg.minEntryPrice >= cfg.maxEntryPrice) {
    throw new Error("MIN_ENTRY_PRICE must be below MAX_ENTRY_PRICE");
  }
  if (cfg.entryStartSec >= cfg.entryEndSec) {
    throw new Error("ENTRY_START_SEC must be below ENTRY_END_SEC");
  }

  if (cfg.mode === "live") {
    if ((env.LIVE_CONFIRM ?? "").trim() !== LIVE_CONFIRM_PHRASE) {
      throw new Error(`MODE=live requires LIVE_CONFIRM="${LIVE_CONFIRM_PHRASE}"`);
    }
    const pk = (env.PRIVATE_KEY ?? "").trim();
    const normalized = pk.startsWith("0x") ? pk : `0x${pk}`;
    if (!/^0x[0-9a-fA-F]{64}$/.test(normalized)) {
      throw new Error("PRIVATE_KEY must be a 32-byte hex key in live mode");
    }
    if (!/^0x[0-9a-fA-F]{40}$/.test(cfg.funderAddress)) {
      throw new Error("FUNDER_ADDRESS must be your Polymarket wallet address in live mode");
    }
    cfg.privateKey = normalized;
  }

  return cfg;
}

/** Load ./.env if present, using Node's built-in loader (no extra dependency). */
export function loadDotEnv(path = ".env"): void {
  if (existsSync(path)) process.loadEnvFile(path);
}

/** A copy of the config that is safe to print. */
export function describeConfig(cfg: Config): Record<string, unknown> {
  const { privateKey, ...rest } = cfg;
  return { ...rest, privateKey: privateKey ? "[set, hidden]" : "[not set]" };
}
