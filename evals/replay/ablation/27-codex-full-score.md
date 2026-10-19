# 方向预测与动作评分（单边成本 10bp）

## 2025-01-02-codex-full

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | NO_TRADE | -3.180963 | decelerate(0.65)→decelerate ✅ | expand(0.55)→expand ✅ | underperform(0.6)→outperform ❌ | -4.55 | 31.93 | -40.75 |
| INTC | NO_TRADE | 18.84 | accelerate(0.55)→accelerate ✅ | expand(0.55)→expand ✅ | underperform(0.55)→outperform ❌ | 19.41 | 5.81 | -33.81 |
| NEM | NO_TRADE | -6.52 | decelerate(0.60)→decelerate ✅ | expand(0.55)→未出  | underperform(0.60)→outperform ❌ | 21.79 | 41.02 | -13.03 |
| UNH | NO_TRADE | -3.740954 | decelerate(0.55)→flat ❌ | contract(0.65)→flat ❌ | underperform(0.60)→underperform ✅ | 5.83 | -37.25 | -54.23 |
| PYPL | NO_TRADE | 2.82 | decelerate(0.58)→decelerate ✅ | contract(0.52)→expand ❌ | underperform(0.53)→underperform ✅ | -24.28 | -22.0 | -37.47 |
| NOW | NO_TRADE | -5.69 | decelerate(0.60)→decelerate ✅ | expand(0.55)→expand ✅ | underperform(0.55)→underperform ✅ | -10.31 | -13.84 | -38.34 |
| AMD | NO_TRADE | 0.37 | accelerate(0.55)→accelerate ✅ | expand(0.65)→expand ✅ | underperform(0.65)→outperform ❌ | -7.66 | 3.39 | -39.63 |
| TGT | NO_TRADE | -24.076985 | decelerate(0.55)→decelerate ✅ | contract(0.6)→expand ❌ | underperform(0.55)→underperform ✅ | -30.28 | -29.22 | -37.18 |
| BLK | NO_TRADE | 11.302363 | decelerate(0.55)→decelerate ✅ | contract(0.52)→contract ✅ | underperform(0.55)→underperform ✅ | -10.72 | -2.26 | -23.74 |

- revenue_growth：命中 8/9，平均 Brier 0.192
- operating_margin：命中 5/8，平均 Brier 0.252
- relative_return_126d：命中 5/9，平均 Brier 0.27
- NO_TRADE 组 126 日净超额：n=9，均值 -2.49%，中位 -2.26%

## 2025-04-01-codex-full

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| ALB | NO_TRADE | -47.786229 | accelerate(0.62)→accelerate ✅ | expand(0.7)→expand ✅ | underperform(0.6)→outperform ❌ | -11.2 | 15.25 | -29.74 |
| AMAT | NO_TRADE | 1.759314 | decelerate(0.55)→flat ❌ | contract(0.55)→expand ❌ | underperform(0.55)→outperform ❌ | 8.68 | 13.09 | -21.37 |
| MU | BUY | 18.1 | decelerate(0.6)→accelerate ❌ | expand(0.55)→expand ✅ | underperform(0.55)→outperform ❌ | 14.89 | 68.08 | -27.04 |
| ADBE | BUY | 13.89 | flat(0.55)→flat ✅ | expand(0.55)→contract ❌ | underperform(0.55)→underperform ✅ | -23.57 | -47.75 | -20.69 |
| NOW | NO_TRADE | -30.5 | decelerate(0.60)→accelerate ❌ | expand(0.55)→expand ✅ | underperform(0.60)→underperform ✅ | 2.28 | -24.82 | -18.55 |
| UNH | NO_TRADE | -10.453 | accelerate(0.55)→accelerate ✅ | contract(0.60)→contract ✅ | underperform(0.55)→underperform ✅ | -35.67 | -33.55 | -60.06 |
| ABBV | NO_TRADE | -3.48 | accelerate(0.60)→accelerate ✅ | expand(0.50)→expand ✅ | outperform(0.52)→outperform ✅ | -1.55 | 19.57 | -16.74 |
| INTU | NO_TRADE | 1.10 | decelerate(0.65)→accelerate ❌ | expand(0.60)→expand ✅ | underperform(0.55)→underperform ✅ | 4.13 | -26.2 | -19.99 |
| AMGN | NO_TRADE | -14.5 | decelerate(0.60)→decelerate ✅ | flat(0.55)→expand ❌ | underperform(0.52)→underperform ✅ | 2.69 | -2.12 | -15.35 |

- revenue_growth：命中 5/9，平均 Brier 0.257
- operating_margin：命中 6/9，平均 Brier 0.219
- relative_return_126d：命中 6/9，平均 Brier 0.244
- BUY 组 126 日净超额：n=2，均值 10.16%，中位 10.16%
- NO_TRADE 组 126 日净超额：n=7，均值 -5.54%，中位 -2.12%

## 2025-07-01-codex-full

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| INTC | NO_TRADE | -57.828464 | decelerate(0.55)→accelerate ❌ | contract(0.55)→expand ❌ | underperform(0.60)→outperform ❌ | 34.37 | 47.04 | -19.05 |
| MU | BUY | 25.830978 | decelerate(0.55)→accelerate ❌ | expand(0.6)→expand ✅ | outperform(0.55)→outperform ✅ | 25.88 | 126.14 | -20.5 |
| AMD | NO_TRADE | -12.55 | decelerate(0.55)→flat ❌ | expand(0.55)→expand ✅ | underperform(0.55)→outperform ❌ | 6.41 | 42.01 | -25.05 |
| ADBE | NO_TRADE | 1.5 | flat(0.60)→flat ✅ | expand(0.55)→expand ✅ | underperform(0.55)→underperform ✅ | -22.49 | -26.3 | -20.33 |
| NOW | NO_TRADE | -14.3 | flat(0.55)→accelerate ❌ | expand(0.6)→expand ✅ | underperform(0.55)→underperform ✅ | -21.51 | -39.99 | -26.97 |
| INTU | NO_TRADE | -11.993349 | decelerate(0.6)→accelerate ❌ | flat(0.5)→expand ❌ | underperform(0.55)→underperform ✅ | -24.74 | -30.0 | -21.94 |
| HD | NO_TRADE | -7.29 | decelerate(0.60)→decelerate ✅ | contract(0.55)→contract ✅ | underperform(0.60)→underperform ✅ | -0.79 | -16.76 | -21.5 |
| BLK | BUY | 8.01 | accelerate(0.50)→accelerate ✅ | contract(0.55)→contract ✅ | outperform(0.53)→underperform ❌ | 8.27 | -1.96 | -17.47 |
| AVGO | NO_TRADE | -18.72 | accelerate(0.55)→accelerate ✅ | expand(0.55)→expand ✅ | underperform(0.55)→outperform ❌ | 12.38 | 16.42 | -21.05 |

- revenue_growth：命中 4/9，平均 Brier 0.26
- operating_margin：命中 7/9，平均 Brier 0.209
- relative_return_126d：命中 5/9，平均 Brier 0.246
- BUY 组 126 日净超额：n=2，均值 62.09%，中位 62.09%
- NO_TRADE 组 126 日净超额：n=7，均值 -1.08%，中位 -16.76%

