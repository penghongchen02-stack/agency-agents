import { join } from "node:path";
import { LiveBroker, PaperBroker, publicClob, type Broker } from "./broker.js";
import { describeConfig, loadConfig, loadDotEnv } from "./config.js";
import { Engine } from "./engine.js";
import { Ledger, log, replayLedger, warn } from "./log.js";
import { Gamma } from "./markets.js";
import { PriceTape, startChainlinkFeed } from "./priceFeed.js";
import { RiskManager } from "./risk.js";

async function main(): Promise<void> {
  loadDotEnv();
  const cfg = loadConfig();
  log("starting", describeConfig(cfg));

  const ledger = new Ledger(cfg.stateDir);
  const paperCash = replayLedger(ledger.read(), "paper", Date.now()).cashDeltaUsd;

  const broker: Broker =
    cfg.mode === "live"
      ? await LiveBroker.connect(cfg)
      : new PaperBroker(cfg.paperBankrollUsd + paperCash);
  log(`strategy ${cfg.strategy} on BTC ${cfg.marketWindow} markets`);
  log(`${cfg.mode} broker ready, bankroll $${(await broker.bankrollUsd()).toFixed(2)}`);

  const tape = new PriceTape();
  const feed = startChainlinkFeed(tape);
  const engine = new Engine({
    cfg,
    tape,
    gamma: new Gamma(cfg.gammaHost, cfg.marketWindow),
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
