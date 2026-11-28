"""按子设计“三线结算”给 plan/v1 交易计划结算（确定性计算，只读，不调用模型）。

用法：.venv/bin/python -I scripts/score-plans.py [--plans FILE] [--as-of YYYY-MM-DD] [--out FILE.md]
  --plans   默认 .local/data/trade_plans.jsonl（只读）
  --as-of   评分日（含）；默认美东当日（16:00 前取前一日）。价格只取到该日
  --out     写 Markdown 到文件；默认打印到 stdout
成交 = 冻结时间（frozen_at，回放计划为当日美东 23:59:59）之后的限价挂单：从第一个常规交易日起最多 entry_valid_sessions
个交易日（缺字段的旧记录按 1 个交易日、只看开盘），逐日看未复权开盘与最低价，开盘在区间内按开盘价成交、
开盘高于上限而最低价触及上限按上限成交；逐日规则见 product/deterministic/plan_math.py。行情取自 data_tools.get_price_history（Yahoo），交易日历 = SPY 的交易日；
个股缺行的日子留在日历内、记为缺价。取价失败会写进“警告”并让该计划记为 price_error，不会当作“无数据”。
cap 到期（as_of >= cap_date）才按 cap 收盘离场；未到期的计划按 as_of 前最后一个收盘估值（未实现）。
只用已完成的交易日：as_of 是今天且美东未到 16:00（或取价返回 last_row_incomplete_session）时丢弃当天行，
实际截止日写在报告里。记录按评分日（实际截止日）美东 23:59:59 截断：之后生效的计划、修订、复核、选择、机会
都不进报告与漏斗。取价带 as_of（还原评分日之后的拆股），评分日及之前的拆股由脚本还原为当时每股口径，
窗口内的拆股由 plan_math 判为不可结算。
退出码：0 正常；1 有取价失败或结算失败；2 无法取得 SPY 日历（拒绝评分）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    try:
        os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]
    except (OSError, KeyError, ValueError):
        pass

from product.deterministic import decision_scoring as ds  # noqa: E402
from product.deterministic import plan_math  # noqa: E402
from product.mcp import data_tools  # noqa: E402

PLANS = REPO / ".local" / "data" / "trade_plans.jsonl"
REFERENCE_CALENDAR = "SPY"
LINE_LABELS = {"plan": "照计划", "hold": "持有对照", "simple_exit": "简单退出对照"}
REASON_LABELS = {"fill": "成交", "stop": "止损", "review": "复核", "cap": "cap", "value": "估值（未实现）"}


def last_complete_day(now: datetime | None = None) -> str:
    """Latest New York date whose regular session has finished (today from 16:00, else yesterday)."""
    now = (now or datetime.now(ds.NY)).astimezone(ds.NY)
    return (now.date() if now.time() >= time(16, 0) else now.date() - timedelta(days=1)).isoformat()


def default_as_of() -> str:
    return last_complete_day()


# ledger field that says when a record became effective, per kind (first present wins; old choices had only recorded_at)
TIME_FIELDS = {"candidate": ("created_at_effective", "created_at"), "plan": ("frozen_at",),
               "revision": ("effective_at", "recorded_at"), "review": ("reviewed_at_effective",),
               "choice": ("effective_at", "recorded_at")}


def cut_rows(rows: list[dict], as_of: str) -> tuple[list[dict], int, int]:
    """(rows effective by the end of the New York day `as_of`, number dropped as later, number dropped as undatable).
    Same rule as the ledger's view: a record that takes effect after the cutoff does not exist yet."""
    cutoff = datetime.combine(date.fromisoformat(as_of), time(23, 59, 59), tzinfo=ds.NY)
    kept, later, undatable = [], 0, 0
    for row in rows:
        fields = TIME_FIELDS.get(row.get("kind"))
        stamp = next((row[f] for f in fields or () if row.get(f)), None)
        try:
            at = ds.parse_utc(stamp) if stamp else None
        except (TypeError, ValueError, AttributeError):
            at = None
        if at is None:
            undatable += 1
        elif at <= cutoff:
            kept.append(row)
        else:
            later += 1
    return kept, later, undatable


