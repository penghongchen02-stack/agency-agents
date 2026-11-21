/**
 * Hard risk limits. These are checked before EVERY order, in paper and live mode alike.
 * Create a file named STOP in the bot directory to halt new entries at once.
 */
import { existsSync } from "node:fs";

export interface RiskLimits {
  stakeUsd: number;
  maxTradesPerSlot: number;
  maxDailyLossUsd: number;
  maxDailyTrades: number;
}

export type RiskVerdict = { ok: true } | { ok: false; reason: string };

function utcDay(tsMs: number): string {
  return new Date(tsMs).toISOString().slice(0, 10);
}

export class RiskManager {
  private day = "";
  private dailyPnl = 0;
  private dailyTrades = 0;
  /** Cost of entries not yet settled; counted as potential loss. */
  private openExposure = 0;
  private readonly tradesBySlot = new Map<number, number>();

  constructor(
    private readonly limits: RiskLimits,
    private readonly stopFile = "STOP",
    private readonly now: () => number = Date.now,
  ) {}

  private roll(): void {
    const d = utcDay(this.now());
    if (d !== this.day) {
      this.day = d;
      this.dailyPnl = 0;
      this.dailyTrades = 0;
    }
  }

  canEnter(slotStart: number, bankrollUsd: number): RiskVerdict {
    this.roll();
    if (existsSync(this.stopFile)) return { ok: false, reason: "STOP file present" };
    if ((this.tradesBySlot.get(slotStart) ?? 0) >= this.limits.maxTradesPerSlot) {
      return { ok: false, reason: "max trades for this slot" };
    }
    if (this.dailyTrades >= this.limits.maxDailyTrades) {
      return { ok: false, reason: "max daily trades" };
    }
    // Worst case: every open position plus this one goes to zero.
    const worstCase = this.dailyPnl - this.openExposure - this.limits.stakeUsd;
    if (worstCase < -this.limits.maxDailyLossUsd) {
      return { ok: false, reason: "daily loss limit" };
    }
    if (bankrollUsd < this.limits.stakeUsd) return { ok: false, reason: "insufficient bankroll" };
    return { ok: true };
  }

  recordEntry(slotStart: number, costUsd: number): void {
    this.roll();
    this.tradesBySlot.set(slotStart, (this.tradesBySlot.get(slotStart) ?? 0) + 1);
    this.dailyTrades += 1;
    this.openExposure += costUsd;
  }

  recordSettle(costUsd: number, pnlUsd: number): void {
    this.roll();
    this.openExposure = Math.max(0, this.openExposure - costUsd);
    this.dailyPnl += pnlUsd;
  }

  snapshot(): { dailyPnl: number; dailyTrades: number; openExposure: number } {
    this.roll();
    return { dailyPnl: this.dailyPnl, dailyTrades: this.dailyTrades, openExposure: this.openExposure };
  }
}
