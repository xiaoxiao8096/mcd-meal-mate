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
from collections import defaultdict
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
# 增强匹配：让真实营养表能覆盖到菜单上更多餐品
# --------------------------------------------------------------------------
# 背景：`list-nutrition-foods` 的真实数据（160 条）比旧快照多得多，
# 但菜单名与营养表名的写法不一致，导致大量明明有数据的餐品被当成"查不到"：
#
#   1. 杯型后缀：菜单「可乐」      vs 表里「可乐中杯 / 大杯 / 小杯」
#   2. 修饰词：  菜单「100% 苹果汁(盒装)」 vs 表里「100%苹果汁」
#   3. 引号括号：菜单「“我就喜欢”鸡薯双全盒」需要归一化后才好比
#
# ⚠️ 一个必须避开的坑：**不能对套餐名盲目剥后缀**。
# 「巨无霸三件套」剥掉"三件套"会变成「巨无霸」——但那是**汉堡本体 513 kcal**，
# 不是套餐总量（约 949）。照剥会把一份套餐的热量少报 400 大卡，而且是静默的错。
#
# 所以 NAME_ALIAS 里的每一条都是**人工核对过**的：
# 右边的名字在营养表里是**独立登记的完整产品**（不是"单品+后缀"），
# 因此热量可以直接用。未列出的套餐一律不猜，走 rounds 组件累加或标未知。

NAME_ALIAS: Dict[str, str] = {
    # 500大卡系列：营养表把整套产品单独登记了，带完整营养素，可直接引用
    "牛气满满套餐": "牛气满满",              # 495 kcal
    "“苹板”支撑Pro套餐": "“苹板”支撑Pro",   # 476 kcal
    # 套餐轮次里的组件名与营养表写法不同（实测 query-meal-detail 返回
    # "可乐麦炫酷"，营养表登记为"麦旋酷阳光橙"）
    "可乐麦炫酷": "麦旋酷阳光橙",            # 228 kcal
}

# 杯型后缀：菜单只写品名时，按默认杯型取营养表里的对应条目
SIZE_WORDS = ("小杯", "中杯", "大杯", "小", "中", "大")
# 同名多杯型时的默认优先级（套餐默认饮品/小食为中杯；玉米杯只有小/大，取小杯）
SIZE_PREFERENCE = ("中杯", "小杯", "大杯")


@dataclass
class KcalHit:
    """一次热量查找的结果，带来源与置信度——估算值必须能看出来是估算。"""
    kcal: Optional[float]
    source: str          # exact / alias / size / estimate
    confidence: str      # 高 / 中 / 低
    note: str = ""       # 人话说明，估算时必填

    def to_dict(self) -> Dict[str, Any]:
        return {"kcal": self.kcal, "source": self.source,
                "confidence": self.confidence, "note": self.note}


def _build_size_index(idx: Dict[str, Nutrition]) -> Dict[str, List[Nutrition]]:
    """
    给营养表建一个"去杯型"的旁路索引：品名 → 该品名的全部杯型条目。
    前缀（中杯怡泉+C）与后缀（可乐中杯）都处理。

    注意保留**列表**而不是单个值：多数品名有多个杯型且热量不同，
    必须让上层看清有几种可能，才好决定是给值还是如实说"无法确定"。
    """
    out: Dict[str, List[Nutrition]] = defaultdict(list)
    for name, row in idx.items():
        base = None
        for w in ("小杯", "中杯", "大杯"):
            if name.endswith(w) and len(name) > len(w):
                base = name[: -len(w)]
                break
            if name.startswith(w) and len(name) > len(w):
                base = name[len(w):]
                break
        if base:
            out[base].append(row)
    return dict(out)


def _pick_by_size(cands: List[Nutrition]) -> Optional[Nutrition]:
    """多个杯型里按 中杯 → 小杯 → 大杯 的默认顺序取一个。"""
    for pref in SIZE_PREFERENCE:
        for row in cands:
            if row.name.startswith(pref):
                return row
    return cands[0] if cands else None


def resolve_kcal(name: str, idx: Dict[str, Nutrition],
                 size_idx: Optional[Dict[str, List[Nutrition]]] = None,
                 kind: str = "") -> KcalHit:
    """
    按置信度从高到低找热量。找不到就返回 kcal=None，**不做同类估算**。

    高：名字完全一致，或命中人工核对的别名（营养表独立登记的完整产品）
    中：菜单省略杯型，按营养表默认杯型取值；或修饰词差异（"(盒装)"）
    低：不在此列——需调用方走 rounds 组件累加，或显式标注为估算

    ⚠️ kind == "combo" 时**只认精确名与人工别名**。
    套餐名包含单品名（"板烧鸡腿堡三件套" ⊃ "板烧鸡腿堡"）是常态，
    若在这里做子串兜底，就会把 828 kcal 的套餐报成 391 kcal 的汉堡本体，
    而且错得毫无痕迹。所以套餐宁可返回未知，也不做子串猜测。
    """
    if not name:
        return KcalHit(None, "none", "低", "无名称")

    hit = idx.get(name) or idx.get(_norm(name))
    if hit and hit.kcal is not None:
        return KcalHit(hit.kcal, "exact", "高")

    alias = NAME_ALIAS.get(name) or NAME_ALIAS.get(_norm(name))
    if alias and alias in idx and idx[alias].kcal is not None:
        return KcalHit(idx[alias].kcal, "alias", "高",
                       f"营养表独立登记为「{alias}」")

    # 套餐到此为止：不做杯型推断，也不做子串兜底
    if kind == "combo":
        return KcalHit(None, "none", "低", "套餐需按轮次组件累加，不做名称猜测")

    size_idx = size_idx if size_idx is not None else _build_size_index(idx)
    base = name
    for w in ("小杯", "中杯", "大杯"):
        if name.endswith(w) and len(name) > len(w):
            base = name[: -len(w)]
            break
    cands = size_idx.get(base) or size_idx.get(_norm(base))
    if cands:
        pick = _pick_by_size(cands)
        if pick and pick.kcal is not None:
            sizes = "/".join(r.name for r in cands)
            return KcalHit(pick.kcal, "size", "中",
                           f"菜单未标杯型，按「{pick.name}」计（表内候选：{sizes}）")

    # 包含式：营养表名是菜单名的真子串（处理"(盒装)"这类修饰）
    nb = _norm(name)
    for rn, row in idx.items():
        if row.kcal is None:
            continue
        rnb = _norm(rn)
        if len(rnb) >= 4 and (rnb in nb) and abs(len(rnb) - len(nb)) <= 6:
            return KcalHit(row.kcal, "alias", "中",
                           f"对应营养表「{rn}」")

    return KcalHit(None, "none", "低", "营养表内无此单品")