def split_factor(ratio) -> float | None:
    """Price multiplier that restores pre-split prices from Yahoo's adjusted ones: "2:1" -> 2, "1:10" -> 0.1."""
    try:
        new, old = (float(x) for x in str(ratio).split(":"))
    except (TypeError, ValueError):
        return None
    return new / old if new > 0 and old > 0 else None


def restore_split_prices(rows: list[list], splits: list[list]) -> tuple[list[list], list[str]]:
    """Rows as they traded: for each split (ex_date, ratio), prices and volume of earlier rows are put back on the
    pre-split per-share basis. Returns (rows, split dates whose ratio could not be read)."""
    rows = [list(r) for r in rows]
    unreadable = []
    for day, ratio in splits:
        factor = split_factor(ratio)
        if factor is None:
            unreadable.append(f"{day}（{ratio}）")
            continue
        for r in rows:
            if r[0] < day:
                for k in range(1, 6):
                    if r[k] is not None:
                        r[k] = round(float(r[k]) * factor, 6)
                if r[6] is not None:
                    r[6] = round(float(r[6]) / factor)
    return rows, unreadable


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
    """Fetches each ticker once; a failure is recorded, never turned into "no data".

    Rows are limited to completed sessions (date <= `last_complete`; the last row is also dropped when the tool says
    its session is incomplete) and put back on the as-traded per-share basis for splits up to `end`
    (`as_of=end` makes the tool undo the splits after `end`)."""

    def __init__(self, start: str, end: str, last_complete: str | None = None):
        self.start, self.end = start, end
        self.last_complete = last_complete or end
        self.rows, self.errors, self.splits = {}, {}, {}
        self.dropped: dict[str, str] = {}      # ticker -> date of the incomplete session that was discarded
        self.unreadable: dict[str, list[str]] = {}

    def get(self, ticker: str):
        if ticker not in self.rows:
            try:
                today = datetime.now(ds.NY).date().isoformat()
                got = data_tools.get_price_history(ticker, start=self.start, end=self.end, as_of=min(self.end, today),
                                                   max_rows=6000)
                rows = [r for r in got["rows"] if r[0] <= self.end]
                if got.get("last_row_incomplete_session") and rows:
                    self.dropped[ticker] = rows.pop()[0]
                late = [r for r in rows if r[0] > self.last_complete]
                if late:
                    self.dropped.setdefault(ticker, late[0][0])
                    rows = [r for r in rows if r[0] <= self.last_complete]
                self.splits[ticker] = [list(x) for x in got.get("splits") or [] if x[0] <= self.end]
                self.rows[ticker], self.unreadable[ticker] = restore_split_prices(rows, self.splits[ticker])
            except Exception as exc:  # noqa: BLE001 - reported, never silently treated as "no data"
                self.rows[ticker], self.errors[ticker] = None, f"{type(exc).__name__}: {exc}"
        return self.rows[ticker]


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return lines


def money(x, nd=2, plus=False):
    if x is None:
        return "—"
    x = 0.0 if abs(x) < 0.5 * 10 ** -nd else x
    return f"{x:+,.{nd}f}" if plus else f"{x:,.{nd}f}"


