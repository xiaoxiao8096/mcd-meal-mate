#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦拼餐师 · 方案渲染器
======================
把 plan.py 输出的 JSON 渲染成三种形态：
  text    终端可读摘要（人看）
  markdown 可直接贴进 README 的对比表
  request  逐套方案的 calculate-price 请求体（喂给 MCP 复核用）

用法:
    python render.py plans.json text
    python render.py plans.json markdown
    python render.py plans.json request
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

BAR = "=" * 68


def _round_text(p: Dict[str, Any]) -> str:
    """把一个方案里的人/份/共享菜铺成一行行文本。"""
    lines: List[str] = []
    for a in p.get("assignments", []):
        rounds = " + ".join(r["name"] for r in a.get("rounds", []))
        head = f"  {a['person']}  {a['itemName']}"
        if rounds:
            head += f"  [{rounds}]"
        flag = "  ⚠辣味未标注" if a.get("spicyUnknown") else ""
        lines.append(f"{head:<52}{a['price']:>8.2f}{flag}")
    for g in p.get("groups", []):
        rounds = " + ".join(r["name"] for r in g.get("rounds", []))
        lines.append(
            f"  [{'/'.join(g['members'])} 共食]  {g['itemName']} ×{g['qty']}"
            f"{('  [' + rounds + ']') if rounds else ''}"
            f"{'':<6}{g['subtotal']:>8.2f}"
        )
    for s in p.get("shared", []):
        lines.append(f"  共享  {s['name']} ×{s['qty']}{'':<24}{s['subtotal']:>8.2f}")
    return "\n".join(lines)


def render_text(d: Dict[str, Any]) -> str:
    st = d.get("store", {})
    out: List[str] = []
    out.append(BAR)
    out.append(f"门店：{st.get('storeName','?')}（storeCode={st.get('storeCode','?')}）")
    out.append(f"解析菜单 {d.get('menuItemCount')} 项 / 套餐详情 {d.get('detailCount')} 份")
    out.append(BAR)
    for p in d.get("plans", []):
        out.append("")
        out.append(f"【{p['label']}】  预估总价 ¥{p['estimatedTotal']}   人均 ¥{p['perCapita']}")
        out.append("-" * 68)
        out.append(_round_text(p))
        for w in p.get("warnings", []):
            out.append(f"  ⚠ {w}")
    out.append("")
    out.append(BAR)
    for n in d.get("notes", []):
        out.append(f"· {n}")
    return "\n".join(out)


def render_markdown(d: Dict[str, Any]) -> str:
    rows: List[str] = []
    rows.append("| 方案 | 策略 | 预估总价 | 人均 | 说明 |")
    rows.append("|---|---|---:|---:|---|")
    desc = {
        "cheapest": "每人最低成本主食 + 1 份共享菜，尽量压总价",
        "balanced": "优先套餐、每人不同样 + 共享菜 + 甜品",
        "tasty": "优先匹配个人偏好的丰富套餐，用满预算",
        "share": "用双人/分享餐按份覆盖多人，差额单品补齐",
    }
    for p in d.get("plans", []):
        warn = "；".join(p.get("warnings", []))
        note = desc.get(p["strategy"], "") + (f"（{warn}）" if warn else "")
        rows.append(
            f"| {p['label']} | `{p['strategy']}` | ¥{p['estimatedTotal']} | ¥{p['perCapita']} | {note} |"
        )
    rows.append("")
    rows.append("> 表中金额为按 MCP `currentPrice` 推导的**预估值**，最终以 `calculate-price` 返回为准。")
    return "\n".join(rows)


def render_requests(d: Dict[str, Any]) -> str:
    return json.dumps(
        {p["strategy"]: p["calculatePriceRequest"] for p in d.get("plans", [])},
        ensure_ascii=False, indent=2,
    )


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print("用法: python render.py <plans.json> <text|markdown|request>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        d = json.load(f)
    mode = argv[2]
    fn = {"text": render_text, "markdown": render_markdown, "request": render_requests}.get(mode)
    if not fn:
        print(f"未知模式: {mode}", file=sys.stderr)
        return 2
    print(fn(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
