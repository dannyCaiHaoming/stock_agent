# Claude Code 开发入口

@AGENTS.md

<!-- handoff:learnings:begin -->
## Session Learnings (auto-updated by handoff)

### Key Decisions
- Decision: expected return from scenario table no longer gates BUY/NO_TRADE; valuation only sizes position — Reason: base scenario negative in 65/84 replay reports regardless of regime, 1-year value gap vs 60-day window mismatch
- Decision: evaluate ranking within peer group vs group median, always alongside prior-60d/126d momentum controls — Reason: plan C 0.47 rank corr fell to 0.23 within sector; single date = one observation
- Decision: stop adding replay dates / tuning rules for 60-day direction — Reason: ablation, A/A'/C, plan D all at coin-flip; pre-registered rule in plan D said stop
- Decision: target is advisor at key chart moments with base-rate distributions (p_up, avg gain/loss, expectancy, drawdown) vs any-day baseline — Reason: user confirmed; wants unemotional probability x payoff advice, not a backtested formula
- Decision: moment definitions normalised by each stock's daily volatility, thresholds not tuned to results — Reason: same rule must fit KO and RKLB; avoid data dredging
- Decision: keep scripts/build-pead-events.py — Reason: insider/congress stats still use its daily control rows
- Decision: sub-session work shares main checkout, no branches — Reason: user preference to work on main

<!-- handoff:learnings:end -->
