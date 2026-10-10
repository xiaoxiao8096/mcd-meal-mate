#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦拼餐师 · 营养热量模块
========================
把 `list-nutrition-foods` 的返回解析成可用的营养表，挂到菜单与方案上。

为什么要单独一个模块
------------------
`list-nutrition-foods` 返回的是一个**字符串**，格式很怪：

    [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,
     carbohydrate,sodium,calcium}:
      巨无霸,null,2146,513,27,26,42,961,171
      ...

不是 JSON、不是 CSV，得自己拆。

三条诚实边界（重要）
-------------------
1. **营养表里没有套餐**。只有单品（巨无霸、板烧鸡腿堡、可乐中杯……），
   三件套/随心配本身不在表里。要估算套餐只能按 query-meal-detail 的轮次
   组件逐个累加，**任何一个组件查不到就整体标未知，绝不用同类餐品估算**。
2. **"去掉酱料能省多少大卡"接口没有给**。modification 只告诉你哪些酱料
   可以去掉，不给去掉后的热量。所以只能推荐"可以去掉巨无霸酱"，
   **不能承诺"省 200 大卡"**。
3. 热量与营养是**参考值**，不构成营养或医疗建议。

能做实的部分
------------
- 逐项热量、蛋白质、脂肪、碳水、钠
- 方案总热量 vs 用户给定的热量目标
- **低卡替换建议**：用营养表里有数据的项做对比，例如
  可乐中杯 147 kcal → 无糖可口可乐 0 kcal（这个换是有据可依的）
- 高热量项提醒（标出整单里热量大头）
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

HEADER = re.compile(r"^\[(\d+)\]\{(.*)\}:\s*$", re.M)


@dataclass
class Nutrition:
    name: str
    kcal: Optional[float]
    protein: Optional[float]
    fat: Optional[float]
    carb: Optional[float]
    sodium: Optional[float]
    calcium: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "kcal": self.kcal, "protein": self.protein,
                "fat": self.fat, "carb": self.carb, "sodium": self.sodium,
                "calcium": self.calcium}


def parse(raw: str) -> List[Nutrition]:
    """
    解析 list-nutrition-foods 的字符串返回。

    形如：
        [160]{productName,...,calcium}:
          猪柳麦满分,null,1288,308,16,16,24,781,213
          ...
    名称里可能自带逗号以外的字符，按"从右往左取 8 个数字字段"更稳，
    这里采用：前导名称 = 逗号分隔后的第 0 项，其余按位置解析。
    """
    if not raw:
        return []
    text = raw.strip()
    m = HEADER.search(text)
    body = text[m.end():] if m else text

    out: List[Nutrition] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        # 结构： name, nutritionDescription, kj, kcal, protein, fat, carb, sodium, calcium
        if len(parts) < 9:
            continue
        name = parts[0].strip()
        vals: List[Optional[float]] = []
        for x in parts[2:9]:                    # 7 个数值字段
            try:
                vals.append(float(x))
            except ValueError:
                vals.append(None)
        if len(vals) < 7 or vals[1] is None:
            continue
        out.append(Nutrition(
            name=name,
            kcal=vals[1], protein=vals[2], fat=vals[3], carb=vals[4],
            sodium=vals[5], calcium=vals[6],
        ))
    return out


def build_index(rows: Iterable[Nutrition]) -> Dict[str, Nutrition]:
    """名称 → 营养。名称做一次轻量归一化，方便与菜单名对齐。"""
    idx: Dict[str, Nutrition] = {}
    for r in rows:
        idx[r.name.strip()] = r
    return idx


def _norm(s: str) -> str:
    """去掉书名号/引号/方括号与空白，让「“我就喜欢”鸡薯双全盒」也能对上。"""
    s = re.sub(r"[“”「」『』【】\[\]（）()·]", "", s or "")
    return re.sub(r"\s+", "", s)


def match(items: Dict[str, Any], idx: Dict[str, Nutrition]) -> Dict[str, Nutrition]:
    """
    把菜单项挂上营养数据。返回 code → Nutrition（只含匹配上的）。
    匹配不上的**不返回**，上层据此显示"热量未知"，不用同类估算。
    """
    norm = {_norm(k): v for k, v in idx.items()}
    out: Dict[str, Nutrition] = {}
    for code, it in items.items():
        name = getattr(it, "name", None) or (it.get("name") if isinstance(it, dict) else "")
        if not name:
            continue
        hit = idx.get(name) or norm.get(_norm(name))
        if hit:
            out[code] = hit
    return out