def group_rows(rows: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    """(candidates, plan_id -> {plan, revisions, reviews, choices}) in file order."""
    candidates = [r for r in rows if r.get("kind") == "candidate"]
    bundles = {r["plan_id"]: {"plan": r, "revisions": [], "reviews": [], "choices": []}
               for r in rows if r.get("kind") == "plan"}
    for r in rows:
        b = bundles.get(r.get("plan_id"))
        if b is None:
            continue
        key = {"revision": "revisions", "review": "reviews", "choice": "choices"}.get(r.get("kind"))
        if key:
            b[key].append(r)
    for b in bundles.values():
        b["revisions"].sort(key=lambda r: r.get("version", 0))
        b["reviews"].sort(key=lambda r: ds.parse_utc(r["reviewed_at_effective"]))
    return candidates, bundles


def frozen_day(plan: dict) -> date:
    return ds.parse_utc(plan["frozen_at"]).astimezone(ds.NY).date()


def leg_note(leg: dict, fill: dict | None = None) -> str:
    if leg["reason"] == "stop":
        return f"收盘 {leg['trigger_close']:g} 在 {leg['trigger_date']} ≤ 失效价 {leg['stop']:g}，次日开盘卖出"
    if leg["reason"] == "review":
        return f"复核 {leg['review_id']}" if leg.get("review_id") else "复核"
    if leg["reason"] == "cap":
        return "cap 日收盘离场"
    if leg["reason"] == "value":
        return "按 as_of 前最后收盘估值，不计卖出成本"
    if fill and fill.get("method") == "limit":
        return f"开盘 {fill['open']:g} 高于区间上限，当日最低触及上限，按上限成交"
    if fill and fill.get("method") == "open" and fill.get("index") is not None:
        return f"{fill['date']} 开盘在区间内，按开盘价成交"
    return "下一常规开盘成交"


def entry_text(plan: dict) -> str:
    """The order-validity sentence for one plan record."""
    if "entry_valid_sessions" not in plan:
        return "挂单有效期：旧记录无该字段，按 1 个交易日处理（只看第一个常规开盘，无限价成交）"
    return f"挂单有效期 {plan['entry_valid_sessions']} 个交易日（限价买单：开盘价或区间上限成交）"


def fill_text(fill: dict) -> str:
    method = {"open": "开盘价", "limit": "限价上限"}.get(fill.get("method"))
    return (f"成交：状态 {fill['status']}；日期 {fill['date'] or '—'}；开盘 {fill['open'] if fill['open'] is not None else '—'}"
            + (f"；成交价 {fill['price']:g}（{method}）" if method else "")
            + (f"；已看 {fill['sessions_scanned']} / {fill['valid_sessions']} 个交易日" if "valid_sessions" in fill else "")
            + f"；股数 {fill['shares'] if fill['shares'] else '—'}")


def legs_table(legs: list[dict], bps: float, fill: dict | None = None) -> list[str]:
    rows = []
    for leg in legs:
        amount = leg["price"] * leg["shares"]
        cost = "—" if leg["reason"] == "value" else money(amount * bps / 10000.0)
        rows.append([leg["date"], "买入" if leg["side"] == "buy" else "卖出", f"{leg['price']:g}", leg["shares"],
                     money(amount), cost, REASON_LABELS.get(leg["reason"], leg["reason"]), leg_note(leg, fill)])
    return table(["日期", "方向", "价格", "股数", "成交额", "成本", "原因", "说明"], rows)


def cap_text(res: dict, as_of: str) -> str:
    if as_of >= res["cap_date"]:
        day = res.get("cap_trading_day")
        return f"cap_date = {res['cap_date']}，已到期" + (f"（cap 交易日 {day}）" if day else "（计划未成交，无 cap 交易日）")
    return f"cap_date = {res['cap_date']}，未到期，open 估值（截至 as_of = {as_of} 前最后一个收盘）"


def day_before(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def score_plan(bundle: dict, book: PriceBook, calendar: list[str], as_of: str) -> dict:
    """{"status", "result" (plan_math.settle output or None), "error"}; status is the plan line status, or
    price_error / settle_error."""
    plan = bundle["plan"]
    rows = book.get(plan["ticker"])
    if rows is None:
        return {"status": "price_error", "result": None, "error": book.errors[plan["ticker"]]}
    prices = ds.align_prices(calendar, rows)
    lows = {r[0]: r[3] for r in rows}      # session low, as traded (needed only by the limit-fill rule)
    bars = plan_math.Bars(prices.dates, prices.open, prices.close, prices.adj, low=[lows.get(d) for d in prices.dates])
    # a discarded incomplete session also ends the scoring window of this ticker
    for ticker in (plan["ticker"], REFERENCE_CALENDAR):
        if ticker in book.dropped:
            as_of = min(as_of, day_before(book.dropped[ticker]))
    try:
        result = plan_math.settle(plan, bundle["revisions"], bundle["reviews"], bars, as_of,
                                  cost_bps_per_side=plan.get("cost_bps_per_side", plan_math.COST_BPS_PER_SIDE),
                                  splits=book.splits.get(plan["ticker"], []),
                                  unparsed_splits=[d for d, ratio in book.splits.get(plan["ticker"], [])
                                                   if split_factor(ratio) is None])
    except plan_math.PlanMathError as exc:
        return {"status": "settle_error", "result": None, "error": str(exc)}
    return {"status": result["lines"]["plan"]["status"], "result": result, "error": None}


def plan_section(bundle: dict, scored: dict, as_of: str) -> list[str]:
    plan = bundle["plan"]
    out = [f"### {plan['ticker']} · `{plan['plan_id']}`" + ("（回放）" if plan.get("replay") else ""), ""]
    versions = scored["result"]["stop_versions"] if scored["result"] else \
        [{"version": 1, "price_invalidation": plan["price_invalidation"]}]
    out += [f"- 论点：{plan['thesis']}",
            f"- 冻结 frozen_at = {plan['frozen_at']}；entry_band = {plan['entry_band']}；entry_ref = {plan['entry_ref']:g}；"
            f"计划股数 {plan['shares_planned']}；R0 = {plan['r0']:g}（预算 {plan['risk_budget']:g}）；"
            f"cost = {plan.get('cost_bps_per_side', plan_math.COST_BPS_PER_SIDE)} bp/边；" + entry_text(plan),
            "- 失效价版本链：" + "；".join(f"v{v['version']} = {v['price_invalidation']:g}"
                                          + (f"（{v['effective_at']} 起）" if v["version"] > 1 else "") for v in versions)]
    if scored["result"]:
        out.append("- " + cap_text(scored["result"], scored["result"]["as_of"]))
    else:
        out.append(f"- cap_date = {frozen_day(plan) + timedelta(days=int(plan['horizon_cap_days']))}（horizon_cap_days = {plan['horizon_cap_days']}）")
    if bundle["reviews"]:
        out.append("- 复核：" + "；".join(f"{r['review_id']} {r['reviewed_at_effective']} {r['thesis_verdict']}/{r['action']}"
                                         for r in bundle["reviews"]))
    if bundle["choices"]:
        out.append("- 用户选择：" + "；".join(f"{c['choice']}（{c.get('ref_id')}）：{c.get('note', '')}" for c in bundle["choices"])
                   + "。选择只用于漏斗计数，不改变结算")
    res = scored["result"]
    if res is None:
        out += ["", f"**{scored['status']}**：{scored['error']}。该计划未结算。", ""]
        return out
    fill = res["fill"]
    out += ["", fill_text(fill), ""]
    bps = res["cost_bps_per_side"]
    summary = []
    for name in plan_math.LINE_NAMES:
        ln = res["lines"][name]
        summary.append([LINE_LABELS[name], ln["status"] + ("（未实现）" if ln["unrealized"] else ""),
                        money(ln["gross"]), money(ln["costs"]), money(ln["net"], plus=True),
                        money(ln["r"], 3, plus=True), money(ln["return_pct"], 2, plus=True),
                        money(ln["min_close_r"], 3, plus=True), ln["end_date"] or "—", ", ".join(ln["flags"]) or "—"])
    out += table(["线", "状态", "毛损益", "成本", "净损益", "R", "收益率%", "途中最低收盘 R", "结束日", "flags"], summary)
    for name in plan_math.LINE_NAMES:
        ln = res["lines"][name]
        out += ["", f"**{LINE_LABELS[name]}成交明细**（{ln['status']}）", ""]
        out += legs_table(ln["legs"], bps, fill) if ln["legs"] else ["（无成交）"]
    pairs = res["pairs"]
    out += ["", "配对差（美元 / R）：" + "；".join(
        f"{label} = {money(pairs[key]['usd'], plus=True)} / {money(pairs[key]['r'], 3, plus=True)}" if pairs[key] else f"{label} = —"
        for key, label in (("plan_minus_hold", "照计划 − 持有"), ("plan_minus_simple", "照计划 − 简单退出"))), ""]
    return out


def funnel(candidates: list[dict], bundles: dict[str, dict], scored: dict[str, dict]) -> list[str]:
    def split(counter_rows):
        return Counter((bool(r.get("replay")), key) for r, key in counter_rows)

    cand = split([(c, c.get("outcome")) for c in candidates])
    status = split([(b["plan"], scored[pid]["status"]) for pid, b in bundles.items()])
    choice = split([(b["plan"], ch["choice"]) for b in bundles.values() for ch in b["choices"]])

    def block(title, counter, keys):
        extra = sorted({k for (_, k) in counter} - set(keys))
        return [f"**{title}**", ""] + table(["项", "实时", "回放"], [
            [k, counter.get((False, k), 0), counter.get((True, k), 0)] for k in [*keys, *extra]]) + [""]

    out = ["## 漏斗", ""]
    out += block("机会（candidate.outcome；plan = 已写成计划）", cand, ["plan", "wait", "not_formed"])
    out += block("计划的结算状态（照计划线；price_error / settle_error = 未能结算）", status,
                 ["unfilled", "expired_unfilled", "not_fillable", "pending", "cancelled_before_fill",
                  "cancelled_stop_before_fill", "open", "closed",
                  "not_settleable",
                  "price_error", "settle_error"])
    out += block("用户选择（choice 行）", choice, ["followed", "declined", "abandoned"])
    return out


def score(rows: list[dict], as_of: str, book: PriceBook | None = None, source: str = "",
          now: datetime | None = None) -> tuple[str, int]:
    """(Markdown, exit code). `book` may be injected; by default prices are fetched from data_tools. `now` is the
    clock used to decide which session is complete (default: the real clock)."""
    date.fromisoformat(as_of)
    complete = last_complete_day(now)
    eff = min(as_of, complete)          # actual cutoff: the last completed session on or before as_of
    total = len(rows)
    rows, later, undatable = cut_rows(rows, eff)
    candidates, bundles = group_rows(rows)
    firsts = [frozen_day(b["plan"]) for b in bundles.values()]
    start = (min([*firsts, date.fromisoformat(eff)]) - timedelta(days=15)).isoformat()
    book = book or PriceBook(start, eff)
    warnings: list[str] = []
    calendar: list[str] = []
    if bundles:
        spy = book.get(REFERENCE_CALENDAR)
        if spy is None:
            raise SystemExit(f"REFUSED: cannot fetch the {REFERENCE_CALENDAR} trading calendar ({book.errors[REFERENCE_CALENDAR]})")
        calendar = sorted({r[0] for r in spy})
    scored = {pid: score_plan(b, book, calendar, eff) for pid, b in bundles.items()}
    for pid, s in scored.items():
        if s["status"] in ("price_error", "settle_error"):
            warnings.append(f"{bundles[pid]['plan']['ticker']}（{pid}）：{s['status']}：{s['error']}；该计划未结算，漏斗记为 {s['status']}")
            continue
        res = s["result"]
        who = f"{bundles[pid]['plan']['ticker']}（{pid}）"
        flags = {f for ln in res["lines"].values() for f in ln["flags"]}
        if "revision_same_day_check" in flags:
            warnings.append(f"{who}：有失效价修订生效于美东 13:00–16:00；提前收市日不在 L1 建模，请人工核对该日是否提前收市、"
                            "该修订是否应在当日收盘判断前生效")
        if "split_ratio_unparsed" in flags:
            warnings.append(f"{who}：冻结日之后有拆股但比例无法解析，此前价格无法还原为当时口径，三条线记 not_settleable"
                            "（flag split_ratio_unparsed，金额留空）")
        if "split_in_window" in flags:
            warnings.append(f"{who}：冻结日至结束日之间有拆股，三条线不可结算（金额留空）")
    for t, day in sorted(book.dropped.items()):
        warnings.append(f"{t}：{day} 的行情未完成（盘中数据），已丢弃，该股评分只到 {day_before(day)}")
    for t, items in sorted(book.unreadable.items()):
        if items:
            warnings.append(f"{t}：拆股比例无法解析（{'、'.join(items)}），此前价格未还原为当时口径；"
                            "冻结日早于该拆股日的计划记 not_settleable")

    out = ["# 交易计划结算（plan/v1，三线）", "",
           f"- 记录：`{source}`（{total} 行，截断后 {len(rows)} 行：{len(candidates)} 个机会，{len(bundles)} 个计划）；评分日 as_of = {as_of}",
           f"- 实际截止：{eff}（美东 {eff} 23:59:59 之前生效的记录、{eff} 之前已完成交易日的行情）"
           + ("" if eff == as_of else f"；as_of {as_of} 的常规交易日尚未收盘，当日行情未用"),
           f"- 已排除：{later} 条在实际截止之后才生效的记录（计划、修订、复核、选择、机会），不进报告与漏斗"
           + (f"；{undatable} 条缺少可判定的生效时间" if undatable else ""),
           "- 成交：限价挂单，从 frozen_at 之后第一个常规交易日起最多 entry_valid_sessions 个交易日（缺字段的旧记录按 1 个交易日、"
           "只看开盘）；逐日按**未复权**价：开盘在区间内按开盘价成交（成交方式“开盘”），开盘高于上限且当日最低价 ≤ 上限按上限成交"
           "（成交方式“限价上限”），开盘低于下限不追低、开盘高于上限未触及则当日不成交，顺延；成交前任一日收盘 ≤ 初始失效价则挂单取消"
           "（cancelled_stop_before_fill）；有效期内未成交 = unfilled；R0 不随实际成交价改变。"
           "成交后止损 = 收盘 ≤ 当时有效失效价（从成交日收盘起查）、次日开盘全部卖出；"
           "复核与修订按其有效时间之后的开盘/收盘生效；cap 到期（as_of >= cap_date）按 cap 日收盘离场，否则按 as_of 前最后收盘估值（未实现）；"
           "第一个可成交开盘已晚于 cap_date 的计划记 expired_unfilled",
           f"- 成本：每笔成交额 × 10 bp，买卖各算一次，估值不算卖出成本；R = 净损益 / R0",
           f"- 数据：`data_tools.get_price_history`（Yahoo，带 as_of；拆股已还原为当时每股口径，窗口内有拆股则不可结算）；"
           f"交易日历 = {REFERENCE_CALENDAR} 的交易日，个股缺行的日子仍在日历内、记为缺价", ""]
    out += ["## 逐计划", ""]
    if not bundles:
        out += ["（无计划）", ""]
    for pid, bundle in sorted(bundles.items(), key=lambda kv: (kv[1]["plan"]["frozen_at"], kv[0])):
        out += plan_section(bundle, scored[pid], eff)
    out += funnel(candidates, bundles, scored)
    if warnings:
        out += ["## 警告", ""] + [f"- {w}" for w in warnings] + [""]
    failed = any(s["status"] in ("price_error", "settle_error") for s in scored.values())
    return "\n".join(out) + "\n", 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plans", type=Path, default=PLANS)
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    as_of = args.as_of or default_as_of()
    date.fromisoformat(as_of)
    rows = read_ledger(args.plans) if args.plans.exists() else []
    try:
        text, code = score(rows, as_of, source=str(args.plans))
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        raise
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