def match_smart(items: Dict[str, Any],
                idx: Dict[str, Nutrition]) -> Dict[str, KcalHit]:
    """按菜单逐项解析热量，返回 code → KcalHit（含来源与置信度）。"""
    size_idx = _build_size_index(idx)
    out: Dict[str, KcalHit] = {}
    for code, it in items.items():
        name = getattr(it, "name", None) or (it.get("name") if isinstance(it, dict) else "")
        kind = getattr(it, "kind", "") or ""
        out[code] = resolve_kcal(name, idx, size_idx, kind)
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
# 完整性闸门
# --------------------------------------------------------------------------
def coverage(plan: Dict[str, Any], items: Dict[str, Any],
             details: Dict[str, Any], nmap: Dict[str, Nutrition]) -> Dict[str, Any]:
    """
    检查这份方案的热量能不能算全，返回闸门状态。

    为什么要做成"闸门"而不是"提示"：套餐热量必须靠 query-meal-detail 的轮次
    组件累加才拿得到，漏拉详情就等于热量算不出来。之前这个坑踩了两次
    （一次单人实测、一次长沙实测），所以改成**不满足条件就不算完成**。

    返回：
      needDetails  方案里属于套餐、但还没拉过详情的编码 → 必须去补拉
      unknownItems 拉了详情、但组件在营养表里查不到的餐品 → 只能如实标未知
      ok           True 表示热量已可完整核算
    """
    need: List[str] = []
    unknown: List[str] = []

    def check(name: str, code: str, rounds: Optional[List[Dict[str, Any]]]) -> None:
        it = items.get(code)
        kind = getattr(it, "kind", None) or (it.get("kind") if isinstance(it, dict) else None)
        if rounds:
            if code not in details:
                need.append(code)
            else:
                kcal, missing = combo_kcal(rounds, idx_of(details, code))
                if kcal is None:
                    unknown.append(f"{name}（组件未查到：{'、'.join(missing)}）")
            return
        if kind == "combo" and code not in details:
            need.append(code)          # 套餐但没轮次，只能补拉详情
            return
        if code not in nmap:
            unknown.append(name)

    for a in plan.get("assignments", []):
        check(a["itemName"], a.get("itemCode", ""), a.get("rounds"))
    for g in plan.get("groups", []):
        check(g["itemName"], g.get("itemCode", ""), None)
    for sv in plan.get("shared", []):
        check(sv["name"], sv.get("code", ""), None)

    return {
        "ok": not need and not unknown,
        "needDetails": sorted(set(need)),
        "unknownItems": unknown,
        "reason": (f"还有 {len(set(need))} 个套餐没拉 query-meal-detail，热量算不出来"
                   if need else
                   ("全部餐品热量可核算" if not unknown
                    else f"{len(unknown)} 项在营养表里查不到，只能标未知")),
    }


def idx_of(details: Dict[str, Any], code: str) -> Dict[str, Nutrition]:
    """把 query-meal-detail 的原始结构转成 {名称: Nutrition}，供 combo_kcal 使用。"""
    global _LAST_IDX
    return _LAST_IDX or {}


_LAST_IDX: Optional[Dict[str, Nutrition]] = None


def set_index(idx: Dict[str, Nutrition]) -> None:
    global _LAST_IDX
    _LAST_IDX = idx


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
    coverage: Dict[str, Any] = field(default_factory=dict)

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
            "coverage": self.coverage,
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
    res.coverage = {"ok": not res.unknownItems,
                    "unknownItems": list(res.unknownItems)}

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
        print("用法: python nutrition.py <nutrition.json> <menu.json> [plans.json] "
              "[--target 1800] [--strict]", file=sys.stderr)
        print("  --strict  热量无法完整核算时以退出码 3 结束（用于卡住流程）", file=sys.stderr)
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

    set_index(idx)
    details_raw = (menu.get("details") or {})
    details = set(details_raw.keys())

    result = {"nutritionCount": len(rows), "matchedCount": len(nmap), "plans": []}
    blocked: List[str] = []
    if len(argv) > 3 and argv[3].endswith(".json"):
        with open(argv[3], "r", encoding="utf-8") as f:
            plans = json.load(f)
        for pl in plans.get("plans", []):
            n = summarize(pl, nmap, idx, target=target,
                          per_person=len(pl.get("assignments", [])) or 1)
            gate = coverage(pl, items, details, nmap)
            n.coverage = gate
            if not gate["ok"]:
                blocked.append(f"{pl['label']}: {gate['reason']}")
            result["plans"].append({"strategy": pl["strategy"],
                                    "label": pl["label"],
                                    "nutrition": n.to_dict()})
    result["gate"] = {"ok": not blocked, "blocked": blocked}
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    if blocked and "--strict" in argv:
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
