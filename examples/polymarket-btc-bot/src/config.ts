/**
 * Configuration: read from environment (and an optional local .env file),
 * validated up front so the bot fails fast instead of trading on bad input.
 */
import { existsSync } from "node:fs";

export const LIVE_CONFIRM_PHRASE = "I accept the risk of losing this money";

export type Mode = "paper" | "live";
export type StrategyName = "fair-value" | "twap-scratch" | "winner-lock";
export type MarketWindow = "5m" | "15m";

export const WINDOW_SECONDS: Record<MarketWindow, number> = { "5m": 300, "15m": 900 };

export interface Config {
  mode: Mode;
  strategy: StrategyName;
  marketWindow: MarketWindow;
  slotSeconds: number;

  privateKey: string; // only populated in live mode
  funderAddress: string;
  signatureType: 0 | 1 | 2;

  // Shared model / execution settings
  minEdge: number;
  feeBuffer: number;
  minVolBpsPerSqrtSec: number;
  pollMs: number;

  // fair-value strategy
  maxEntryPrice: number;
  minEntryPrice: number;
  entryStartSec: number;
  entryEndSec: number;

  // twap-scratch strategy (the original README's described style)
  twapWindowSec: number;
  rescoreSec: number;
  scratchEntryStartSec: number;
  scratchEntryEndSec: number;
  scratchMinPrice: number;
  scratchMaxPrice: number;
  scratchExitProb: number;

  // winner-lock strategy (what the original .exe actually ran)
  wlLastSec: number;
  wlMinPrice: number;
  wlMaxPrice: number;
  wlMinEdge: number;
  wlFeeBuffer: number;

  // Risk
  stakeUsd: number;
  maxTradesPerSlot: number;
  maxSlotUsd: number;
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

function oneOf<T extends string>(env: Env, key: string, fallback: T, allowed: readonly T[]): T {
  const value = (env[key] ?? fallback).trim().toLowerCase() as T;
  if (!allowed.includes(value)) {
    throw new Error(`${key} must be one of ${allowed.join(", ")} (got "${env[key]}")`);
  }
  return value;
}

function band(lo: number, hi: number, what: string): void {
  if (lo >= hi) throw new Error(`${what}: lower bound must be below upper bound`);
}

export function loadConfig(env: Env = process.env): Config {
  const mode = oneOf(env, "MODE", "paper", ["paper", "live"] as const);
  const marketWindow = oneOf(env, "MARKET_WINDOW", "5m", ["5m", "15m"] as const);
  const slot = WINDOW_SECONDS[marketWindow];
  const stakeUsd = num(env, "STAKE_USD", 5, 1, 10_000);

  const cfg: Config = {
    mode,
    strategy: oneOf(env, "STRATEGY", "fair-value", ["fair-value", "twap-scratch", "winner-lock"] as const),
    marketWindow,
    slotSeconds: slot,

    privateKey: "",
    funderAddress: (env.FUNDER_ADDRESS ?? "").trim(),
    signatureType: num(env, "SIGNATURE_TYPE", 1, 0, 2) as 0 | 1 | 2,

    minEdge: num(env, "MIN_EDGE", 0.05, 0, 0.5),
    feeBuffer: num(env, "FEE_BUFFER", 0.02, 0, 0.2),
    minVolBpsPerSqrtSec: num(env, "MIN_VOL_BPS_PER_SQRT_SEC", 0.8, 0.01, 100),
    pollMs: num(env, "POLL_MS", 2000, 250, 60_000),

    maxEntryPrice: num(env, "MAX_ENTRY_PRICE", 0.8, 0.01, 0.99),
    minEntryPrice: num(env, "MIN_ENTRY_PRICE", 0.2, 0.01, 0.99),
    entryStartSec: num(env, "ENTRY_START_SEC", 30, 0, slot - 1),
    entryEndSec: num(env, "ENTRY_END_SEC", Math.min(240, slot - 1), 1, slot - 1),

    twapWindowSec: num(env, "TWAP_WINDOW_SEC", 30, 1, 300),
    rescoreSec: num(env, "RESCORE_SEC", 15, 1, 120),
    scratchEntryStartSec: num(env, "SCRATCH_ENTRY_START_SEC", 5, 0, slot - 1),
    scratchEntryEndSec: num(env, "SCRATCH_ENTRY_END_SEC", 150, 1, slot - 1),
    scratchMinPrice: num(env, "SCRATCH_MIN_PRICE", 0.45, 0.01, 0.99),
    scratchMaxPrice: num(env, "SCRATCH_MAX_PRICE", 0.55, 0.01, 0.99),
    scratchExitProb: num(env, "SCRATCH_EXIT_PROB", 0.5, 0.01, 0.99),

    wlLastSec: num(env, "WL_LAST_SEC", 60, 5, slot - 1),
    wlMinPrice: num(env, "WL_MIN_PRICE", 0.9, 0.5, 0.99),
    wlMaxPrice: num(env, "WL_MAX_PRICE", 0.96, 0.5, 0.99),
    wlMinEdge: num(env, "WL_MIN_EDGE", 0.01, 0, 0.5),
    wlFeeBuffer: num(env, "WL_FEE_BUFFER", 0.005, 0, 0.2),

    stakeUsd,
    maxTradesPerSlot: num(env, "MAX_TRADES_PER_SLOT", 1, 1, 20),
    maxSlotUsd: num(env, "MAX_SLOT_USD", stakeUsd * 3, 1, 100_000),
    maxDailyLossUsd: num(env, "MAX_DAILY_LOSS_USD", 25, 1, 1_000_000),
    maxDailyTrades: num(env, "MAX_DAILY_TRADES", 60, 1, 10_000),
    paperBankrollUsd: num(env, "PAPER_BANKROLL_USD", 100, 1, 10_000_000),

    stateDir: env.STATE_DIR ?? "state",
    clobHost: env.CLOB_HOST ?? "https://clob.polymarket.com",
    gammaHost: env.GAMMA_HOST ?? "https://gamma-api.polymarket.com",
  };

  band(cfg.minEntryPrice, cfg.maxEntryPrice, "MIN/MAX_ENTRY_PRICE");
  band(cfg.entryStartSec, cfg.entryEndSec, "ENTRY_START/END_SEC");
  band(cfg.scratchMinPrice, cfg.scratchMaxPrice, "SCRATCH_MIN/MAX_PRICE");
  band(cfg.scratchEntryStartSec, cfg.scratchEntryEndSec, "SCRATCH_ENTRY_START/END_SEC");
  band(cfg.wlMinPrice, cfg.wlMaxPrice, "WL_MIN/MAX_PRICE");
  if (cfg.maxSlotUsd < cfg.stakeUsd) throw new Error("MAX_SLOT_USD must be at least STAKE_USD");

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
