# 方向预测与动作评分（单边成本 10bp）

## 2025-01-02-codex-b

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| NEM | NO_TRADE | -19.103376 | accelerate(0.55)→decelerate ❌ | expand(0.55)→未出  | underperform(0.55)→outperform ❌ | 21.79 | 41.02 | -13.03 |
| MU | NO_TRADE | 12.87845 | decelerate(0.75)→decelerate ✅ | expand(0.55)→expand ✅ | underperform(0.55)→outperform ❌ | -4.55 | 31.93 | -40.75 |
| INTC | NO_TRADE | -29.377349 | decelerate(0.55)→accelerate ❌ | expand(0.55)→expand ✅ | underperform(0.65)→outperform ❌ | 19.41 | 5.81 | -33.81 |
| NOW | NO_TRADE | -11.35244 | decelerate(0.65)→decelerate ✅ | expand(0.60)→expand ✅ | underperform(0.55)→underperform ✅ | -10.31 | -13.84 | -38.34 |
| UNH | NO_TRADE | -8.08326 | decelerate(0.60)→flat ❌ | contract(0.55)→flat ❌ | underperform(0.60)→underperform ✅ | 5.83 | -37.25 | -54.23 |
| AMD | NO_TRADE | 0.35 | accelerate(0.55)→accelerate ✅ | expand(0.75)→expand ✅ | underperform(0.6)→outperform ❌ | -7.66 | 3.39 | -39.63 |
| PYPL | NO_TRADE | 2.375997 | decelerate(0.7)→decelerate ✅ | expand(0.6)→expand ✅ | outperform(0.55)→underperform ❌ | -24.28 | -22.0 | -37.47 |
| TGT | NO_TRADE | -11.256811 | decelerate(0.60)→decelerate ✅ | contract(0.60)→expand ❌ | underperform(0.60)→underperform ✅ | -30.28 | -29.22 | -37.18 |
| BLK | NO_TRADE | 2.738385 | accelerate(0.55)→decelerate ❌ | expand(0.55)→contract ❌ | outperform(0.52)→underperform ❌ | -10.72 | -2.26 | -23.74 |

- revenue_growth：命中 5/9，平均 Brier 0.212
- operating_margin：命中 5/8，平均 Brier 0.219
- relative_return_126d：命中 3/9，平均 Brier 0.276
- NO_TRADE 组 126 日净超额：n=9，均值 -2.49%，中位 -2.26%

## 2025-04-01-codex-b

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| ALB | NO_TRADE | -50.780402 | accelerate(0.65)→accelerate ✅ | expand(0.65)→expand ✅ | underperform(0.55)→outperform ❌ | -11.2 | 15.25 | -29.74 |
| MU | NO_TRADE | -1.530363 | decelerate(0.72)→accelerate ❌ | expand(0.58)→expand ✅ | underperform(0.55)→outperform ❌ | 15.09 | 68.28 | -27.04 |
| ADBE | NO_TRADE | 2.97 | flat(0.65)→flat ✅ | expand(0.60)→contract ❌ | underperform(0.55)→underperform ✅ | -23.37 | -47.55 | -20.69 |
| AMAT | BUY | 12.762284 | accelerate(0.58)→flat ❌ | expand(0.55)→expand ✅ | underperform(0.55)→outperform ❌ | 8.48 | 12.89 | -21.37 |
| NOW | NO_TRADE | -20.072778 | decelerate(0.65)→accelerate ❌ | expand(0.6)→expand ✅ | underperform(0.6)→underperform ✅ | 2.28 | -24.82 | -18.55 |
| UNH | NO_TRADE | -2.689579 | accelerate(0.6)→accelerate ✅ | contract(0.6)→contract ✅ | underperform(0.55)→underperform ✅ | -35.67 | -33.55 | -60.06 |
| INTU | NO_TRADE | -1.865944 | decelerate(0.75)→accelerate ❌ | expand(0.85)→expand ✅ | underperform(0.55)→underperform ✅ | 4.13 | -26.2 | -19.99 |
| ABBV | NO_TRADE | -7.52067 | accelerate(0.60)→accelerate ✅ | expand(0.55)→expand ✅ | outperform(0.55)→outperform ✅ | -1.55 | 19.58 | -16.74 |
| AMGN | NO_TRADE | -7.308203 | decelerate(0.65)→decelerate ✅ | expand(0.55)→expand ✅ | underperform(0.55)→underperform ✅ | 2.69 | -2.12 | -15.35 |

- revenue_growth：命中 5/9，平均 Brier 0.281
- operating_margin：命中 8/9，平均 Brier 0.179
- relative_return_126d：命中 6/9，平均 Brier 0.231
- BUY 组 126 日净超额：n=1，均值 12.89%，中位 12.89%
- NO_TRADE 组 126 日净超额：n=8，均值 -3.89%，中位 -13.47%

## 2025-07-01-codex-b

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | BUY | 22.837096 | decelerate(0.65)→accelerate ❌ | expand(0.55)→expand ✅ | outperform(0.55)→outperform ✅ | 25.88 | 126.14 | -20.5 |
| INTC | NO_TRADE | -63.189111 | decelerate(0.6)→accelerate ❌ | expand(0.8)→expand ✅ | underperform(0.6)→outperform ❌ | 34.37 | 47.04 | -19.05 |
| AMD | NO_TRADE | -9.731936 | accelerate(0.60)→flat ❌ | expand(0.60)→expand ✅ | outperform(0.55)→outperform ✅ | 6.41 | 42.01 | -25.05 |
| ADBE | BUY | 20.132631 | flat(0.55)→flat ✅ | expand(0.60)→expand ✅ | underperform(0.55)→underperform ✅ | -22.69 | -26.5 | -20.33 |
| NOW | NO_TRADE | -19.958811 | flat(0.60)→accelerate ❌ | expand(0.60)→expand ✅ | underperform(0.60)→underperform ✅ | -21.51 | -39.99 | -26.97 |
| INTU | NO_TRADE | -5.08609 | decelerate(0.55)→accelerate ❌ | expand(0.60)→expand ✅ | outperform(0.55)→underperform ❌ | -24.74 | -30.0 | -21.94 |
| HD | NO_TRADE | -9.825093 | decelerate(0.75)→decelerate ✅ | contract(0.70)→contract ✅ | underperform(0.58)→underperform ✅ | -0.79 | -16.76 | -21.5 |
| AVGO | NO_TRADE | -8.555907 | decelerate(0.6)→accelerate ❌ | expand(0.65)→expand ✅ | underperform(0.55)→outperform ❌ | 12.38 | 16.42 | -21.05 |
| BLK | NO_TRADE | -3.564886 | accelerate(0.65)→accelerate ✅ | expand(0.55)→contract ❌ | outperform(0.55)→underperform ❌ | 8.47 | -1.76 | -17.47 |

- revenue_growth：命中 3/9，平均 Brier 0.284
- operating_margin：命中 8/9，平均 Brier 0.155
- relative_return_126d：命中 5/9，平均 Brier 0.246
- BUY 组 126 日净超额：n=2，均值 49.82%，中位 49.82%
- NO_TRADE 组 126 日净超额：n=7，均值 2.42%，中位 -1.76%

