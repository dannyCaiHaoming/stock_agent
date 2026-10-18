# 方向预测与动作评分（单边成本 10bp）

## 2025-01-02-codex-a

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | NO_TRADE | -12.827815 | decelerate(0.70)→decelerate ✅ | expand(0.65)→expand ✅ | underperform(0.60)→outperform ❌ | -4.55 | 31.93 | -40.75 |
| NEM | NO_TRADE | -14.067893 | decelerate(0.55)→decelerate ✅ | expand(0.55)→未出  | underperform(0.55)→outperform ❌ | 21.79 | 41.02 | -13.03 |
| INTC | NO_TRADE | -38.314837 | accelerate(0.55)→accelerate ✅ | expand(0.6)→expand ✅ | underperform(0.6)→outperform ❌ | 19.41 | 5.81 | -33.81 |
| UNH | NO_TRADE | 9.378358 | decelerate(0.55)→flat ❌ | contract(0.60)→flat ❌ | outperform(0.55)→underperform ❌ | 5.83 | -37.25 | -54.23 |
| PYPL | BUY | 35.958443 | accelerate(0.55)→decelerate ❌ | expand(0.65)→expand ✅ | outperform(0.55)→underperform ❌ | -24.48 | -22.2 | -37.47 |
| NOW | NO_TRADE | -19.568722 | decelerate(0.60)→decelerate ✅ | expand(0.65)→expand ✅ | underperform(0.55)→underperform ✅ | -10.31 | -13.84 | -38.34 |
| TGT | NO_TRADE | 13.737909 | decelerate(0.55)→decelerate ✅ | contract(0.55)→expand ❌ | underperform(0.60)→underperform ✅ | -30.28 | -29.22 | -37.18 |
| AMD | NO_TRADE | 1.528487 | accelerate(0.55)→accelerate ✅ | expand(0.6)→expand ✅ | outperform(0.52)→outperform ✅ | -7.66 | 3.39 | -39.63 |
| BLK | BUY | 14.691031 | decelerate(0.58)→decelerate ✅ | expand(0.56)→contract ❌ | outperform(0.55)→underperform ❌ | -10.92 | -2.46 | -23.74 |

- revenue_growth：命中 7/9，平均 Brier 0.205
- operating_margin：命中 5/8，平均 Brier 0.208
- relative_return_126d：命中 3/9，平均 Brier 0.28
- BUY 组 126 日净超额：n=2，均值 -12.33%，中位 -12.33%
- NO_TRADE 组 126 日净超额：n=7，均值 0.26%，中位 3.39%

## 2025-04-01-codex-a

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | NO_TRADE | 6.947343 | decelerate(0.65)→accelerate ❌ | expand(0.65)→expand ✅ | underperform(0.55)→outperform ❌ | 15.09 | 68.28 | -27.04 |
| ALB | NO_TRADE | 0.272834 | accelerate(0.55)→accelerate ✅ | expand(0.6)→expand ✅ | underperform(0.55)→outperform ❌ | -11.2 | 15.25 | -29.74 |
| AMAT | BUY | 12.509236 | accelerate(0.55)→flat ❌ | expand(0.60)→expand ✅ | underperform(0.55)→outperform ❌ | 8.48 | 12.89 | -21.37 |
| ADBE | BUY | 20.32092 | flat(0.55)→flat ✅ | expand(0.55)→contract ❌ | outperform(0.55)→underperform ❌ | -23.57 | -47.75 | -20.69 |
| NOW | NO_TRADE | -22.305974 | decelerate(0.60)→accelerate ❌ | expand(0.55)→expand ✅ | underperform(0.55)→underperform ✅ | 2.28 | -24.82 | -18.55 |
| UNH | NO_TRADE | 9.016352 | decelerate(0.6)→accelerate ❌ | contract(0.6)→contract ✅ | underperform(0.55)→underperform ✅ | -35.67 | -33.55 | -60.06 |
| ABBV | BUY | 9.350691 | accelerate(0.55)→accelerate ✅ | expand(0.6)→expand ✅ | outperform(0.55)→outperform ✅ | -1.75 | 19.37 | -16.74 |
| AMGN | NO_TRADE | 6.035034 | decelerate(0.65)→decelerate ✅ | expand(0.55)→expand ✅ | outperform(0.55)→underperform ❌ | 2.69 | -2.12 | -15.35 |
| INTU | BUY | 3.910382 | decelerate(0.7)→accelerate ❌ | expand(0.9)→expand ✅ | outperform(0.55)→underperform ❌ | 3.93 | -26.4 | -19.99 |

- revenue_growth：命中 4/9，平均 Brier 0.296
- operating_margin：命中 8/9，平均 Brier 0.164
- relative_return_126d：命中 3/9，平均 Brier 0.269
- BUY 组 126 日净超额：n=4，均值 -10.47%，中位 -6.75%
- NO_TRADE 组 126 日净超额：n=5，均值 4.61%，中位 -2.12%

## 2025-07-01-codex-a

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | BUY | 44.948203 | accelerate(0.60)→accelerate ✅ | expand(0.60)→expand ✅ | outperform(0.55)→outperform ✅ | 25.88 | 126.14 | -20.5 |
| INTC | NO_TRADE | 4.1 | decelerate(0.6)→accelerate ❌ | expand(0.75)→expand ✅ | underperform(0.58)→outperform ❌ | 34.37 | 47.04 | -19.05 |
| AMD | NO_TRADE | 3.540399 | decelerate(0.60)→flat ❌ | expand(0.55)→expand ✅ | outperform(0.55)→outperform ✅ | 6.41 | 42.01 | -25.05 |
| ADBE | BUY | 22.564233 | accelerate(0.55)→flat ❌ | expand(0.55)→expand ✅ | outperform(0.55)→underperform ❌ | -22.69 | -26.5 | -20.33 |
| NOW | NO_TRADE | -19.767945 | decelerate(0.62)→accelerate ❌ | expand(0.60)→expand ✅ | underperform(0.58)→underperform ✅ | -21.51 | -39.99 | -26.97 |
| INTU | NO_TRADE | 2.155779 | decelerate(0.6)→accelerate ❌ | expand(0.55)→expand ✅ | outperform(0.55)→underperform ❌ | -24.74 | -30.0 | -21.94 |
| HD | NO_TRADE | 3.624619 | decelerate(0.85)→decelerate ✅ | contract(0.65)→contract ✅ | underperform(0.55)→underperform ✅ | -0.79 | -16.76 | -21.5 |
| AVGO | BUY | 8.300304 | accelerate(0.55)→accelerate ✅ | expand(0.60)→expand ✅ | outperform(0.55)→outperform ✅ | 12.18 | 16.22 | -21.05 |
| BLK | NO_TRADE | -1.326886 | accelerate(0.65)→accelerate ✅ | contract(0.60)→contract ✅ | outperform(0.55)→underperform ❌ | 8.47 | -1.76 | -17.47 |

- revenue_growth：命中 4/9，平均 Brier 0.253
- operating_margin：命中 9/9，平均 Brier 0.159
- relative_return_126d：命中 5/9，平均 Brier 0.248
- BUY 组 126 日净超额：n=3，均值 38.62%，中位 16.22%
- NO_TRADE 组 126 日净超额：n=6，均值 0.09%，中位 -9.26%