# --------------------------------------------------------------------------
# 低卡替换建议
# --------------------------------------------------------------------------
# 分类 → 同类里热量最低的候选。仅用于"换点什么更省"，不改变餐品身份。
CATEGORY_RULES = [
    ("可乐",        ["可乐中杯", "无糖可口可乐中杯", "可乐小杯", "无糖可口可乐小杯"]),
    ("雪碧",        ["雪碧中杯", "雪碧小杯"]),
    ("红茶",        ["锡兰红茶", "阳光柠檬红茶小杯"]),
    ("咖啡",        ["冰美式小杯", "热美式小杯", "冰美式中杯"]),
    ("牛奶",        ["纯牛奶（盒装）", "热牛奶小杯", "纯悦"]),
    ("奶昔",        ["优品豆浆小杯", "冰燕麦奶小杯", "热燕麦奶小杯"]),
    ("冰淇淋",      ["圆筒冰淇淋", "纯悦", "苹果片"]),
    ("派",          ["菠萝派", "香芋派"]),
    ("薯条",        ["小薯条", "迷你薯条", "中薯条", "脆脆薯条"]),
]


def swap_suggestions(item_name: str, idx: Dict[str, Nutrition],
                     limit: int = 2) -> List[Dict[str, Any]]:
    """
    给某个高热量品项找同类更低碳的替代。只在营养表里确实有数据时才提。
    返回 [{from, to, save}]，save 是 kcal 差值（来自表内数据，不是估算）。
    """
    cur = idx.get(item_name) or next((v for k, v in idx.items() if _norm(k) == _norm(item_name)), None)
    if not cur or cur.kcal is None:
        return []
    out: List[Dict[str, Any]] = []
    for key, cands in CATEGORY_RULES:
        if key not in (item_name or ""):
            continue
        for c in cands:
            alt = idx.get(c)
            if not alt or alt.kcal is None or alt.name == item_name:
                continue
            if alt.kcal < cur.kcal:
                out.append({"from": item_name, "to": alt.name,
                            "fromKcal": cur.kcal, "toKcal": alt.kcal,
                            "save": round(cur.kcal - alt.kcal, 1)})
        break
    out.sort(key=lambda x: -x["save"])
    return out[:limit]


# --------------------------------------------------------------------------
# 去酱建议
# --------------------------------------------------------------------------
# 麦当劳特调项里常见的"可以不要"的高脂配料。
DROPPABLE_HINTS = ("酱", "芝士", "吉士", "奶油", "沙拉酱", "蛋黄酱", "千岛酱")

def drop_suggestions(detail: Optional[Dict[str, Any]]) -> List[str]:
    """
    从 query-meal-detail 的 modification 里挑出"可以去掉"的配料名。

    ⚠️ 只给名称，**不给热量节省数字**——MCP 没有提供去掉后的热量。
    """
    if not detail:
        return []
    out: List[str] = []
    items = ((detail.get("modification") or {}).get("items")) or []
    for it in items:
        for v in it.get("values") or []:
            nm = (v.get("name") or "").strip()
            if nm and any(h in nm for h in DROPPABLE_HINTS):
                out.append(nm)
    return sorted(set(out))


def combo_kcal(rounds: Optional[List[Dict[str, Any]]],
               idx: Dict[str, Nutrition]) -> Tuple[Optional[float], List[str]]:
    """
    套餐热量 = 各轮次选中组件的热量之和。

    这是唯一有据可依的算法：query-meal-detail 告诉我们这份套餐实际选了
    哪些组件，而 list-nutrition-foods 给出了每个组件的热量，逐个相加即可。

    任何一个组件在营养表里查不到，就返回 None 并列出缺哪些——
    **绝不用"同类套餐大概多少"去估算**。
    """
    if not rounds:
        return None, []
    total = 0.0
    missing: List[str] = []
    norm = {_norm(k): v for k, v in idx.items()}
    for r in rounds:
        nm = r.get("name") or ""
        hit = idx.get(nm) or norm.get(_norm(nm))
        if not hit or hit.kcal is None:
            missing.append(nm)
        else:
            total += hit.kcal
    return (None if missing else round(total, 1)), missing


# --------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------
@dataclass
class PlanNutrition:
    known: bool = True
    totalKcal: float = 0.0
    knownItems: int = 0
    unknownItems: List[str] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    swaps: List[Dict[str, Any]] = field(default_factory=list)
    drops: List[str] = field(default_factory=list)
    tips: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "known": self.known,
            "totalKcal": round(self.totalKcal, 1),
            "knownItems": self.knownItems,
            "unknownItems": self.unknownItems,
            "rows": self.rows,
            "swaps": self.swaps,
            "drops": self.drops,
            "tips": self.tips,
        }


