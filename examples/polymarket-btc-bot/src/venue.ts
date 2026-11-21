/**
 * A Venue is where markets, order books and results come from. The engine only
 * talks to this interface, so the same strategies run on:
 *  - "us":     Polymarket US (gateway.polymarket.us), CFTC-regulated, settles on CF Benchmarks BRTI
 *  - "global": polymarket.com (Gamma + CLOB), settles on Chainlink
 *  - backtests, which replay recorded history through the same interface.
 */
import type { ClobClient } from "@polymarket/clob-client-v2";
import { quoteFor } from "./broker.js";
import type { Gamma, SlotMarket, Winner } from "./markets.js";
import type { Quote } from "./model.js";

export interface Venue {
  readonly name: string;
  market(slotStart: number): Promise<SlotMarket | null>;
  resolution(slotStart: number): Promise<Winner | null>;
  /** Up and Down quotes for a market (each with best ask and best bid). */
  quotes(market: SlotMarket): Promise<Quote[]>;
}

export class GlobalVenue implements Venue {
  readonly name = "global";
  constructor(
    private readonly gamma: Gamma,
    private readonly clob: ClobClient,
  ) {}

  market(slotStart: number) {
    return this.gamma.market(slotStart);
  }

  resolution(slotStart: number) {
    return this.gamma.resolution(slotStart);
  }

  quotes(m: SlotMarket) {
    return Promise.all([quoteFor(this.clob, "UP", m.upTokenId), quoteFor(this.clob, "DOWN", m.downTokenId)]);
  }
}
