#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""活动感知自测。核心断言：活动数据必须真的改变决策，而不只是打个标记。"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import campaign as C  # noqa: E402
import plan as P  # noqa: E402

_p = _f = 0
SAMPLE = os.path.join(ROOT, "data", "sample-case-4p-180.json")
CAMPS = os.path.join(ROOT, "data", "sample-campaigns.json")


def check(name: str, cond: bool, detail: str = "") -> None:
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS  {name}")
    else:
        _f += 1
        print(f"  FAIL  {name}  {detail}")


def load():
    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = P.parse_menu(data["menu"])
    tags = {c: it.tags for c, it in items.items()}
    details = {}
    for code, d in (data["details"] or {}).items():
        it = items.get(str(code))
        det = P.parse_detail(d, it.price if it else 0.0, tags)
        if det:
            details[str(code)] = det
    people = [P.Person(pid=x["id"], avoid=list(x.get("avoid") or []),
                      prefer=list(x.get("prefer") or [])) for x in data["group"]["people"]]
    return data, items, details, people


def test_core_name():
    print("\n[1] 核心词剥离")
    check("龙焰鸡腿堡三件套 → 龙焰鸡腿堡", C.core_name("龙焰鸡腿堡三件套") == "龙焰鸡腿堡")
    check("麦麦周末双人餐 → 麦麦周末", C.core_name("麦麦周末双人餐") == "麦麦周末")
    check("巨无霸三件套 → 巨无霸", C.core_name("巨无霸三件套") == "巨无霸")
    check("派 → 派（不剥）", C.core_name("派") == "派")
    check("新升级巨无霸 → 巨无霸", C.core_name("新升级巨无霸") == "巨无霸")


def test_match():
    print("\n[2] 活动关联识别")
    data, items, details, people = load()
    camps = C.load_campaigns(CAMPS)
    with open(CAMPS, encoding="utf-8") as f:
        today = json.load(f)["queryDate"]
    hits = C.match_menu(camps, items, today)
    names = [h.name for h in hits]
    check("识别到龙焰鸡腿堡三件套", "龙焰鸡腿堡三件套" in names, str(names))
    check("识别到蓝莓爆爆珠麦旋风", "蓝莓爆爆珠麦旋风" in names)
    check("识别到灰焰圆筒", "灰焰圆筒" in names)
    check("识别到鸡薯双全盒", "“我就喜欢”鸡薯双全盒" in names)
    # 不该出现的
    check("麦香鸡未被误判（活动文案里没有）", "麦香鸡" not in names)
    check("派 未被误判（单字核心词不参与匹配）", "派" not in names)
    # 状态
    h = next((x for x in hits if x.name == "龙焰鸡腿堡三件套"), None)
    check("状态标记为 today", h is not None and h.status == "today", h.status if h else "None")


def test_slogan():
    print("\n[3] 营销话术提取")
    camps = C.load_campaigns(CAMPS)
    s = C.summarize(camps, "2026-10-10")
    check("提取到今日活动 15 条", s["todayCount"] == 15, str(s["todayCount"]))
    check("话术列表非空", len(s["slogans"]) > 0)
    check("话术已去掉 emoji", not any("🫐" in x or "🩶" in x or "🆕" in x for x in s["slogans"]))
    joined = " ".join(s["slogans"])
    check("保留了完整语义（就「酱」心有所「薯」）", "就「酱」心有所「薯」" in joined, joined[:80])
    check("谐音梗落点被单独抽出", set(s["puns"]) >= {"酱", "薯"}, str(s["puns"]))


def test_campaign_changes_decision():
    print("\n[4] 活动数据真的改变决策（这是本模块存在的意义）")
    data, items, details, people = load()
    budget = float(data["group"]["budget"])

    # 无活动数据
    P._CAMPAIGN_CODES.clear()
    plain = {st: P.build_plan(st, people, items, details, budget) for st in
             ("value", "cheapest", "tasty")}

    # 有活动数据
    camps = C.load_campaigns(CAMPS)
    hits = C.match_menu(camps, items, "2026-10-10")
    P._CAMPAIGN_CODES.clear()
    P._CAMPAIGN_CODES.update(h.code for h in hits)
    aware = {st: P.build_plan(st, people, items, details, budget) for st in
             ("value", "cheapest", "tasty")}

    # 极致省钱：价格优先，活动不该改变它
    pn = [s.name for _, s in plain["cheapest"].per_person]
    an = [s.name for _, s in aware["cheapest"].per_person]
    check("极致省钱：活动数据不改变选择（价格优先）", pn == an, f"{pn} vs {an}")

    # 性价比：camp 排在 is_rich 之后，只在"同样是套餐"时才起作用，
    # 所以允许变化，但不能把套餐换成单品
    pn = [s.name for _, s in plain["value"].per_person]
    an = [s.name for _, s in aware["value"].per_person]
    check("性价比：总价仍不超预算", aware["value"].total <= budget, str(aware["value"].total))

    # 当季尝鲜：活动必须改变选择
    pn = [s.name for _, s in plain["tasty"].per_person]
    an = [s.name for _, s in aware["tasty"].per_person]
    check("当季尝鲜：活动数据改变了选择", pn != an, f"{pn} vs {an}")
    camp_names = {h.name for h in hits}
    check("当季尝鲜：至少一人拿到活动限定品",
          any(n in camp_names for n in an), str(an))
    check("当季尝鲜：总价未超预算", aware["tasty"].total <= budget, str(aware["tasty"].total))
    check("当季尝鲜：仍满足不吃辣约束",
          all(s.flavour.spicy is not True
              for p, s in aware["tasty"].per_person if "spicy" in p.avoid))
    P._CAMPAIGN_CODES.clear()


def test_annotate():
    print("\n[5] 方案标注")
    data, items, details, people = load()
    camps = C.load_campaigns(CAMPS)
    hits = C.match_menu(camps, items, "2026-10-10")
    P._CAMPAIGN_CODES.clear()
    P._CAMPAIGN_CODES.update(h.code for h in hits)
    pl = P.build_plan("tasty", people, items, details, float(data["group"]["budget"]))
    d = pl.to_dict(data["store"])
    C.annotate_plan(d, hits)
    check("标注了活动项数 > 0", d.get("campaignTaggedItems", 0) > 0, str(d.get("campaignTaggedItems")))
    tagged = [a for a in d["assignments"] if a.get("campaign")]
    check("被标注的项都带活动名", all(a["campaign"] for a in tagged), str(len(tagged)))
    P._CAMPAIGN_CODES.clear()


def main() -> int:
    print("=" * 62)
    print("活动感知 · 离线自测")
    print("=" * 62)
    test_core_name()
    test_match()
    test_slogan()
    test_campaign_changes_decision()
    test_annotate()
    print("\n" + "=" * 62)
    print(f"通过 {_p} / 失败 {_f}")
    print("=" * 62)
    return 0 if _f == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
