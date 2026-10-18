# 方向预测与动作评分（单边成本 10bp）

## 2025-07-01-claude-a

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | NO_TRADE | 7.0 | decelerate(0.55)→accelerate ❌ | expand(0.55)→expand ✅ | underperform(0.55)→outperform ❌ | 26.08 | 126.34 | -20.5 |
| INTC | NO_TRADE | -30.3 | decelerate(0.5)→accelerate ❌ | expand(0.8)→expand ✅ | underperform(0.55)→outperform ❌ | 34.37 | 47.04 | -19.05 |
| ADBE | NO_TRADE | -5.5 | decelerate(0.65)→flat ❌ | contract(0.45)→expand ❌ | underperform(0.55)→underperform ✅ | -22.49 | -26.3 | -20.33 |
| AMD | NO_TRADE | 10.2 | decelerate(0.75)→flat ❌ | expand(0.5)→expand ✅ | underperform(0.55)→outperform ❌ | 6.41 | 42.01 | -25.05 |
| INTU | BUY | 10.2 | accelerate(0.55)→accelerate ✅ | expand(0.6)→expand ✅ | outperform(0.5)→underperform ❌ | -24.939999999999998 | -30.2 | -21.94 |
| HD | NO_TRADE | -4.3 | decelerate(0.6)→decelerate ✅ | contract(0.6)→contract ✅ | underperform(0.55)→underperform ✅ | -0.79 | -16.76 | -21.5 |
| NOW | NO_TRADE | -4.4 | decelerate(0.45)→accelerate ❌ | expand(0.6)→expand ✅ | outperform(0.5)→underperform ❌ | -21.51 | -39.99 | -26.97 |
| AVGO | NO_TRADE | -37.0 | decelerate(0.6)→accelerate ❌ | expand(0.75)→expand ✅ | underperform(0.55)→outperform ❌ | 12.38 | 16.42 | -21.05 |
| BLK | NO_TRADE | -7.3 | flat(0.4)→accelerate ❌ | contract(0.6)→contract ✅ | outperform(0.55)→underperform ❌ | 8.47 | -1.76 | -17.47 |

- revenue_growth：命中 2/9，平均 Brier 0.291
- operating_margin：命中 8/9，平均 Brier 0.155
- relative_return_126d：命中 2/9，平均 Brier 0.269
- BUY 组 126 日净超额：n=1，均值 -30.2%，中位 -30.2%
- NO_TRADE 组 126 日净超额：n=8，均值 18.38%，中位 7.33%

## 2025-07-01-claude-b

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | BUY | -0.2 | decelerate(0.55)→accelerate ❌ | expand(0.65)→expand ✅ | outperform(0.5)→outperform ✅ | 25.88 | 126.14 | -20.5 |
| INTC | NO_TRADE | 10.0 | decelerate(0.65)→accelerate ❌ | expand(0.85)→expand ✅ | underperform(0.55)→outperform ❌ | 34.37 | 47.04 | -19.05 |
| AMD | NO_TRADE | -30.2 | decelerate(0.7)→flat ❌ | flat(0.45)→expand ❌ | underperform(0.55)→outperform ❌ | 6.41 | 42.01 | -25.05 |
| ADBE | NO_TRADE | -2.5 | decelerate(0.7)→flat ❌ | contract(0.5)→expand ❌ | underperform(0.55)→underperform ✅ | -22.49 | -26.3 | -20.33 |
| NOW | NO_TRADE | -32.3 | flat(0.45)→accelerate ❌ | expand(0.55)→expand ✅ | outperform(0.5)→underperform ❌ | -21.51 | -39.99 | -26.97 |
| INTU | BUY | 1.1 | flat(0.4)→accelerate ❌ | expand(0.6)→expand ✅ | outperform(0.5)→underperform ❌ | -24.939999999999998 | -30.2 | -21.94 |
| AVGO | NO_TRADE | -33.6 | decelerate(0.5)→accelerate ❌ | expand(0.65)→expand ✅ | underperform(0.55)→outperform ❌ | 12.38 | 16.42 | -21.05 |
| HD | NO_TRADE | -3.2 | decelerate(0.85)→decelerate ✅ | contract(0.7)→contract ✅ | underperform(0.5)→underperform ✅ | -0.79 | -16.76 | -21.5 |
| BLK | NO_TRADE | -0.7 | accelerate(0.6)→accelerate ✅ | contract(0.7)→contract ✅ | underperform(0.55)→underperform ✅ | 8.47 | -1.76 | -17.47 |

- revenue_growth：命中 2/9，平均 Brier 0.278
- operating_margin：命中 7/9，平均 Brier 0.14
- relative_return_126d：命中 4/9，平均 Brier 0.257
- BUY 组 126 日净超额：n=2，均值 47.97%，中位 47.97%
- NO_TRADE 组 126 日净超额：n=7，均值 2.95%，中位 -1.76%

## 2025-07-01-claude-c

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | BUY | 5.2 | decelerate(0.7)→accelerate ❌ | expand(0.6)→expand ✅ | outperform(0.55)→outperform ✅ | 25.88 | 126.14 | -20.5 |
| INTC | NO_TRADE | -54.8 | decelerate(0.7)→accelerate ❌ | expand(0.9)→expand ✅ | underperform(0.55)→outperform ❌ | 34.37 | 47.04 | -19.05 |
| AMD | NO_TRADE | 2.8 | decelerate(0.8)→flat ❌ | expand(0.6)→expand ✅ | underperform(0.55)→outperform ❌ | 6.41 | 42.01 | -25.05 |
| ADBE | NO_TRADE | 7.7 | decelerate(0.7)→flat ❌ | contract(0.5)→expand ❌ | underperform(0.55)→underperform ✅ | -22.49 | -26.3 | -20.33 |
| NOW | NO_TRADE | 5.5 | decelerate(0.6)→accelerate ❌ | expand(0.6)→expand ✅ | underperform(0.55)→underperform ✅ | -21.51 | -39.99 | -26.97 |
| INTU | NO_TRADE | 0.9 | decelerate(0.5)→accelerate ❌ | expand(0.5)→expand ✅ | underperform(0.5)→underperform ✅ | -24.74 | -30.0 | -21.94 |
| HD | NO_TRADE | -8.6 | decelerate(0.85)→decelerate ✅ | contract(0.6)→contract ✅ | underperform(0.55)→underperform ✅ | -0.79 | -16.76 | -21.5 |
| AVGO | NO_TRADE | -16.4 | accelerate(0.35)→accelerate ✅ | contract(0.5)→expand ❌ | underperform(0.55)→outperform ❌ | 12.38 | 16.42 | -21.05 |
| BLK | NO_TRADE | -10.6 | decelerate(0.45)→accelerate ❌ | contract(0.5)→contract ✅ | underperform(0.5)→underperform ✅ | 8.47 | -1.76 | -17.47 |

- revenue_growth：命中 2/9，平均 Brier 0.374
- operating_margin：命中 7/9，平均 Brier 0.183
- relative_return_126d：命中 6/9，平均 Brier 0.246
- BUY 组 126 日净超额：n=1，均值 126.14%，中位 126.14%
- NO_TRADE 组 126 日净超额：n=8，均值 -1.17%，中位 -9.26%

