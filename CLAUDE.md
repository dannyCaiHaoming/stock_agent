# Claude Code 开发入口

@AGENTS.md

<!-- handoff:learnings:begin -->
## Session Learnings (auto-updated by handoff)

### Implicit Rules
- Docs in Chinese; identifiers English
- Codex CLI: codex exec -m gpt-6.2-astra -s read-only, artifacts only under .local/runs/<id>/
- Work on main, commit only on user approval
- Old ledgers append-only; new mode uses separate evals/forward/decision-ledger.jsonl

### Key Decisions
- Decision: split promise — decision tool usable after P1, investment edge claimed only after P2 forward results — Reason: no buy-side signal passed registered tests
- Decision: first tested hypothesis = holder protection (halve on E1/E2 events vs hold B0, mechanical rule B1, guidance-cut rule B2) — Reason: only passing signal (terra news-review Q1 +0.28, Q3 −11.4pp) is company-bad-news continuation
- Decision: horizons frozen by event group (E1 earnings big drop 20d, E2 deviation |z|>=2 60d, E0 routine 60d), not LLM-chosen — Reason: PEAD big-drop vs sector ETF −0.24pp at 20d but +3.08pp at 60d; horizon choice flips conclusion
- Decision: never multiply LLM p by historical avg gain/loss from different conditions; card shows relative / absolute / cash-destination columns separately — Reason: different populations and variables
- Decision: unified fill = next regular session open after decided_at; Δ=(w1−w0)(R_stock−R_alt)−cost diff, HOLD/WAIT=0 — Reason: always-hold scores exactly zero, no gaming
- Decision: lightweight chain default, full advocate/skeptic/CIO on request only — Reason: ablation shows no gain, 5-6 min per run exhausts Codex quota
- Decision (confirmed 2026-11-22, protocol v1): expand scan to S&P 500 stratified, pause forward-run.sh and forward-groups.sh, primary scoring swaps into sector ETF, E2 wins overlap with E1 — Reason: 100 events with ~11 reduces gives only 39-55% power; 165-255 events needed
- Decision: expected return from scenario table no longer gates BUY/NO_TRADE; valuation only sizes position — Reason: base scenario negative in 65/84 replay reports regardless of regime, 1-year value gap vs 60-day window mismatch
- Decision: stop adding replay dates / tuning rules for 60-day direction — Reason: ablation, A/A'/C, plan D all at coin-flip; pre-registered rule in plan D said stop
- Decision: moment definitions normalised by each stock's daily volatility, thresholds not tuned to results — Reason: same rule must fit KO and RKLB; avoid data dredging
- Decision: keep scripts/build-pead-events.py — Reason: insider/congress stats still use its daily control rows
- Decision: sub-session work shares main checkout, no branches — Reason: user preference to work on main

<!-- handoff:learnings:end -->
