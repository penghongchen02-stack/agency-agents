import { join } from "node:path";
import { LiveBroker, PaperBroker, publicClob, type Broker } from "./broker.js";
import { describeConfig, loadConfig, loadDotEnv } from "./config.js";
import { Engine } from "./engine.js";
import { Ledger, log, warn } from "./log.js";
import { Gamma } from "./markets.js";
import { PriceTape, startChainlinkFeed } from "./priceFeed.js";
import { RiskManager } from "./risk.js";

async function main(): Promise<void> {
  loadDotEnv();
  const cfg = loadConfig();
  log("starting", describeConfig(cfg));

  const ledger = new Ledger(cfg.stateDir);
  const settledPnl = ledger
    .read()
    .reduce((sum, e) => (e.kind === "settle" && e.mode === "paper" ? sum + e.pnlUsd : sum), 0);
  const unsettledCost = (() => {
    const entries = ledger.read().filter((e) => e.mode === "paper");
    const settled = new Set(entries.filter((e) => e.kind === "settle").map((e) => `${e.slug}:${e.side}`));
    return entries
      .filter((e) => e.kind === "entry" && !settled.has(`${e.slug}:${e.side}`))
      .reduce((s, e) => s + e.costUsd, 0);
  })();

  const broker: Broker =
    cfg.mode === "live"
      ? await LiveBroker.connect(cfg)
      : new PaperBroker(cfg.paperBankrollUsd + settledPnl - unsettledCost);
  log(`${cfg.mode} broker ready, bankroll $${(await broker.bankrollUsd()).toFixed(2)}`);

  const tape = new PriceTape();
  const feed = startChainlinkFeed(tape);
  const engine = new Engine({
    cfg,
    tape,
    gamma: new Gamma(cfg.gammaHost),
    clob: publicClob(cfg),
    broker,
    risk: new RiskManager(cfg, join(process.cwd(), "STOP")),
    ledger,
  });

  const timer = setInterval(() => void engine.tick(), cfg.pollMs);
  const shutdown = () => {
    log("shutting down (open positions stay on the book until they resolve)");
    clearInterval(timer);
    feed.stop();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  warn("fatal", err);
  process.exit(1);
});
