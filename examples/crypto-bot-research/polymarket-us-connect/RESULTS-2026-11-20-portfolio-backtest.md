# Portfolio Backtest from $1,000 (2026-11-20)

`python -m pmus_recorder backtest` (`pmus_recorder/portfolio_backtest.py`)

**Summary**
- **Holdout (9 days not used to choose any setting):** $1,000 grew to **$3,545**, about **$283/day**. Every day was profitable and the worst day made **$123**.
  - The **middle day was about $165**. 2026-11-17 alone made $1,014, from arbitrage pairs whose close landed between the two opens, so both legs paid.
- **Under every stress test on its own** (1¢ slippage per leg, fees ×1.5, a 25-contract cap, or the XRP bot losing 1 trade in 30), the holdout still made **$141–261/day**.
  - **With all stresses together it made $91/day**, just under the $100 target.
- **The dev rows are in-sample.** The settings were chosen on those dates, so their numbers are optimistic. Before 2026-10-15 there are few markets in the data.
- **Not yet proven:** order size, and whether both arbitrage legs really fill at once. The live arbitrage paper test checks that.

Bots: arbitrage repeat (all coins) + XRP 1h leader. At most 50 contracts per trade, 5% of the balance per bet, 10% per arbitrage buy, winnings reinvested.

**Dev** dates are where the settings were chosen (in-sample, optimistic). **Holdout** dates were never used to choose. Each period is replayed from a fresh $1,000.

| Scenario | All 45 days: end balance | $/day | Holdout: end balance | $/day | Worst holdout day | Holdout days positive |
|---|---|---|---|---|---|---|
| base | $9,351 | $199 | $3,545 | $283 | $123 | 100% |
| slippage 1c/leg | $7,454 | $154 | $3,120 | $236 | $83 | 100% |
| fees x1.5 | $8,651 | $182 | $3,346 | $261 | $114 | 100% |
| 25-contract cap | $5,176 | $99 | $2,273 | $141 | $61 | 100% |
| 1 loss in 30 (XRP) | $8,501 | $179 | $3,245 | $249 | $73 | 100% |
| all stresses | $3,480 | $59 | $1,820 | $91 | $14 | 100% |

| Bot alone (base) | All 45 days: end balance | $/day | Holdout $/day | Trades (all) | Avg contracts |
|---|---|---|---|---|---|
| arb_repeat | $7,421 | $153 | $211 | 1641 | 50 |
| xrp_1h_leader | $2,930 | $52 | $72 | 513 | 50 |

## Day by day (base scenario, one $1,000 account over all 45 days)

