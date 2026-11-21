import { join } from "node:path";
import { LiveBroker, PaperBroker, publicClob, type Broker } from "./broker.js";
import { describeConfig, loadConfig, loadDotEnv } from "./config.js";
import { Engine } from "./engine.js";
import { Ledger, log, replayLedger, warn } from "./log.js";
import { Gamma } from "./markets.js";
import { PriceTape, startBrtiFeed, startChainlinkFeed } from "./priceFeed.js";
import { RiskManager } from "./risk.js";
import { UsLiveBroker } from "./usBroker.js";
import { UsGateway, UsVenue } from "./usVenue.js";
import { GlobalVenue, type Venue } from "./venue.js";

async function main(): Promise<void> {
  loadDotEnv();
  const cfg = loadConfig();
  log("starting", describeConfig(cfg));

  const ledger = new Ledger(cfg.stateDir);
  const paperCash = replayLedger(ledger.read(), "paper", Date.now()).cashDeltaUsd;

  const broker: Broker =
    cfg.mode === "paper"
      ? new PaperBroker(cfg.paperBankrollUsd + paperCash, cfg.feeTheta)
      : cfg.venue === "us"
        ? new UsLiveBroker(cfg)
        : await LiveBroker.connect(cfg);
  const venueLabel = cfg.venue === "us" ? "Polymarket US" : "Polymarket (global)";
  log(`strategy ${cfg.strategy} on ${venueLabel} BTC ${cfg.marketWindow} markets`);
  log(`${cfg.mode} broker ready, bankroll $${(await broker.bankrollUsd()).toFixed(2)}`);

  const tape = new PriceTape();
  let venue: Venue;
  let feed: { stop: () => void };
  if (cfg.venue === "us") {
    const gw = new UsGateway(cfg.usGatewayHost);
    venue = new UsVenue(gw, cfg.marketWindow);
    feed = startBrtiFeed(tape, gw);
  } else {
    venue = new GlobalVenue(new Gamma(cfg.gammaHost, cfg.marketWindow), publicClob(cfg));
    feed = startChainlinkFeed(tape);
  }
  const engine = new Engine({
    cfg,
    tape,
    venue,
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
