# 方向预测与动作评分（单边成本 10bp）

## 2025-01-02-codex-b-gpt-6.1-sol

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | NO_TRADE | 2.764417 | decelerate(0.85)→decelerate ✅ | expand(0.8)→expand ✅ | underperform(0.6)→outperform ❌ | -4.55 | 31.93 | -40.75 |
| INTC | NO_TRADE | -16.180534 | accelerate(0.55)→accelerate ✅ | expand(0.6)→expand ✅ | underperform(0.6)→outperform ❌ | 19.41 | 5.81 | -33.81 |
| NEM | NO_TRADE | -2.244258 | decelerate(0.8)→decelerate ✅ | expand(0.6)→未出  | underperform(0.55)→outperform ❌ | 21.79 | 41.02 | -13.03 |
| UNH | NO_TRADE | -0.113758 | accelerate(0.6)→flat ❌ | expand(0.55)→flat ❌ | underperform(0.6)→underperform ✅ | 5.83 | -37.25 | -54.23 |
| NOW | NO_TRADE | -3.813837 | decelerate(0.6)→decelerate ✅ | expand(0.7)→expand ✅ | underperform(0.55)→underperform ✅ | -10.31 | -13.84 | -38.34 |
| PYPL | BUY | 11.002585 | decelerate(0.6)→decelerate ✅ | expand(0.7)→expand ✅ | outperform(0.55)→underperform ❌ | -24.48 | -22.2 | -37.47 |
| AMD | NO_TRADE | -2.801956 | accelerate(0.65)→accelerate ✅ | expand(0.75)→expand ✅ | underperform(0.55)→outperform ❌ | -7.66 | 3.39 | -39.63 |
| TGT | NO_TRADE | -6.685977 | flat(0.55)→decelerate ❌ | contract(0.55)→expand ❌ | underperform(0.6)→underperform ✅ | -30.28 | -29.22 | -37.18 |
| BLK | BUY | 8.17095 | accelerate(0.55)→decelerate ❌ | expand(0.6)→contract ❌ | outperform(0.55)→underperform ❌ | -10.92 | -2.46 | -23.74 |

- revenue_growth：命中 6/9，平均 Brier 0.186
- operating_margin：命中 5/8，平均 Brier 0.176
- relative_return_126d：命中 3/9，平均 Brier 0.273
- BUY 组 126 日净超额：n=2，均值 -12.33%，中位 -12.33%
- NO_TRADE 组 126 日净超额：n=7，均值 0.26%，中位 3.39%

## 2025-04-01-codex-b-gpt-6.1-sol

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | NO_TRADE | 0.689892 | decelerate(0.75)→accelerate ❌ | expand(0.65)→expand ✅ | outperform(0.55)→outperform ✅ | 15.09 | 68.28 | -27.04 |
| AMAT | BUY | 19.748893 | flat(0.5)→flat ✅ | expand(0.65)→expand ✅ | outperform(0.55)→outperform ✅ | 8.48 | 12.89 | -21.37 |
| ALB | NO_TRADE | 14.425108 | accelerate(0.75)→accelerate ✅ | expand(0.8)→expand ✅ | underperform(0.6)→outperform ❌ | -11.2 | 15.25 | -29.74 |
| ADBE | NO_TRADE | 11.358509 | flat(0.6)→flat ✅ | expand(0.55)→contract ❌ | underperform(0.55)→underperform ✅ | -23.37 | -47.55 | -20.69 |
| UNH | NO_TRADE | 1.890731 | accelerate(0.7)→accelerate ✅ | flat(0.5)→contract ❌ | underperform(0.55)→underperform ✅ | -35.67 | -33.55 | -60.06 |
| NOW | NO_TRADE | -7.221674 | decelerate(0.65)→accelerate ❌ | expand(0.7)→expand ✅ | underperform(0.55)→underperform ✅ | 2.28 | -24.82 | -18.55 |
| ABBV | BUY | 3.443802 | accelerate(0.65)→accelerate ✅ | expand(0.55)→expand ✅ | outperform(0.55)→outperform ✅ | -1.75 | 19.38 | -16.74 |
| INTU | NO_TRADE | 4.35663 | decelerate(0.65)→accelerate ❌ | expand(0.75)→expand ✅ | underperform(0.55)→underperform ✅ | 4.13 | -26.2 | -19.99 |
| AMGN | NO_TRADE | 3.26707 | decelerate(0.75)→decelerate ✅ | expand(0.7)→expand ✅ | underperform(0.55)→underperform ✅ | 2.69 | -2.12 | -15.35 |

- revenue_growth：命中 6/9，平均 Brier 0.239
- operating_margin：命中 7/9，平均 Brier 0.142
- relative_return_126d：命中 8/9，平均 Brier 0.22
- BUY 组 126 日净超额：n=2，均值 16.13%，中位 16.13%
- NO_TRADE 组 126 日净超额：n=7，均值 -7.24%，中位 -24.82%

## 2025-07-01-codex-b-gpt-6.1-sol

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| AMD | NO_TRADE | -0.234003 | decelerate(0.6)→flat ❌ | expand(0.55)→expand ✅ | underperform(0.55)→outperform ❌ | 6.41 | 42.01 | -25.05 |
| INTC | NO_TRADE | -14.920686 | decelerate(0.6)→accelerate ❌ | expand(0.85)→expand ✅ | underperform(0.6)→outperform ❌ | 34.37 | 47.04 | -19.05 |
| MU | BUY | 12.644594 | decelerate(0.65)→accelerate ❌ | expand(0.75)→expand ✅ | outperform(0.55)→outperform ✅ | 25.88 | 126.14 | -20.5 |
| ADBE | NO_TRADE | 17.7142 | decelerate(0.65)→flat ❌ | expand(0.6)→expand ✅ | underperform(0.6)→underperform ✅ | -22.49 | -26.3 | -20.33 |
| NOW | NO_TRADE | -14.692873 | flat(0.6)→accelerate ❌ | expand(0.65)→expand ✅ | underperform(0.55)→underperform ✅ | -21.51 | -39.99 | -26.97 |
| INTU | BUY | 11.544279 | accelerate(0.6)→accelerate ✅ | expand(0.65)→expand ✅ | outperform(0.55)→underperform ❌ | -24.94 | -30.2 | -21.94 |
| HD | NO_TRADE | -2.200254 | decelerate(0.8)→decelerate ✅ | flat(0.55)→contract ❌ | underperform(0.55)→underperform ✅ | -0.79 | -16.76 | -21.5 |
| AVGO | NO_TRADE | 1.044179 | accelerate(0.6)→accelerate ✅ | expand(0.75)→expand ✅ | underperform(0.55)→outperform ❌ | 12.38 | 16.42 | -21.05 |
| BLK | NO_TRADE | 0.886882 | accelerate(0.6)→accelerate ✅ | contract(0.65)→contract ✅ | underperform(0.55)→underperform ✅ | 8.47 | -1.76 | -17.47 |

- revenue_growth：命中 4/9，平均 Brier 0.272
- operating_margin：命中 8/9，平均 Brier 0.131
- relative_return_126d：命中 5/9，平均 Brier 0.249
- BUY 组 126 日净超额：n=2，均值 47.97%，中位 47.97%
- NO_TRADE 组 126 日净超额：n=7，均值 2.95%，中位 -1.76%

