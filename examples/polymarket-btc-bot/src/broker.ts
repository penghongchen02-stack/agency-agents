/**
 * Order execution. Two brokers share one interface:
 *  - PaperBroker: simulates a fill at the real best ask, capped at its displayed size.
 *  - LiveBroker:  sends Fill-And-Kill orders (buy and scratch-sell) through Polymarket's OFFICIAL CLOB client,
 *                 with a price cap so it never pays more than the ask we priced.
 *
 * The private key is used only to sign orders locally (viem). Nothing in this file
 * transmits it. The only network calls are to the Polymarket CLOB host.
 */
import {
  AssetType,
  COLLATERAL_TOKEN_DECIMALS,
  Chain,
  ClobClient,
  OrderType,
  Side,
} from "@polymarket/clob-client-v2";
import { createWalletClient, custom } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { polygon } from "viem/chains";
import type { Config } from "./config.js";
import type { Decision, Quote } from "./model.js";
import type { SlotMarket } from "./markets.js";

export interface Fill {
  price: number; // average price per share
  shares: number;
  costUsd: number;
  orderId?: string;
}

export interface SellFill {
  price: number; // average price per share
  shares: number;
  proceedsUsd: number;
  orderId?: string;
}

export interface SellOrder {
  side: "UP" | "DOWN";
  marketSlug: string;
  tokenId: string;
  shares: number;
  price: number; // minimum acceptable price
}

export interface Broker {
  readonly mode: "paper" | "live";
  bankrollUsd(): Promise<number>;
  buy(market: SlotMarket, decision: Decision, stakeUsd: number, quote: Quote): Promise<Fill | null>;
  sell(order: SellOrder, quote: Quote): Promise<SellFill | null>;
  /** Paper only: credit a settled position. Live payouts are redeemed on Polymarket. */
  credit(payoutUsd: number): void;
}

/** Public (unauthenticated) client for reading order books. */
export function publicClob(cfg: Config): ClobClient {
  return new ClobClient({ host: cfg.clobHost, chain: Chain.POLYGON });
}

export async function quoteFor(
  clob: ClobClient,
  side: "UP" | "DOWN",
  tokenId: string,
): Promise<Quote> {
  const book = await clob.getOrderBook(tokenId);
  let bestAsk: number | null = null;
  let askSize = 0;
  for (const level of book.asks ?? []) {
    const price = Number(level.price);
    if (!Number.isFinite(price)) continue;
    if (bestAsk === null || price < bestAsk) {
      bestAsk = price;
      askSize = Number(level.size);
    }
  }
  let bestBid: number | null = null;
  let bidSize = 0;
  for (const level of book.bids ?? []) {
    const price = Number(level.price);
    if (!Number.isFinite(price)) continue;
    if (bestBid === null || price > bestBid) {
      bestBid = price;
      bidSize = Number(level.size);
    }
  }
  return { side, tokenId, bestAsk, askSize, bestBid, bidSize };
}

/**
 * Simulated fills at the displayed best price, capped at its size. With feeTheta > 0
 * the taker fee θ·C·p·(1−p) is charged on every fill, as on Polymarket US.
 */
export class PaperBroker implements Broker {
  readonly mode = "paper" as const;
  constructor(
    private bankroll: number,
    private readonly feeTheta = 0,
  ) {}

  async bankrollUsd(): Promise<number> {
    return this.bankroll;
  }

  async buy(_m: SlotMarket, d: Decision, stakeUsd: number, q: Quote): Promise<Fill | null> {
    const perShare = d.price + this.feeTheta * d.price * (1 - d.price);
    const shares = Math.floor(Math.min(stakeUsd / perShare, q.askSize) * 100) / 100;
    if (shares <= 0) return null;
    const costUsd = shares * perShare;
    if (costUsd > this.bankroll) return null;
    this.bankroll -= costUsd;
    return { price: d.price, shares, costUsd };
  }

  async sell(o: SellOrder, q: Quote): Promise<SellFill | null> {
    if (q.bestBid === null || q.bestBid < o.price) return null;
    const shares = Math.floor(Math.min(o.shares, q.bidSize) * 100) / 100;
    if (shares <= 0) return null;
    const proceedsUsd = shares * (q.bestBid - this.feeTheta * q.bestBid * (1 - q.bestBid));
    this.bankroll += proceedsUsd;
    return { price: q.bestBid, shares, proceedsUsd };
  }

  credit(payoutUsd: number): void {
    this.bankroll += payoutUsd;
  }
}

/**
 * A wallet that can only sign locally. Its transport refuses every network call, so the
 * key provably never talks to a blockchain node or any other server.
 */
export function signingOnlyWallet(privateKey: `0x${string}`) {
  const noNetwork = custom({
    request: async ({ method }) => {
      throw new Error(`blocked RPC call "${method}": this bot only signs locally`);
    },
  });
  return createWalletClient({ account: privateKeyToAccount(privateKey), chain: polygon, transport: noNetwork });
}

export class LiveBroker implements Broker {
  readonly mode = "live" as const;
  private constructor(private readonly client: ClobClient) {}

  static async connect(cfg: Config): Promise<LiveBroker> {
    const signer = signingOnlyWallet(cfg.privateKey as `0x${string}`);
    const bootstrap = new ClobClient({ host: cfg.clobHost, chain: Chain.POLYGON, signer });
    const creds = await bootstrap.createOrDeriveApiKey();
    const client = new ClobClient({
      host: cfg.clobHost,
      chain: Chain.POLYGON,
      signer,
      creds,
      signatureType: cfg.signatureType,
      funderAddress: cfg.funderAddress,
    });
    return new LiveBroker(client);
  }

  async bankrollUsd(): Promise<number> {
    const r = await this.client.getBalanceAllowance({ asset_type: AssetType.COLLATERAL });
    return Number(r.balance) / 10 ** COLLATERAL_TOKEN_DECIMALS;
  }

  async buy(_m: SlotMarket, d: Decision, stakeUsd: number): Promise<Fill | null> {
    const resp = await this.client.createAndPostMarketOrder(
      { tokenID: d.tokenId, amount: stakeUsd, side: Side.BUY, price: d.price },
      undefined, // tick size / neg-risk are looked up by the client
      OrderType.FAK,
    );
    if (!resp.success) throw new Error(`order rejected: ${resp.errorMsg || resp.status}`);
    const shares = Number(resp.takingAmount);
    const costUsd = Number(resp.makingAmount);
    if (!(shares > 0) || !(costUsd > 0)) return null; // nothing matched
    return { price: costUsd / shares, shares, costUsd, orderId: resp.orderID };
  }

  async sell(o: SellOrder): Promise<SellFill | null> {
    const resp = await this.client.createAndPostMarketOrder(
      { tokenID: o.tokenId, amount: Math.floor(o.shares * 100) / 100, side: Side.SELL, price: o.price },
      undefined,
      OrderType.FAK,
    );
    if (!resp.success) throw new Error(`order rejected: ${resp.errorMsg || resp.status}`);
    const shares = Number(resp.makingAmount);
    const proceedsUsd = Number(resp.takingAmount);
    if (!(shares > 0) || !(proceedsUsd > 0)) return null;
    return { price: proceedsUsd / shares, shares, proceedsUsd, orderId: resp.orderID };
  }

  credit(): void {
    // Live winnings show up as redeemable positions on Polymarket.
  }
}
