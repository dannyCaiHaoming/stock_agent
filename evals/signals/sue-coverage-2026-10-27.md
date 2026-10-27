# SUE 证据链覆盖率

生成：2026-10-28 01:32。口径：每个财季一行（第一份完整业绩公告）；`verified` = 当季与去年同季 GAAP EPS 均通过程序核对。

- 去重后业绩事件：3796；被排除（非业绩公告/重复）：275

## 状态

| 状态 | 数 | 占比 |
|---|---|---|
| verified | 3403 | 89.6% |
| unverified | 344 | 9.1% |
| missing:no_gaap_eps_in_text | 28 | 0.7% |
| missing:no_eps_table | 21 | 0.6% |

## 排除原因

| 原因 | 数 |
|---|---|
| non_earnings_release:other | 94 |
| non_earnings_release:operating_update | 53 |
| non_earnings_release:guidance_only | 44 |
| non_earnings_release:preannouncement | 31 |
| non_earnings_release:no_exhibit | 26 |
| duplicate_of | 21 |
| non_earnings_release:annual_only | 6 |

检验窗口内事件（来自 events-8k，2019 起）：3078；其中 verified 2743，其前 8 个季度也全部 verified（连续 9 季）2291

## unverified 备注（一事件可有多个）

| 备注 | 数 |
|---|---|
| current_verified_year_ago_not | 308 |
| no_year_ago_column_in_table | 166 |
| yago_unverified:quote_year_or_date_check_failed | 38 |
| program_hint_nongaap_table_or_label | 11 |
| cur_quote_mentions_adjusted | 7 |
| cur_header_quote_not_in_header | 6 |
| llm_row_not_a_candidate | 5 |
| yago_unverified:year_mismatch_or_not_quarterly | 3 |
| cur_col_not_quarterly | 2 |
| period_not_verified | 2 |
| yago_value_mismatch_cell | 1 |
| cur_sign_inconsistent_with_quote | 1 |
| period_end_inferred_from_quarter_label_and_filing_date | 1 |
| cur_col_year_differs_from_period | 1 |
| period_end_not_in_text | 1 |

## 按年份（检验窗口，signal_date 年）

| 键 | 事件 | verified | 连续9季 |
|---|---|---|---|
| 2019 | 369 | 335 | 280 |
| 2020 | 369 | 329 | 271 |
| 2021 | 378 | 335 | 279 |
| 2022 | 396 | 346 | 287 |
| 2023 | 396 | 353 | 292 |
| 2024 | 405 | 363 | 309 |
| 2025 | 414 | 373 | 313 |
| 2026 | 351 | 309 | 260 |

## 按年份（含 2017-18 历史事件）

| 键 | 事件 | verified | 连续9季 |
|---|---|---|---|
| 2017 | 358 | 328 | 0 |
| 2018 | 360 | 332 | 0 |
| 2019 | 369 | 335 | 280 |
| 2020 | 369 | 329 | 271 |
| 2021 | 378 | 335 | 279 |
| 2022 | 396 | 346 | 287 |
| 2023 | 396 | 353 | 292 |
| 2024 | 405 | 363 | 309 |
| 2025 | 414 | 373 | 313 |
| 2026 | 351 | 309 | 260 |

## 按板块 ETF（benchmark）

| 键 | 事件 | verified | 连续9季 |
|---|---|---|---|
| XLB | 121 | 84 | 41 |
| XLC | 244 | 240 | 205 |
| XLE | 95 | 74 | 63 |
| XLF | 356 | 312 | 258 |
| XLI | 372 | 331 | 250 |
| XLK | 956 | 908 | 818 |
| XLP | 189 | 189 | 126 |
| XLRE | 52 | 32 | 32 |
| XLU | 101 | 36 | 3 |
| XLV | 375 | 349 | 312 |
| XLY | 217 | 188 | 183 |

## 按 ticker（检验窗口）

