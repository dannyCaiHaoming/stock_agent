# 方向预测与动作评分（单边成本 10bp）

## 2025-01-02-codex-c

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | BUY | 7.892615 | decelerate(0.6)→decelerate ✅ | expand(0.65)→expand ✅ | outperform(0.55)→outperform ✅ | -4.75 | 31.73 | -40.75 |
| NEM | BUY | 9.070379 | accelerate(0.58)→decelerate ❌ | expand(0.56)→未出  | outperform(0.52)→outperform ✅ | 21.59 | 40.82 | -13.03 |
| INTC | NO_TRADE | 3.336734 | decelerate(0.60)→accelerate ❌ | contract(0.60)→expand ❌ | underperform(0.60)→outperform ❌ | 19.41 | 5.81 | -33.81 |
| UNH | NO_TRADE | 2.425902 | accelerate(0.55)→flat ❌ | contract(0.60)→flat ❌ | underperform(0.55)→underperform ✅ | 5.83 | -37.25 | -54.23 |
| NOW | NO_TRADE | -47.09 | decelerate(0.6)→decelerate ✅ | expand(0.6)→expand ✅ | outperform(0.52)→underperform ❌ | -10.31 | -13.84 | -38.34 |
| PYPL | NO_TRADE | 4.597525 | decelerate(0.6)→decelerate ✅ | expand(0.6)→expand ✅ | outperform(0.55)→underperform ❌ | -24.28 | -22.0 | -37.47 |
| AMD | BUY | 11.64124 | accelerate(0.65)→accelerate ✅ | expand(0.58)→expand ✅ | outperform(0.52)→outperform ✅ | -7.86 | 3.19 | -39.63 |
| TGT | NO_TRADE | -9.527102 | decelerate(0.6)→decelerate ✅ | contract(0.6)→expand ❌ | underperform(0.55)→underperform ✅ | -30.28 | -29.22 | -37.18 |
| BLK | NO_TRADE | -0.598812 | decelerate(0.58)→decelerate ✅ | flat(0.52)→contract ❌ | underperform(0.55)→underperform ✅ | -10.72 | -2.26 | -23.74 |

- revenue_growth：命中 6/9，平均 Brier 0.215
- operating_margin：命中 4/8，平均 Brier 0.246
- relative_return_126d：命中 6/9，平均 Brier 0.245
- BUY 组 126 日净超额：n=3，均值 25.25%，中位 31.73%
- NO_TRADE 组 126 日净超额：n=6，均值 -16.46%，中位 -17.92%

## 2025-04-01-codex-c

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| MU | NO_TRADE | -3.511653 | decelerate(0.65)→accelerate ❌ | expand(0.60)→expand ✅ | underperform(0.55)→outperform ❌ | 15.09 | 68.28 | -27.04 |
| ALB | NO_TRADE | -54.686156 | accelerate(0.60)→accelerate ✅ | expand(0.65)→expand ✅ | underperform(0.60)→outperform ❌ | -11.2 | 15.25 | -29.74 |
| AMAT | BUY | 23.53 | decelerate(0.58)→flat ❌ | expand(0.60)→expand ✅ | outperform(0.58)→outperform ✅ | 8.48 | 12.89 | -21.37 |
| ADBE | BUY | 29.836765 | decelerate(0.58)→flat ❌ | flat(0.53)→contract ❌ | underperform(0.57)→underperform ✅ | -23.57 | -47.75 | -20.69 |
| NOW | NO_TRADE | -3.275123 | decelerate(0.70)→accelerate ❌ | expand(0.60)→expand ✅ | underperform(0.58)→underperform ✅ | 2.28 | -24.82 | -18.55 |
| ABBV | NO_TRADE | -12.896515 | accelerate(0.55)→accelerate ✅ | expand(0.55)→expand ✅ | outperform(0.5)→outperform ✅ | -1.55 | 19.57 | -16.74 |
| UNH | NO_TRADE | -0.48 | accelerate(0.60)→accelerate ✅ | contract(0.55)→contract ✅ | underperform(0.55)→underperform ✅ | -35.67 | -33.55 | -60.06 |
| AMGN | NO_TRADE | -6.457765 | decelerate(0.60)→decelerate ✅ | expand(0.55)→expand ✅ | underperform(0.55)→underperform ✅ | 2.69 | -2.12 | -15.35 |
| INTU | BUY | 14.156763 | decelerate(0.62)→accelerate ❌ | expand(0.68)→expand ✅ | outperform(0.54)→underperform ❌ | 3.93 | -26.4 | -19.99 |

- revenue_growth：命中 4/9，平均 Brier 0.295
- operating_margin：命中 8/9，平均 Brier 0.177
- relative_return_126d：命中 6/9，平均 Brier 0.239
- BUY 组 126 日净超额：n=3，均值 -20.42%，中位 -26.4%
- NO_TRADE 组 126 日净超额：n=6，均值 7.1%，中位 6.56%

## 2025-07-01-codex-c

| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |
|---|---|---|---|---|---|---|---|---|
| INTC | NO_TRADE | -32.70 | accelerate(0.52)→accelerate ✅ | expand(0.60)→expand ✅ | underperform(0.62)→outperform ❌ | 34.37 | 47.04 | -19.05 |
| MU | BUY | 52.398901 | accelerate(0.6)→accelerate ✅ | expand(0.65)→expand ✅ | outperform(0.55)→outperform ✅ | 25.88 | 126.14 | -20.5 |
| ADBE | BUY | 11.854919 | decelerate(0.55)→flat ❌ | expand(0.55)→expand ✅ | outperform(0.52)→underperform ❌ | -22.69 | -26.5 | -20.33 |
| AMD | NO_TRADE | -2.687887 | decelerate(0.60)→flat ❌ | expand(0.58)→expand ✅ | underperform(0.55)→outperform ❌ | 6.41 | 42.01 | -25.05 |
| NOW | NO_TRADE | 3.415729 | decelerate(0.65)→accelerate ❌ | expand(0.60)→expand ✅ | outperform(0.52)→underperform ❌ | -21.51 | -39.99 | -26.97 |
| INTU | BUY | 22.815727 | decelerate(0.65)→accelerate ❌ | expand(0.60)→expand ✅ | outperform(0.55)→underperform ❌ | -24.94 | -30.2 | -21.94 |
| HD | NO_TRADE | -0.51 | decelerate(0.65)→decelerate ✅ | contract(0.60)→contract ✅ | underperform(0.55)→underperform ✅ | -0.79 | -16.76 | -21.5 |
| BLK | NO_TRADE | 1.38655 | decelerate(0.55)→accelerate ❌ | contract(0.60)→contract ✅ | outperform(0.52)→underperform ❌ | 8.47 | -1.76 | -17.47 |
| AVGO | NO_TRADE | -4.744642 | accelerate(0.55)→accelerate ✅ | expand(0.60)→expand ✅ | underperform(0.55)→outperform ❌ | 12.38 | 16.42 | -21.05 |

- revenue_growth：命中 4/9，平均 Brier 0.281
- operating_margin：命中 9/9，平均 Brier 0.162
- relative_return_126d：命中 2/9，平均 Brier 0.279
- BUY 组 126 日净超额：n=3，均值 23.15%，中位 -26.5%
- NO_TRADE 组 126 日净超额：n=6，均值 7.83%，中位 7.33%

