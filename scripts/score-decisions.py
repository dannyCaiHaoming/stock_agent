"""按决策账本协议 v1 给 decision/v2 记录成交并评分（确定性计算，不做判断）。

用法：.venv/bin/python -I scripts/score-decisions.py [--ledger FILE] [--as-of YYYY-MM-DD] [--out FILE.md]
  --ledger  默认 evals/forward/decision-ledger.jsonl（只读）
  --as-of   评分日（含）；默认美东当日（16:00 前取前一日）。价格只取到该日
  --out     写 Markdown 到文件；默认打印到 stdout
成交 = decided_at 之后第一个常规交易日复权开盘（回放记录用 decided_at_effective）；Δ 与区间见协议 §4–§6。
只对 source=scan 的 E2 主样本做判定；按需记录与回放记录逐条列出，永不进主样本。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

import numpy as np  # noqa: E402

from product.deterministic import decision_scoring as ds  # noqa: E402
from product.mcp import data_tools  # noqa: E402

LEDGER = REPO / "evals" / "forward" / "decision-ledger.jsonl"
REFERENCE_CALENDAR = "SPY"


def default_as_of() -> str:
    now = datetime.now(ds.NY)
    return (now.date() if now.time() >= time(16, 0) else now.date() - timedelta(days=1)).isoformat()


def read_ledger(path: Path) -> list[dict]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{n}: invalid JSON ({exc})") from exc
    return rows


class PriceBook:
    def __init__(self, start: str, end: str):
        self.start, self.end, self.rows, self.errors = start, end, {}, {}

    def get(self, ticker: str):
        if ticker not in self.rows:
            try:
                got = data_tools.get_price_history(ticker, start=self.start, end=self.end, max_rows=6000)["rows"]
                self.rows[ticker] = [r for r in got if r[0] <= self.end]
            except Exception as exc:  # noqa: BLE001 - reported, never silently treated as "no data"
                self.rows[ticker], self.errors[ticker] = None, f"{type(exc).__name__}: {exc}"
        return self.rows[ticker]


def f(x, nd=2, plus=True):
    if x is None:
        return "—"
    x = 0.0 if abs(x) < 0.5 * 10 ** -nd else x      # no "-0.00"
    return f"{x:+.{nd}f}" if plus else f"{x:.{nd}f}"


def ci_text(ci):
    return "不可用（W<3L）" if ci is None else f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return lines


def record_rows(scored):
    rows = []
    for s in sorted(scored, key=lambda r: (r.get("fill_date") or "9999", r["ticker"])):
        rows.append([s["decision_id"], s["ticker"], s["group"], s["source"], s["action"],
                     f"{s['w0']:g}→{s['w1']:g}", s["horizon_days"], s.get("fill_date", "—"), s.get("exit_date", "—"),
                     s["status"] + (f"（迟到 {s['late_sessions']} 日）" if s.get("late") else ""),
                     f(s.get("r_stock")), f(s.get("r_etf")),
                     f(s.get("delta_etf")), f(s.get("delta_b1_etf")), f(s.get("delta_b2_etf")),
                     f(s.get("delta_cash")), f(s.get("delta_b1_cash")), f(s.get("delta_b2_cash"))])
    return table(["id", "ticker", "组", "来源", "动作", "w0→w1", "h", "成交日", "结算日", "状态", "R_stock", "R_ETF",
                  "Δ(ETF)", "Δ_B1(ETF)", "Δ_B2(ETF)", "Δ(现金)", "Δ_B1(现金)", "Δ_B2(现金)"], rows)


def group_means(rows, keyfn, key="delta_etf"):
    buckets = defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            buckets[keyfn(r)].append(r[key])
    return [[k, len(v), f(ds.mean(v))] for k, v in sorted(buckets.items(), key=lambda kv: str(kv[0]))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    as_of = args.as_of or default_as_of()
    date.fromisoformat(as_of)
    rows = read_ledger(args.ledger) if args.ledger.exists() else []
    events = ds.build_events(rows)

    dated = [e for e in events if e["event_date"]]
    stamps = [ds.parse_utc(ds.fill_time(e["decision"])).astimezone(ds.NY).date() for e in events if e["decision"]]
    firsts = stamps + [date.fromisoformat(e["event_date"]) for e in dated]
    start = (min(firsts) - timedelta(days=15)).isoformat() if firsts else (date.fromisoformat(as_of) - timedelta(days=60)).isoformat()
    book = PriceBook(start, as_of)

    # Independent trading calendar: SPY sessions (also for no_sector stocks). A day a stock or ETF has no row for
    # stays in the calendar with missing prices; it never shifts a fill or an exit.
    calendar_rows = book.get(REFERENCE_CALENDAR) if events else []
    if calendar_rows is None:
        raise SystemExit(f"REFUSED: cannot fetch the {REFERENCE_CALENDAR} trading calendar ({book.errors[REFERENCE_CALENDAR]})")
    calendar = sorted({r[0] for r in calendar_rows})

    warnings = []
    scored_all = []
    for e in events:
        if e["decision"] is None:
            # the window a missing decision would have had, on the same calendar
            horizon = 20 if e["group"] == "E1" else 60
            stamp = (e["stamp"] or f"{e['event_date']}T16:00:01-05:00") if e["event_date"] else None
            e["no_decision_matured"] = bool(stamp) and ds.matured(stamp, calendar, horizon)
            continue
        rec = e["decision"]
        stock_rows = book.get(rec["ticker"])
        bench = rec.get("benchmark")
        bench_rows = book.get(bench) if bench and bench != "no_sector" else None
        if stock_rows is None:
            warnings.append(f"{rec['ticker']}（{rec.get('decision_id')}）：取价失败（{book.errors[rec['ticker']]}），到期后记 price_error 并计入缺失率")
        if bench and bench != "no_sector" and bench_rows is None:
            warnings.append(f"{rec['ticker']}（{rec.get('decision_id')}）：基准 {bench} 取价失败（{book.errors.get(bench)}），ETF 口径记 etf_unscorable")
        e["scored"] = ds.score_record(rec, calendar, ds.align_prices(calendar, stock_rows), ds.align_prices(calendar, bench_rows))
        scored_all.append(e["scored"])
    events_ok = events

    out = [f"# 决策账本评分（协议 v1）", "",
           f"- 账本：`{args.ledger}`（{len(rows)} 行，{len(events)} 个事件）；评分日 as_of = {as_of}",
           f"- 成交：decided_at 之后第一个常规交易日复权开盘；h 日收盘结算；Δ 单位为百分点/标准仓位（=100）",
           f"- 数据：`data_tools.get_price_history`（Yahoo，复权开盘 = open×adj_close/close）；交易日历 = {REFERENCE_CALENDAR} 的交易日，个股或 ETF 缺行的日子仍在日历内、记为缺价", ""]

    # ---------------- funnel (E2 scan, replays excluded)
    fn = ds.funnel(events_ok, "E2")
    ex = fn["excluded"]
    out += ["## 漏斗（source=scan 的 E2，不含回放）", ""]
    out += table(["层", "数量", "本层被排除"], [
        ["候选", fn["candidates"], f"未抽中 {ex['not_selected']}；无 selection 记录 {ex['no_selection']}"],
        ["抽中", fn["selected"], f"决策失败 {ex['failure']}；无记录 {ex['awaiting_decision']}"],
        ["决策成功", fn["decided"], f"未到期 {ex['pending']}"],
        ["已到期", fn["matured"], f"取价异常 price_error {ex['price_error']}"],
        ["取到行情", fn["priced"], f"not_fillable {ex['not_fillable']}"],
        ["可成交", fn["fillable"], f"unscorable（个股结算缺价或 ETF 缺价）{ex['unscorable']}"],
        ["可评分", fn["scorable"], f"迟到 {ex['late']}"],
        ["不迟到（主样本）", len(fn["main"]), ""]])
    rate = fn["missing_rate"]
    out += ["", f"- 缺失率 = （无决策已到期 + price_error + not_fillable + ETF 口径 unscorable）÷ 抽中且已到期 = "
            f"{fn['missing']} / {fn['matured_selected']} = " + ("—" if rate is None else f"{rate:.1%}")
            + ("　**样本缺失偏高（>10%）**" if fn["missing_high"] else ""),
            f"- 未到期不计入分子分母：无决策事件窗口未到期 {ex['no_decision_unmatured']}，决策成功但未到期 {ex['pending']}（到期只看日历，与能否成交无关）"]
    if fn["no_selection"]:
        out += [f"- **警告**：{len(fn['no_selection'])} 个扫描事件没有 `selection` 行（决策或失败记录单独存在），不视为抽中、不进主样本："
                + "；".join(f"{e['ticker']} {e['event_date']} " + (e["decision"]["decision_id"] if e["decision"] else "failure") for e in fn["no_selection"])]
        warnings.append(f"{len(fn['no_selection'])} 个扫描事件缺 selection 行（见漏斗）")
    out += [""]

    # ---------------- primary test
    main_rows = fn["main"]
    if as_of >= ds.FINAL_DATE:  # calendar cap: only events that matured before the cap day
        main_rows = [r for r in main_rows if r["exit_date"] < ds.FINAL_DATE]
    interim = ds.interim_snapshot(main_rows, ds.BLOCK_WEEKS["E2"], fn["pending"])   # whole fill weeks, one look
    final = ds.is_final(len(main_rows), as_of)
    main_rows = ds.cap_sample(main_rows)
    L = ds.BLOCK_WEEKS["E2"]
    wk = [ds.week_index(r["fill_date"]) for r in main_rows]
    W = (max(wk) - min(wk) + 1) if wk else None
    st = ds.summarize(main_rows, "delta_etf", L, "delta_b1_etf")
    ci_d, ci_p = st["ci"], st["diff"]["ci"]
    verdict = ds.verdict(ci_d, ci_p) if final else "—（未到最终分析，不判定）"
    out += ["## 主检验：E2 · ETF 口径 · terra 决策 vs B0 / B1", "",
            f"- 阶段：**{'最终分析' if final else '收集中（区间仅作描述，不据此判定）'}**；主样本已到期 {len(main_rows)} 个"
            f"（最终 {ds.FINAL_N}，或日历到 {ds.FINAL_DATE}）；成交周数 W = {W if W else '—'}，块长 L = {L} 周"
            f"（W≥3L = {W is not None and W >= 3 * L}）", ""]
    out += table(["统计量", "n", "均值（pp）", "90% 区间"], [
        ["Δ（ETF 口径，相对 B0=0）", st["n"], f(st["mean"]), ci_text(ci_d)],
        ["Δ − Δ_B1", st["diff"]["n"], f(st["diff"]["mean"]), ci_text(ci_p)]])
    out += ["", f"- MUE = +{ds.MUE_PP:.2f} pp；最终判定：**{verdict}**（顺序：不值得 → 支持 → 证据不足；只在最终分析时作数）"]
    if interim is None:
        out += [f"- 中期查看（只有一次，只允许判定 1 提前停止）：尚未触发（需主样本已到期 ≥ {ds.INTERIM_N} 且 W ≥ 3L）", ""]
    elif interim["state"] == "pending":
        out += [f"- 中期查看待定（触发周事件未全部到期）：触发周 {interim['trigger_week_start']}（周一），快照含成交周 ≤ 该周的 "
                f"{interim['n']} 个已到期事件，另有 {interim['n_pending']} 个同周或更早的事件尚未到期；到期后才第一次输出判定", ""]
    else:
        out += [f"- 中期查看（已输出，只有这一次；之后每次运行都用同一个快照）：触发周 {interim['trigger_week_start']}（周一），"
                f"成交周 ≤ 该周的 n = {interim['n']}（截至成交日 {interim['cutoff_fill_date']}），W = {interim['W']}，"
                f"Δ 均值 {f(interim['mean'])}，区间 {ci_text(interim['ci_delta'])}，"
                f"Δ − Δ_B1 区间 {ci_text(interim['ci_diff'])} → **{interim['verdict']}**", ""]

    # ---------------- secondary
    out += ["## 次要报告（不做判定）", ""]
    cash = ds.summarize(main_rows, "delta_cash", L, "delta_b1_cash")
    b2 = ds.summarize(main_rows, "delta_b2_etf", L)
    d2 = [r["delta_etf"] - r["delta_b2_etf"] for r in main_rows if r.get("delta_etf") is not None and r.get("delta_b2_etf") is not None]
    b1 = ds.summarize(main_rows, "delta_b1_etf", L)
    out += table(["口径", "n", "均值（pp）", "90% 区间"], [
        ["现金口径 Δ", cash["n"], f(cash["mean"]), ci_text(cash["ci"])],
        ["现金口径 Δ − Δ_B1", cash["diff"]["n"], f(cash["diff"]["mean"]), ci_text(cash["diff"]["ci"])],
        ["B1（ETF）Δ_B1", b1["n"], f(b1["mean"]), ci_text(b1["ci"])],
        ["B2（ETF）Δ_B2", b2["n"], f(b2["mean"]), ci_text(b2["ci"])],
        ["Δ − Δ_B2（ETF）", len(d2), f(ds.mean(d2)), "—"]])
    out += ["", "**按动作**", ""] + table(["动作", "n", "均值 Δ(ETF)"], group_means(main_rows, lambda r: r["action"]))
    dirs = {}
    for e in events_ok:
        if e["decision"]:
            z = (e["decision"].get("event") or {}).get("deviation_z")
            dirs[e["decision"].get("decision_id")] = "下偏" if z is not None and z <= -2 else "上偏" if z is not None else "未知"
    out += ["", "**按偏离方向**", ""] + table(["方向", "n", "均值 Δ(ETF)"],
                                           group_means(main_rows, lambda r: dirs.get(r["decision_id"], "未知")))
    tiers = {e["decision"].get("decision_id"): e["decision"].get("tier") or "未记录"
             for e in events_ok if e["decision"]}
    out += ["", "**按层（原池/新增，取记录的 `tier` 字段）**", ""] + table(
        ["层", "n", "均值 Δ(ETF)"], group_means(main_rows, lambda r: tiers.get(r["decision_id"], "未记录")))

    ps = {e["decision"].get("decision_id"): (e["decision"].get("p_outperform") or {}).get("case")
          for e in events_ok if e["decision"]}
    cal_rows = []
    for name, lo, hi in (("< 0.45", -1, 0.45), ("0.45–0.55", 0.45, 0.5500001), ("> 0.55", 0.5500001, 2)):
        sel = [r for r in main_rows if ps.get(r["decision_id"]) is not None and lo <= ps[r["decision_id"]] < hi
               and "outperformed" in r]
        cal_rows.append([name, len(sel), "—" if not sel else f"{np.mean([ps[r['decision_id']] for r in sel]):.2f}",
                         "—" if not sel else f"{np.mean([r['outperformed'] for r in sel]):.0%}"])
    out += ["", "**分档校准（p_outperform.case → 实际跑赢板块频率）**", ""] + table(["档", "n", "平均 p", "实际跑赢"], cal_rows)
    pm_rec = [r["w1"] * r["path_min"] for r in main_rows if r.get("path_min") is not None]
    pm_b0 = [r["w0"] * r["path_min"] for r in main_rows if r.get("path_min") is not None]
    out += ["", "**途中最低收盘（相对入场，股票腿，不含资金去向腿）的 10% 分位（pp）**", ""] + table(
        ["仓位", "n", "10% 分位"],
        [["建议仓位 (w1×最低)", len(pm_rec), f(float(np.percentile(pm_rec, 10))) if pm_rec else "—"],
         ["B0 (w0×最低)", len(pm_b0), f(float(np.percentile(pm_b0, 10))) if pm_b0 else "—"]])

    e1 = [e["scored"] for e in events_ok if e["decision"] and e["group"] == "E1" and e["source"] == "scan"
          and not e["replay"] and e["scored"]["status"] == "scored"]
    s1 = ds.summarize(e1, "delta_etf", ds.BLOCK_WEEKS["E1"], "delta_b1_etf")
    out += ["", "**E1（非重叠，扫描，20 日）**", ""] + table(["统计量", "n", "均值（pp）", "90% 区间（L=4 周）"], [
        ["Δ（ETF）", s1["n"], f(s1["mean"]), ci_text(s1["ci"])],
        ["Δ − Δ_B1", s1["diff"]["n"], f(s1["diff"]["mean"]), ci_text(s1["diff"]["ci"])]])
    aux = [r for r in scored_all if r.get("aux20_etf") is not None and not r["replay"]]
    if aux:
        out += ["", f"E2 与 E1 重叠的辅助 20 日 Δ(ETF)：n={len(aux)}，均值 {f(ds.mean([r['aux20_etf'] for r in aux]))} pp", ""]

    # ---------------- per record
    live = [s for s in scored_all if not s["replay"]]
    replay = [s for s in scored_all if s["replay"]]
    out += ["", "## 逐条（非回放）", ""] + (record_rows(live) if live else ["（无）"])
    out += ["", "## 回放记录（`replay=true`，用 decided_at_effective 成交，永不进主样本）", ""] + \
           (record_rows(replay) if replay else ["（无）"])
    if warnings:
        out += ["", "## 警告", ""] + [f"- {w}" for w in warnings]
    text = "\n".join(out) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