| Date (UTC) | Period | Trades | Contracts | Arbitrage P&L | XRP P&L | Day P&L | Balance |
|---|---|---|---|---|---|---|---|
| 2026-10-09 | dev | 2 | 100 | $+0.99 | $+0.00 | $+0.99 | $1,000.99 |
| 2026-10-11 | dev | 1 | 50 | $+0.36 | $+0.00 | $+0.36 | $1,001.35 |
| 2026-10-12 | dev | 2 | 100 | $+0.72 | $+0.00 | $+0.72 | $1,002.07 |
| 2026-10-13 | dev | 2 | 100 | $+1.17 | $+0.00 | $+1.17 | $1,003.25 |
| 2026-10-14 | dev | 1 | 50 | $+0.72 | $+0.00 | $+0.72 | $1,003.97 |
| 2026-10-15 | dev | 9 | 450 | $+16.54 | $+17.06 | $+33.60 | $1,037.57 |
| 2026-10-16 | dev | 57 | 2850 | $+64.78 | $+30.98 | $+95.76 | $1,133.33 |
| 2026-10-17 | dev | 41 | 2050 | $+30.11 | $+10.45 | $+40.56 | $1,173.88 |
| 2026-10-18 | dev | 33 | 1650 | $+21.08 | $+28.26 | $+49.34 | $1,223.22 |
| 2026-10-19 | dev | 26 | 1300 | $+9.05 | $+20.45 | $+29.50 | $1,252.72 |
| 2026-10-20 | dev | 41 | 2050 | $+32.94 | $+20.91 | $+53.85 | $1,306.57 |
| 2026-10-21 | dev | 41 | 2050 | $+19.18 | $+20.18 | $+39.36 | $1,345.94 |
| 2026-10-22 | dev | 39 | 1950 | $+93.18 | $+15.00 | $+108.18 | $1,454.12 |
| 2026-10-23 | dev | 76 | 3800 | $+595.06 | $+18.63 | $+613.70 | $2,067.82 |
| 2026-10-24 | dev | 69 | 3450 | $+260.54 | $+20.42 | $+280.96 | $2,348.78 |
| 2026-10-25 | dev | 86 | 4300 | $+119.57 | $+22.73 | $+142.30 | $2,491.08 |
| 2026-10-26 | dev | 43 | 2150 | $+41.09 | $+112.55 | $+153.63 | $2,644.71 |
| 2026-10-27 | dev | 59 | 2950 | $+50.14 | $+14.99 | $+65.13 | $2,709.84 |
| 2026-10-28 | dev | 67 | 3350 | $+148.84 | $+25.04 | $+173.88 | $2,883.72 |
| 2026-10-29 | dev | 65 | 3250 | $+197.30 | $+69.83 | $+267.13 | $3,150.85 |
| 2026-10-30 | dev | 70 | 3500 | $+268.72 | $+44.41 | $+313.13 | $3,463.98 |
| 2026-10-31 | dev | 48 | 2400 | $+59.87 | $+33.32 | $+93.19 | $3,557.17 |
| 2026-11-01 | dev | 111 | 5550 | $+695.05 | $+24.59 | $+719.64 | $4,276.81 |
| 2026-11-02 | dev | 50 | 2500 | $+101.81 | $+58.95 | $+160.75 | $4,437.56 |
| 2026-11-03 | dev | 53 | 2650 | $+83.02 | $+48.79 | $+131.81 | $4,569.38 |
| 2026-11-04 | dev | 77 | 3850 | $+98.14 | $+55.25 | $+153.39 | $4,722.77 |
| 2026-11-05 | dev | 108 | 5400 | $+318.96 | $+65.35 | $+384.30 | $5,107.07 |
| 2026-11-06 | dev | 31 | 1550 | $+84.12 | $+100.49 | $+184.61 | $5,291.68 |
| 2026-11-07 | dev | 74 | 3700 | $+183.93 | $+38.77 | $+222.70 | $5,514.39 |
| 2026-11-08 | dev | 107 | 5350 | $+248.70 | $+94.94 | $+343.64 | $5,858.02 |
| 2026-11-09 | dev | 50 | 2500 | $+317.47 | $+92.08 | $+409.55 | $6,267.57 |
| 2026-11-10 | dev | 61 | 3050 | $+323.05 | $+112.98 | $+436.03 | $6,703.60 |
| 2026-11-11 | dev | 45 | 2250 | $+27.40 | $+88.40 | $+115.80 | $6,819.40 |
| 2026-11-12 | holdout | 48 | 2400 | $+60.28 | $+81.17 | $+141.45 | $6,960.85 |
| 2026-11-13 | holdout | 54 | 2700 | $+66.95 | $+61.97 | $+128.92 | $7,089.78 |
| 2026-11-14 | holdout | 81 | 4050 | $+119.34 | $+41.53 | $+160.88 | $7,250.65 |
| 2026-11-15 | holdout | 62 | 3100 | $+127.23 | $+45.08 | $+172.30 | $7,422.95 |
| 2026-11-16 | holdout | 37 | 1850 | $+76.34 | $+61.34 | $+137.68 | $7,560.63 |
| 2026-11-17 | holdout | 68 | 3400 | $+954.50 | $+59.94 | $+1,014.44 | $8,575.07 |
| 2026-11-18 | holdout | 63 | 3150 | $+47.51 | $+121.94 | $+169.45 | $8,744.52 |
| 2026-11-19 | holdout | 47 | 2350 | $+331.47 | $+82.11 | $+413.57 | $9,158.10 |
| 2026-11-20 | holdout | 49 | 2450 | $+123.95 | $+69.33 | $+193.28 | $9,351.38 |

Display prices carry no size, so fills of up to 50 contracts are assumed, not proven. Arbitrage assumes both legs fill at the quoted prices. Not financial advice.