| 键 | 事件 | verified | 连续9季 |
|---|---|---|---|
| AAOI | 31 | 31 | 31 |
| AAPL | 31 | 31 | 31 |
| ABBV | 31 | 31 | 31 |
| ABT | 32 | 19 | 11 |
| ADBE | 31 | 31 | 31 |
| ALAB | 10 | 9 | 1 |
| ALB | 31 | 31 | 24 |
| AMAT | 30 | 30 | 22 |
| AMD | 31 | 31 | 31 |
| AMGN | 31 | 31 | 31 |
| AMT | 32 | 32 | 32 |
| AMZN | 31 | 31 | 31 |
| AVGO | 31 | 26 | 13 |
| AXP | 32 | 32 | 32 |
| BA | 32 | 31 | 23 |
| BAC | 32 | 32 | 32 |
| BKSY | 20 | 19 | 10 |
| BLK | 9 | 9 | 1 |
| BMY | 31 | 30 | 22 |
| C | 30 | 25 | 9 |
| CAT | 31 | 30 | 22 |
| CIEN | 31 | 30 | 22 |
| CMCSA | 32 | 32 | 25 |
| COHR | 31 | 31 | 31 |
| COP | 31 | 10 | 0 |
| COST | 31 | 31 | 0 |
| CRDO | 17 | 11 | 0 |
| CRM | 31 | 31 | 31 |
| CSCO | 31 | 31 | 31 |
| CVS | 31 | 31 | 31 |
| CVX | 31 | 31 | 31 |
| DE | 31 | 31 | 30 |
| DIS | 30 | 30 | 22 |
| DUK | 31 | 26 | 3 |
| FCX | 32 | 26 | 15 |
| GE | 31 | 15 | 3 |
| GEV | 9 | 6 | 0 |
| GILD | 31 | 31 | 31 |
| GOOGL | 31 | 31 | 31 |
| GS | 32 | 32 | 32 |
| HD | 31 | 31 | 31 |
| HON | 32 | 32 | 32 |
| IBM | 32 | 0 | 0 |
| INTC | 31 | 31 | 31 |
| INTU | 31 | 31 | 31 |
| IRDM | 32 | 32 | 32 |
| JNJ | 32 | 30 | 24 |
| JPM | 32 | 32 | 32 |
| KLAC | 31 | 31 | 31 |
| KO | 32 | 32 | 32 |
| LIN | 26 | 21 | 2 |
| LITE | 31 | 31 | 31 |
| LLY | 31 | 31 | 25 |
| LMT | 32 | 32 | 32 |
| LOW | 31 | 31 | 31 |
| LRCX | 32 | 32 | 32 |
| MA | 31 | 31 | 31 |
| MCD | 31 | 30 | 25 |
| META | 32 | 31 | 23 |
| MKSI | 31 | 31 | 31 |
| MRK | 31 | 24 | 16 |
| MRVL | 22 | 22 | 14 |
| MS | 31 | 31 | 23 |
| MSFT | 31 | 31 | 31 |
| MU | 31 | 31 | 31 |
| NEE | 32 | 1 | 0 |
| NEM | 32 | 6 | 0 |
| NFLX | 32 | 32 | 32 |
| NKE | 31 | 31 | 31 |
| NOW | 31 | 31 | 31 |
| NTAP | 31 | 31 | 31 |
| NVDA | 31 | 30 | 22 |
| ORCL | 31 | 29 | 17 |
| PEP | 32 | 32 | 0 |
| PFE | 31 | 31 | 30 |
| PG | 32 | 32 | 32 |
| PL | 20 | 20 | 12 |
| PLD | 20 | 0 | 0 |
| PYPL | 32 | 27 | 11 |
| QCOM | 31 | 31 | 31 |
| RDW | 19 | 18 | 10 |
| RKLB | 19 | 18 | 10 |
| RTX | 32 | 32 | 28 |
| SBUX | 31 | 31 | 31 |
| SCHW | 32 | 29 | 29 |
| SLB | 32 | 32 | 32 |
| SNDK | 6 | 6 | 0 |
| SO | 31 | 3 | 0 |
| STX | 31 | 31 | 31 |
| T | 23 | 22 | 14 |
| TER | 31 | 31 | 31 |
| TGT | 31 | 31 | 31 |
| TLN | 7 | 6 | 0 |
| TMO | 32 | 32 | 32 |
| TSLA | 31 | 3 | 3 |
| TXN | 32 | 32 | 32 |
| UNH | 31 | 28 | 28 |
| UNP | 32 | 32 | 32 |
| UPS | 32 | 15 | 6 |
| V | 31 | 0 | 0 |
| VSAT | 31 | 31 | 31 |
| VZ | 32 | 30 | 26 |
| WDC | 31 | 31 | 23 |
| WFC | 32 | 32 | 26 |
| WMT | 31 | 31 | 31 |
| XOM | 1 | 1 | 0 |

## XBRL 核对（仅核对，不是来源）

| 项 | match | mismatch | uncheckable |
|---|---|---|---|
| 当季 EPS | 2945 | 77 | 110 |
| 当季 EPS，财年 Q4 用 FY−9M 近似（容差 0.06，EPS 不可加，仅参考） | 566 | 34 | |
| 去年同季 EPS（XBRL 为首次披露值；8-K 同列可能是重述/拆股调整值） | 2709 | 168 | 526 |

当季可核对准确率：97.5%（n=3022）；去年同季：94.2%（n=2877）

| 年份 | match | mismatch | approx_match(Q4) | approx_far(Q4) | uncheckable |
|---|---|---|---|---|---|
| 2017 | 315 | 6 | 21 | 4 | 7 |
| 2018 | 318 | 5 | 24 | 2 | 7 |
| 2019 | 323 | 5 | 26 | 0 | 10 |
| 2020 | 322 | 11 | 26 | 1 | 6 |
| 2021 | 293 | 12 | 56 | 2 | 6 |
| 2022 | 278 | 12 | 83 | 2 | 6 |
| 2023 | 283 | 8 | 83 | 4 | 7 |
| 2024 | 296 | 11 | 82 | 4 | 7 |
| 2025 | 309 | 3 | 88 | 6 | 7 |
| 2026 | 208 | 4 | 77 | 9 | 47 |
