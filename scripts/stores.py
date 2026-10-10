#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦拼餐师 · 门店优选
====================
`query-nearby-stores` 会把附近的店全列出来，但用户不该在一堆店里面自己挑。

这个模块做三件事：
1. **校验城市对不对**——如果所有门店名都不含你填的城市，说明城市填错了。
   （真实踩过：把湖南工商大学南校区当成衡阳，实际在长沙。）
2. **滤掉已经打烊的**——用 `businessStartTime` / `businessEndTime` 和当前时间比。
   凌晨两点查到一批店却全都关门了，是最蠢的失败。
3. **按距离排序**，并标出是否支持预约、是否还剩可选时段。
4. **给一句话推荐**——人数多/要预约/现在关门，都会影响选哪家。

时区说明
--------
接口返回的营业时间是**当地时间**（北京时间），不带时区标记；
本模块假定它就是本地时间，用 `now-time-info` 取的当前时间做比较。
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def _hhmm(s: str) -> Optional[int]:
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _hhmm_to_min(t: Optional[int]) -> str:
    if t is None:
        return "?"
    return f"{t // 60:02d}:{t % 60:02d}"


def is_open(store: Dict[str, Any], now_min: int) -> bool:
    """
    判断此刻是否在营业时间内。

    注意跨零点：比如 07:00–01:00（次日），now=23:30 应该算营业中。
    """
    a, b = _hhmm(store.get("businessStartTime")), _hhmm(store.get("businessEndTime"))
    if a is None or b is None:
        return True                      # 没给营业时间就不筛，别误杀
    if a <= b:
        return a <= now_min <= b
    return now_min >= a or now_min <= b   # 跨零点


def next_slot(store: Dict[str, Any], today: Optional[str]) -> Optional[str]:
    """从 reservationTimeOptions 里找出今天还可选的时段，取最后一个（最晚）。"""
    for opt in store.get("reservationTimeOptions") or []:
        if today and opt.get("date") != today:
            continue
        txt = opt.get("reservationOptionText") or ""
        if txt:
            return txt
    return None


def city_mismatch(stores: List[Dict[str, Any]], city: str) -> List[str]:
    """
    找出店名里不含所填城市的门店。

    这是个真实踩过的坑：把「湖南工商大学南校区」当成衡阳（实际在长沙），
    接口照样返回了衡阳的门店——因为 city 过滤确实生效了，错的是填进去的值。
    所以这里做一次反向校验：城市填错时，店名会集体对不上。
    """
    if not city or not stores:
        return []
    c = city.strip().replace("市", "")
    return [s.get("storeName", "") for s in stores if c not in (s.get("storeName") or "")]


def pick(stores: List[Dict[str, Any]], now_min: int, today: Optional[str] = None,
         limit: int = 3, city: Optional[str] = None) -> Dict[str, Any]:
    """
    优选门店。

    返回 {open, closed, best, reason}
      open   此刻营业中的店，按距离升序
      closed 此刻已打烊的店（也返回，方便如实告知"这家现在不开"）
      best   推荐的第一家
      reason 推荐理由，一句话
    """
    if not stores:
        return {"open": [], "closed": [], "best": None, "warning": "",
                "reason": "没查到门店"}

    op = [s for s in stores if s.get("businessStatus", True) and is_open(s, now_min)]
    cl = [s for s in stores if not (s.get("businessStatus", True) and is_open(s, now_min))]
    key = lambda s: (s.get("distance") is None, s.get("distance") or 0)  # noqa: E731
    op.sort(key=key)
    cl.sort(key=key)

    warn = ""
    bad = city_mismatch(stores, city or "")
    if bad and len(bad) == len(stores):
        warn = (f"⚠ 返回的 {len(bad)} 家门店名都不含「{city}」，"
                f"城市很可能填错了，请和用户确认城市后再继续")
    elif bad:
        warn = f"⚠ 有 {len(bad)} 家门店名不含「{city}」，请确认是否跨城"

    if not op:
        return {"open": [], "closed": cl[:limit], "best": None, "warning": warn,
                "reason": f"附近这几家此刻都没营业（{_hhmm_to_min(now_min)}），换个时间或换附近门店"}

    best = op[0]
    bits = [f"{best.get('distance')} 米"]
    if best.get("reservation"):
        slot = next_slot(best, today)
        bits.append("支持预约" + (f"，今天还有 {slot}" if slot else ""))
    else:
        bits.append("不支持预约")
    end = best.get("businessEndTime")
    if end:
        bits.append(f"营业到 {end}")
    return {"open": op[:limit], "closed": cl[:limit], "best": best,
            "warning": warn, "reason": " · ".join(bits)}


def render(result: Dict[str, Any]) -> str:
    L = ["📍 门店", ""]
    if result.get("warning"):
        L.append(result["warning"])
        L.append("")
    best = result.get("best")
    if best:
        L.append(f"  推荐  {best['storeName']}（{best['storeCode']}）")
        L.append(f"        {result['reason']}")
        L.append("")
    for s in result.get("open", []):
        star = "★" if best and s["storeCode"] == best["storeCode"] else " "
        L.append(f"  {star} {s['storeName']}  {s.get('distance')} 米  {s.get('address','')}")
    for s in result.get("closed", []):
        L.append(f"    ✕ {s['storeName']}  已打烊（{s.get('businessEndTime')} 结束）")
    L.append("")
    L.append(f"  {result['reason']}")
    return "\n".join(L)


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print("用法: python stores.py <stores.json> [--now 13:30] [--today 2026-10-10] [--city 长沙]", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        d = json.load(f)
    now = argv[argv.index("--now") + 1] if "--now" in argv else "12:00"
    today = argv[argv.index("--today") + 1] if "--today" in argv else None
    city = argv[argv.index("--city") + 1] if "--city" in argv else None
    n = _hhmm(now) or 720
    print(render(pick(d.get("data") or [], n, today, city=city)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
