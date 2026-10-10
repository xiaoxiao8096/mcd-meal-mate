#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门店优选自测。核心断言：城市填错必须被检出。"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import stores as S  # noqa: E402

_p = _f = 0
SAMPLE = os.path.join(ROOT, "data", "sample-stores.json")


def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS  {name}")
    else:
        _f += 1
        print(f"  FAIL  {name}  {detail}")


def main() -> int:
    print("=" * 62)
    print("门店优选 · 离线自测")
    print("=" * 62)
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)["data"]

    print("\n[1] 营业时间判定（含跨零点）")
    hm = lambda x: int(x[:2]) * 60 + int(x[3:])  # noqa: E731
    d0 = {"businessStartTime": "07:00", "businessEndTime": "23:59"}
    d1 = {"businessStartTime": "07:00", "businessEndTime": "01:00"}
    check("23:59 打烊的店，13:30 营业中", S.is_open(d0, hm("13:30")))
    check("23:59 打烊的店，23:59 仍算营业中", S.is_open(d0, hm("23:59")))
    check("01:00 打烊的店，23:50 营业中（跨零点）", S.is_open(d1, hm("23:50")))
    check("01:00 打烊的店，00:30 营业中（跨零点）", S.is_open(d1, hm("00:30")))
    check("01:00 打烊的店，03:00 不营业", not S.is_open(d1, hm("03:00")))
    check("无营业时间字段时不筛", S.is_open({}, hm("03:00")))

    print("\n[2] 城市一致性校验（实测踩过的坑）")
    check("填对城市时无告警", S.pick(data, hm("17:00"), "2026-10-10", city="衡阳")["warning"] == "")
    r = S.pick(data, hm("17:00"), "2026-10-10", city="长沙")
    check("填错城市时告警", bool(r["warning"]), r["warning"])
    check("告警文案点明城市名", "长沙" in r["warning"], r["warning"])

    print("\n[3] 优选结果")
    r = S.pick(data, hm("17:00"), "2026-10-10", city="衡阳")
    check("给出推荐门店", r["best"] is not None)
    check("推荐最近的一家", r["best"]["distance"] == min(x["distance"] for x in data))
    check("理由含距离与营业时间", "米" in r["reason"] and "营业到" in r["reason"], r["reason"])
    r3 = S.pick(data, hm("03:00"), "2026-10-10", city="衡阳")
    check("凌晨无店营业时如实报告", r3["best"] is None and "没营业" in r3["reason"], r3["reason"])

    print("\n" + "=" * 62)
    print(f"通过 {_p} / 失败 {_f}")
    print("=" * 62)
    return 0 if _f == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
