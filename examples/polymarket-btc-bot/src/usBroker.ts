/**
 * Live trading on Polymarket US through Polymarket's OFFICIAL SDK (`polymarket-us`,
 * github.com/Polymarket/polymarket-us-typescript). Requests are signed locally with
 * your Ed25519 API secret; the secret itself is never sent anywhere.
 *
 * Order rules (docs.polymarket.us):
 *  - One instrument per market. Up = BUY_LONG (YES), Down = BUY_SHORT (NO).
 *  - The order price ALWAYS refers to the YES side. Buying NO at 0.40 is sent as 0.60.
 *  - API orders must be flagged MANUAL_ORDER_INDICATOR_AUTOMATIC.
 *
 * Safety: every order is first sent to `orders.preview`. If the exchange's reading of
 * the order (intent, YES price, quantity) differs from ours in any way, we refuse to
 * place it. Orders are IOC limits, so nothing is left resting on the book.
 */
import { PolymarketUS, type CreateOrderParams, type CreateOrderResponse, type OrderIntent } from "polymarket-us";
import type { Broker, Fill, SellFill, SellOrder } from "./broker.js";
import type { Config } from "./config.js";
import type { SlotMarket } from "./markets.js";
import type { Decision } from "./model.js";

const px = (v: number) => ({ value: v.toFixed(2), currency: "USD" as const });

/** Convert the price of the side we want into the YES price the API expects. */
export function yesPriceFor(side: "UP" | "DOWN", sidePrice: number): number {
  return Math.round((side === "UP" ? sidePrice : 1 - sidePrice) * 100) / 100;
}

export function buildOrder(
  slug: string,
  intent: OrderIntent,
  yesPrice: number,
  quantity: number,
): CreateOrderParams {
  return {
    marketSlug: slug,
    intent,
    type: "ORDER_TYPE_LIMIT",
    price: px(yesPrice),
    quantity,
    tif: "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL",
    manualOrderIndicator: "MANUAL_ORDER_INDICATOR_AUTOMATIC",
    synchronousExecution: true,
    maxBlockTime: "5",
  };
}

/** Sum fills from a synchronous order response, in the traded side's terms. */
export function summarizeExecutions(
  resp: CreateOrderResponse,
  side: "UP" | "DOWN",
): { shares: number; notional: number; commission: number } {
  let shares = 0;
  let notional = 0;
  let commission = 0;
  for (const e of resp.executions ?? []) {
    if (e.type !== "EXECUTION_TYPE_FILL" && e.type !== "EXECUTION_TYPE_PARTIAL_FILL") continue;
    const q = Number(e.lastShares ?? 0);
    const yes = Number(e.lastPx?.value ?? NaN);
    if (!(q > 0) || !Number.isFinite(yes)) continue;
    shares += q;
    notional += q * (side === "UP" ? yes : 1 - yes);
    commission += Number(e.commissionNotionalCollected?.value ?? 0);
  }
  return { shares, notional, commission };
}

export class UsLiveBroker implements Broker {
  readonly mode = "live" as const;
  private readonly client: PolymarketUS;

  constructor(cfg: Config) {
    this.client = new PolymarketUS({ keyId: cfg.usKeyId, secretKey: cfg.usSecretKey });
  }

  async bankrollUsd(): Promise<number> {
    const r = await this.client.account.balances();
    const usd = r.balances.find((b) => b.currency === "USD") ?? r.balances[0];
    return usd ? Number(usd.buyingPower) : 0;
  }

  private async placeChecked(order: CreateOrderParams): Promise<CreateOrderResponse> {
    const preview = await this.client.orders.preview({ request: order });
    const p = preview.order;
    const samePrice = Math.abs(Number(p.price?.value) - Number(order.price!.value)) < 1e-9;
    if (p.intent !== order.intent || !samePrice || Number(p.quantity) > Number(order.quantity)) {
      throw new Error(
        `preview mismatch, order NOT placed: sent ${order.intent} ${order.quantity}@${order.price!.value}, ` +
          `exchange read ${p.intent} ${p.quantity}@${p.price?.value}`,
      );
    }
    return this.client.orders.create(order);
  }

  async buy(m: SlotMarket, d: Decision, stakeUsd: number): Promise<Fill | null> {
    const quantity = Math.floor((stakeUsd / d.price) * 100) / 100;
    if (quantity <= 0) return null;
    const intent: OrderIntent = d.side === "UP" ? "ORDER_INTENT_BUY_LONG" : "ORDER_INTENT_BUY_SHORT";
    const resp = await this.placeChecked(buildOrder(m.slug, intent, yesPriceFor(d.side, d.price), quantity));
    const s = summarizeExecutions(resp, d.side);
    if (s.shares <= 0) return null;
    return { price: s.notional / s.shares, shares: s.shares, costUsd: s.notional + s.commission, orderId: resp.id };
  }

  async sell(o: SellOrder): Promise<SellFill | null> {
    const quantity = Math.floor(o.shares * 100) / 100;
    if (quantity <= 0) return null;
    const intent: OrderIntent = o.side === "UP" ? "ORDER_INTENT_SELL_LONG" : "ORDER_INTENT_SELL_SHORT";
    const resp = await this.placeChecked(buildOrder(o.marketSlug, intent, yesPriceFor(o.side, o.price), quantity));
    const s = summarizeExecutions(resp, o.side);
    if (s.shares <= 0) return null;
    return { price: s.notional / s.shares, shares: s.shares, proceedsUsd: s.notional - s.commission, orderId: resp.id };
  }

  credit(): void {
    // Polymarket US settles positions to your cash balance automatically.
  }
}