def summarize(plan: Dict[str, Any], nmap: Dict[str, Nutrition],
              idx: Dict[str, Nutrition], details: Optional[Dict[str, Any]] = None,
              target: Optional[float] = None,
              per_person: int = 1) -> PlanNutrition:
    """
    汇总一份方案的热量。

    target  用户给定的每人每日热量目标；给了就做对比与提醒。
    """
    res = PlanNutrition()
    seen_swap_from = set()

    def add(name: str, qty: int, code: str,
            rounds: Optional[List[Dict[str, Any]]] = None) -> None:
        # 套餐：按轮次组件累加；单品/无轮次：直接查表
        if rounds:
            kcal, missing = combo_kcal(rounds, idx)
            if kcal is None:
                res.unknownItems.append(f"{name}（组件未查到：{'、'.join(missing)}）")
                return
            res.totalKcal += kcal * qty
            res.knownItems += 1
            comp = " + ".join(r.get("name", "") for r in rounds)
            res.rows.append({"name": name, "qty": qty, "kcal": round(kcal / qty, 1),
                             "kcalTotal": round(kcal * qty, 1),
                             "components": comp,
                             "protein": None, "fat": None, "sodium": None})
            return
        n = nmap.get(code)
        if not n or n.kcal is None:
            res.unknownItems.append(f"{name} ×{qty}")
            return
        k = n.kcal * qty
        res.totalKcal += k
        res.knownItems += 1
        res.rows.append({
            "name": name, "qty": qty, "kcal": round(n.kcal, 1),
            "kcalTotal": round(k, 1),
            "protein": n.protein, "fat": n.fat, "sodium": n.sodium,
        })
        if n.kcal >= 400 and name not in seen_swap_from:
            for s in swap_suggestions(n.name, idx):
                if s["from"] not in seen_swap_from:
                    seen_swap_from.add(s["from"])
                    res.swaps.append(s)

    for a in plan.get("assignments", []):
        add(a["itemName"], 1, a.get("itemCode", ""), a.get("rounds"))
    for g in plan.get("groups", []):
        add(g["itemName"], g.get("qty", 1), g.get("itemCode", ""))
    for sv in plan.get("shared", []):
        add(sv["name"], sv.get("qty", 1), sv.get("code", ""))

    if res.unknownItems:
        res.known = False

    if details:
        for code in (a.get("itemCode") for a in plan.get("assignments", [])):
            d = details.get(code)
            if d:
                drops = drop_suggestions(d)
                if drops:
                    res.drops.extend(drops)
        res.drops = sorted(set(res.drops))

    # 提醒
    if target and target > 0 and (res.known or res.totalKcal > 0):
        avg = res.totalKcal / max(1, per_person)
        pct = avg / target * 100
        res.tips.append(f"人均约 {avg:.0f} kcal，为目标 {target:.0f} kcal 的 {pct:.0f}%")
        if avg > target:
            over = avg - target
            res.tips.append(f"超出约 {over:.0f} kcal，可从上面的替换建议里挑一个换掉")
        elif avg > target * 0.9:
            res.tips.append("接近目标上限，注意别再加共享菜")
        else:
            res.tips.append("在目标之内 👍")
    if res.swaps:
        best = res.swaps[0]
        res.tips.append(f"把「{best['from']}」换成「{best['to']}」能省 {best['save']:.0f} kcal")
    if res.drops:
        res.tips.append("可去掉：" + "、".join(res.drops[:4]) + "（MCP 未提供去酱后的热量，不估算）")
    if not res.known:
        res.tips.insert(0, "部分餐品不在营养表内，总热量只是已查到的部分，不是全单真实值")

    return res


def render(res: PlanNutrition, per_person: int) -> str:
    L: List[str] = []
    head = "🔥 热量" if res.known else "🔥 热量（部分未知）"
    L.append(head)
    L.append("")
    for r in res.rows:
        L.append(f"  {r['name'][:30]:<32}{r['kcalTotal']:>8.0f} kcal")
    L.append("")
    L.append(f"  合计 {res.totalKcal:.0f} kcal    人均 {res.totalKcal/max(1,per_person):.0f} kcal")
    if res.unknownItems:
        L.append(f"  未查到：{'、'.join(res.unknownItems)}")
    if res.swaps:
        L.append("")
        L.append("  💡 换个更轻的")
        for s in res.swaps:
            L.append(f"     {s['from']} → {s['to']}   省 {s['save']:.0f} kcal")
    for t in res.tips:
        L.append(f"  · {t}")
    return "\n".join(L)


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print("用法: python nutrition.py <nutrition.json> <menu.json> [plans.json] [--target 1800]", file=sys.stderr)
        return 2
    import plan as P
    with open(argv[1], "r", encoding="utf-8") as f:
        raw = json.load(f)
    rows = parse(raw.get("raw") or "")
    idx = build_index(rows)
    with open(argv[2], "r", encoding="utf-8") as f:
        menu = json.load(f)
    items = P.parse_menu(menu.get("menu") or menu)
    nmap = match(items, idx)

    target = None
    if "--target" in argv:
        try:
            target = float(argv[argv.index("--target") + 1])
        except (IndexError, ValueError):
            pass

    result = {"nutritionCount": len(rows), "matchedCount": len(nmap), "plans": []}
    if len(argv) > 3 and argv[3].endswith(".json"):
        with open(argv[3], "r", encoding="utf-8") as f:
            plans = json.load(f)
        for pl in plans.get("plans", []):
            n = summarize(pl, nmap, idx, target=target,
                          per_person=len(pl.get("assignments", [])) or 1)
            result["plans"].append({"strategy": pl["strategy"],
                                    "label": pl["label"],
                                    "nutrition": n.to_dict()})
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
