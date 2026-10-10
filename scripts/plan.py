#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦拼餐师 · 规划引擎
==================
纯离线计算模块。不联网、不调用 MCP、只吃 JSON、只吐 JSON。

设计原则
--------
1. 菜单与套餐详情由调用方（WorkBuddy Agent）通过麦当劳 MCP 取得后传入，
   本模块负责"组合优化"这一纯计算环节。好处是：引擎可离线单测，不依赖
   网络与账号；价格一律来自 MCP 返回的 currentPrice，绝不臆造。
2. 任何无法从数据中确认的信息一律标为 unknown 并向上抛出，由上层如实
   告知用户"查不到"，不做降级猜测。
3. 所有方案最终都要由 calculate-price 复核，本模块只负责给出候选与请求体。

四种策略
--------
value     性价比首选：命中偏好 > 套餐优先 > 当季活动 > 价格从低到高（主打）
cheapest  极致省钱：每人最低成本主食 + 1 份共享小食，不加甜品
tasty     当季尝鲜：同样先保证是套餐，最后取贵的把预算用满
share     多人拼单：优先用双人/分享餐按"份"覆盖多人，差额用单品补齐
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# --------------------------------------------------------------------------
# 口味判定
# --------------------------------------------------------------------------
# 仅做"名称/标签文本命中"的启发式判定，不是成分表。
# 命中不到时 spicy 为 None（未知），由上层如实说明，绝不默认"不辣"即"安全"。
SPICY_HINTS = ("辣", "川香", "麻辣", "黑椒")
CHICKEN_HINTS = ("鸡", "鸡腿", "鸡翅")
FISH_HINTS = ("鱼", "鳕鱼")
BEEF_HINTS = ("牛",)


@dataclass
class Flavour:
    spicy: Optional[bool] = None
    chicken: bool = False
    fish: bool = False
    beef: bool = False


def detect_flavour(*texts: str) -> Flavour:
    blob = " ".join(t for t in texts if t)
    if not blob:
        return Flavour()
    return Flavour(
        spicy=any(h in blob for h in SPICY_HINTS),
        chicken=any(h in blob for h in CHICKEN_HINTS),
        fish=any(h in blob for h in FISH_HINTS),
        beef=any(h in blob for h in BEEF_HINTS),
    )


# --------------------------------------------------------------------------
# 分类
# --------------------------------------------------------------------------
COMBO_HINTS = ("三件套", "四件套", "套餐")
SHARE_HINTS = ("双人餐", "两人餐", "分享餐", "全家桶", "多人餐")
RICH_HINTS = ("三件套", "四件套")
MAIN_HINTS = ("汉堡", "堡", "卷", "鱼", "鸡排", "随心配", "吉士")
SHARE_SIDE_HINTS = ("薯条", "小食", "拼盘", "鸡块", "鸡翅", "脆薯饼", "芝士条", "鸡薯双全", "V翅")
BIG_SHARE_HINTS = ("拼盘", "双拼", "分享", "全家", "鸡薯双全", "十翅", "八件", "随心拼")
DESSERT_HINTS = ("新地", "派", "冰淇淋", "圆筒", "麦旋风")
DRINK_HINTS = ("可乐", "雪碧", "红茶", "咖啡", "牛奶", "果汁", "怡泉", "美汁源", "麦炫酷", "水")


@dataclass
class Item:
    code: str
    name: str
    price: float
    original_price: float
    tags: List[str]
    category: str
    flavour: Flavour
    kind: str = "unknown"        # combo | main | share_side | dessert | drink | unknown
    serves: int = 1              # 一份可满足几人（分享餐为 2）

    @property
    def is_share_meal(self) -> bool:
        return self.serves >= 2

    @property
    def is_complete_meal(self) -> bool:
        """套餐/随心配类自带小食或饮料，比裸单品更接近"一顿完整饭"。"""
        return self.kind == "combo" or "随心配" in self.name

    @property
    def is_big_share(self) -> bool:
        return any(h in self.name for h in BIG_SHARE_HINTS)


def classify(name: str, category: str) -> str:
    cat = (category or "").replace("\n", "").replace("/", "")
    n = name or ""
    if any(h in n for h in SHARE_HINTS):
        return "combo"
    if any(h in n for h in COMBO_HINTS) or "套餐" in cat or "单人餐" in cat:
        return "combo"
    if any(h in n for h in DESSERT_HINTS) or "冰淇淋" in cat:
        return "dessert"
    if any(h in n for h in DRINK_HINTS) or "饮品" == cat:
        return "drink"
    # 共享小食只认名称里的线索：小食甜品/其他 这个分类太杂，不能整包当共享菜
    if any(h in n for h in SHARE_SIDE_HINTS) or "拼盘" in cat:
        return "share_side"
    if any(h in n for h in MAIN_HINTS) or "堡" in cat:
        return "main"
    return "unknown"


def estimate_serves(name: str) -> int:
    n = name or ""
    if "全家桶" in n:
        return 4
    if any(h in n for h in SHARE_HINTS):
        return 2
    return 1


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_diff_price(raw: str) -> float:
    """把 "+ ¥1.5" / "- ¥1" / "+¥0" 解析成 float。未识别返回 0.0。"""
    if raw is None:
        return 0.0
    s = re.sub(r"\s+", "", str(raw)).replace("¥", "").replace("+", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


@dataclass
class Choice:
    code: str
    name: str
    diff: float
    is_default: bool
    flavour: Flavour


@dataclass
class Round:
    rid: str
    name: str
    min_qty: int
    max_qty: int
    choices: List[Choice]

    @property
    def required(self) -> bool:
        return self.min_qty >= 1


@dataclass
class Detail:
    code: str
    name: str
    base_price: float
    rounds: List[Round]


def parse_menu(menu_data: Dict[str, Any]) -> Dict[str, Item]:
    code_to_cat: Dict[str, str] = {}
    code_to_tags: Dict[str, List[str]] = {}
    for cat in menu_data.get("categories") or []:
        cname = (cat.get("name") or "").replace("\n", "").replace("/", "")
        for m in cat.get("meals") or []:
            c = str(m.get("code"))
            code_to_cat[c] = cname
            code_to_tags[c] = [str(t) for t in (m.get("tags") or [])]

    items: Dict[str, Item] = {}
    for code, body in (menu_data.get("meals") or {}).items():
        name = body.get("name") or ""
        cat = code_to_cat.get(str(code), "")
        tags = code_to_tags.get(str(code), [])
        price = _f(body.get("currentPrice"))
        items[str(code)] = Item(
            code=str(code),
            name=name,
            price=price,
            original_price=_f(body.get("originalPrice"), price),
            tags=tags,
            category=cat,
            flavour=detect_flavour(name, *tags),
            kind=classify(name, cat),
            serves=estimate_serves(name),
        )
    return items


def parse_detail(detail_data: Dict[str, Any], base_price: float,
                 tags_by_code: Optional[Dict[str, List[str]]] = None) -> Optional[Detail]:
    """
    tags_by_code：菜单里 code → tags 的映射。

    必须带上它。套餐详情的 choices 只有名称，没有 tags；像「酥酥多笋卷」这种
    名字里没有"辣"、但菜单标签写着「川香风味」的餐品，只看名字会被误判成不辣。
    choice.code 与菜单 item.code 是同一套编码，据此回查标签才能补全口味信息。
    """
    if not detail_data:
        return None
    tags_by_code = tags_by_code or {}
    rounds: List[Round] = []
    for r in detail_data.get("rounds") or []:
        choices = [
            Choice(
                code=str(c.get("code")),
                name=c.get("name") or "",
                diff=parse_diff_price(c.get("diffPrice")),
                is_default=str(c.get("isDefault")) == "1",
                flavour=detect_flavour(c.get("name") or "",
                                       *tags_by_code.get(str(c.get("code")), [])),
            )
            for c in (r.get("choices") or [])
        ]
        rounds.append(Round(
            rid=str(r.get("id")),
            name=r.get("name") or "",
            min_qty=int(r.get("minQuantity") or 0),
            max_qty=int(r.get("maxQuantity") or 0),
            choices=choices,
        ))
    return Detail(code=str(detail_data.get("code")),
                  name=detail_data.get("name") or "",
                  base_price=base_price, rounds=rounds)


# --------------------------------------------------------------------------
# 约束
# --------------------------------------------------------------------------
@dataclass
class Person:
    pid: str
    avoid: List[str] = field(default_factory=list)
    prefer: List[str] = field(default_factory=list)


def spicy_conflict(p: Person, fl: Flavour) -> bool:
    """仅在明确命中辣味关键词时判为冲突；未知（None）不阻断，但需上层标注。"""
    return "spicy" in p.avoid and fl.spicy is True


def preference_hits(p: Person, fl: Flavour) -> int:
    n = 0
    if "chicken" in p.prefer and fl.chicken:
        n += 1
    if "fish" in p.prefer and fl.fish:
        n += 1
    if "beef" in p.prefer and fl.beef:
        n += 1
    return n


# --------------------------------------------------------------------------
# 选配求解
# --------------------------------------------------------------------------
@dataclass
class Selection:
    code: str
    name: str
    price: float
    rounds: List[Tuple[str, Choice]] = field(default_factory=list)
    spicy_unknown: bool = False
    flavour: Flavour = field(default_factory=Flavour)

    def signature(self) -> str:
        return self.code + "|" + ",".join(f"{rid}:{ch.code}" for rid, ch in self.rounds)


def solve_rounds(detail: Detail, person: Person, used: Optional[Set[str]] = None) -> Optional[Selection]:
    """
    为一份可轮换餐品选出满足 person 约束、且总价最低的选配。

    used_sig：全组已用过的选配签名，用于避免两个人吃到完全相同的一份。
    任一必选轮次没有合法选项时返回 None——这是"不吃辣的人不能用这份套餐"的
    判定依据，宁可整份弃用也不把辣餐端上去。
    """
    used = used or set()

    # 每一轮按 (偏好命中, 价格, 是否默认) 排好序
    ordered: List[List[Choice]] = []
    legal_flags: List[bool] = []
    for rd in detail.rounds:
        legal: List[Choice] = []
        for ch in rd.choices:
            if rd.required and spicy_conflict(person, ch.flavour):
                continue
            legal.append(ch)
        if not legal:
            return None
        legal_flags.append("spicy" in person.avoid and any(c.flavour.spicy is None for c in legal))
        ordered.append(sorted(
            legal,
            key=lambda c: (-preference_hits(person, c.flavour), detail.base_price + c.diff, not c.is_default),
        ))

    unknown = any(legal_flags)

    def build(picks: List[Choice]) -> Tuple[float, List[Tuple[str, Choice]], Flavour]:
        total = detail.base_price
        pairs: List[Tuple[str, Choice]] = []
        spicy_any = chicken = fish = beef = False
        for rd, ch in zip(detail.rounds, picks):
            total += ch.diff
            pairs.append((rd.rid, ch))
            spicy_any = spicy_any or (ch.flavour.spicy is True)
            chicken = chicken or ch.flavour.chicken
            fish = fish or ch.flavour.fish
            beef = beef or ch.flavour.beef
        fl = Flavour(spicy=True if spicy_any else (None if unknown else False),
                     chicken=chicken, fish=fish, beef=beef)
        return round(total, 2), pairs, fl

    def sig_of(pairs: List[Tuple[str, Choice]]) -> str:
        return detail.code + "|" + ",".join(f"{rid}:{ch.code}" for rid, ch in pairs)

    # 基准组合：每轮都取最优
    picks = [lst[0] for lst in ordered]
    total, pairs, fl = build(picks)
    if not used or sig_of(pairs) not in used:
        return Selection(code=detail.code, name=detail.name, price=total,
                         rounds=pairs, spicy_unknown=unknown, flavour=fl)

    # 撞车了：允许在有限范围内改动轮次，挑一个"没被用过且最便宜"的组合
    best: Optional[Tuple[float, List[Tuple[str, Choice]], Flavour]] = None
    for r in range(len(ordered)):
        for alt in ordered[r][1:4]:
            cand = list(picks)
            cand[r] = alt
            t, p2, f2 = build(cand)
            if sig_of(p2) in used:
                continue
            if best is None or t < best[0]:
                best = (t, p2, f2)
    if best:
        return Selection(code=detail.code, name=detail.name, price=best[0],
                         rounds=best[1], spicy_unknown=unknown, flavour=best[2])
    return Selection(code=detail.code, name=detail.name, price=total,
                     rounds=pairs, spicy_unknown=unknown, flavour=fl)


# --------------------------------------------------------------------------
# 方案
# --------------------------------------------------------------------------
STRATEGIES = {
    "value": "性价比首选",
    "cheapest": "极致省钱",
    "tasty": "当季尝鲜",
    "share": "多人拼单",
}

# 各策略的共享配置：(共享小食份数, 甜品份数)
SHARED_RECIPE = {
    "cheapest": (1, 0),
    "value": (2, 1),
    "tasty": (3, 2),
    "share": (1, 1),
}

# 共享菜最多占总预算的比例——人均再便宜也不该把一大半钱花在共享上
SHARED_BUDGET_RATIO = 0.25


@dataclass
class Group:
    """一份可覆盖多人的餐品（如双人分享餐），由 members 共同分摊。"""
    members: List[str]
    code: str
    name: str
    qty: int
    unit_price: float
    rounds: List[Tuple[str, Choice]] = field(default_factory=list)

    @property
    def subtotal(self) -> float:
        return round(self.unit_price * self.qty, 2)


@dataclass
class Plan:
    strategy: str
    label: str
    per_person: List[Tuple[Person, Selection]]
    shared: List[Tuple[Item, int]]
    groups: List[Group] = field(default_factory=list)
    headcount: int = 0
    warnings: List[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        s = sum(sel.price for _, sel in self.per_person)
        s += sum(it.price * q for it, q in self.shared)
        s += sum(g.subtotal for g in self.groups)
        return round(s, 2)

    def to_dict(self, store: Dict[str, Any]) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        assign: List[Dict[str, Any]] = []
        assigned_ids = {p.pid for p, _ in self.per_person}
        for person, sel in self.per_person:
            entry: Dict[str, Any] = {"productCode": sel.code, "quantity": 1}
            if sel.rounds:
                entry["roundList"] = [
                    {"round": rid, "comboItemList": [{"code": ch.code, "quantity": 1}]}
                    for rid, ch in sel.rounds
                ]
            items.append(entry)
            assign.append({
                "person": person.pid,
                "avoid": person.avoid,
                "prefer": person.prefer,
                "itemCode": sel.code,
                "itemName": sel.name,
                "rounds": [
                    {"round": rid, "code": ch.code, "name": ch.name, "diff": ch.diff}
                    for rid, ch in sel.rounds
                ],
                "price": sel.price,
                "spicyUnknown": sel.spicy_unknown,
                "isCampaignItem": sel.code in _CAMPAIGN_CODES,
            })
        for g in self.groups:
            entry = {"productCode": g.code, "quantity": g.qty}
            if g.rounds:
                entry["roundList"] = [
                    {"round": rid, "comboItemList": [{"code": ch.code, "quantity": 1}]}
                    for rid, ch in g.rounds
                ]
            items.append(entry)
        for it, q in self.shared:
            items.append({"productCode": it.code, "quantity": q})
        return {
            "strategy": self.strategy,
            "label": self.label,
            "estimatedTotal": self.total,
            "perCapita": round(self.total / max(1, self.headcount or len(assigned_ids) or len(self.per_person)), 2),
            "assignments": assign,
            "groups": [
                {
                    "members": g.members,
                    "itemCode": g.code,
                    "itemName": g.name,
                    "qty": g.qty,
                    "unitPrice": g.unit_price,
                    "subtotal": g.subtotal,
                    "rounds": [
                        {"round": rid, "code": ch.code, "name": ch.name, "diff": ch.diff}
                        for rid, ch in g.rounds
                    ],
                }
                for g in self.groups
            ],
            "shared": [
                {"code": it.code, "name": it.name, "qty": q,
                 "unitPrice": it.price, "subtotal": round(it.price * q, 2)}
                for it, q in self.shared
            ],
            "warnings": self.warnings,
            "calculatePriceRequest": {
                "storeCode": store.get("storeCode"),
                "orderType": store.get("orderType"),
                "beType": store.get("beType"),
                "items": items,
            },
        }


def candidate_selections(
    person: Person,
    items: Dict[str, Item],
    details: Dict[str, Detail],
    used: Set[str],
) -> List[Selection]:
    out: List[Selection] = []
    for code, it in items.items():
        if it.kind not in ("combo", "main") or it.price <= 0:
            continue
        if spicy_conflict(person, it.flavour):
            continue
        d = details.get(code)
        if d and d.rounds:
            sel = solve_rounds(d, person, used)
            if sel:
                out.append(sel)
        else:
            # 没拉过 query-meal-detail 的套餐，我们不知道轮次里有什么，
            # 即使套餐名本身不含辣味关键词，也必须标成"辣味未知"，
            # 不能默认它不辣。这是"不猜"原则的落点。
            unknown = "spicy" in person.avoid
            out.append(Selection(code=it.code, name=it.name, price=it.price,
                                 spicy_unknown=unknown, flavour=it.flavour))
    return out


def rank(sel: Selection, person: Person, strategy: str, used: Set[str]) -> Tuple:
    """排序键：越小越优先。"""
    pref = -preference_hits(person, sel.flavour)      # 命中偏好优先
    dup = 1 if sel.signature() in used else 0          # 与已选重复则降权
    is_rich = 0 if any(h in sel.name for h in RICH_HINTS) else 1
    is_share = 0 if any(h in sel.name for h in SHARE_HINTS) else 1
    if strategy == "cheapest":
        # 2 元一档分桶：同档内优先"自带饮料/小食的完整套餐"，
        # 避免为了省 0.4 元给出一个只有干巴巴一个汉堡的方案。
        bucket = int(-(-sel.price // 2))
        return (dup, bucket, 0 if sel.flavour is not None and _is_complete(sel) else 1, sel.price, pref)
    camp = 0 if sel.code in _CAMPAIGN_CODES else 1
    if strategy == "value":
        # 性价比：命中偏好 > 套餐优先 > 当季活动 > 价格从低到高。
        # 套餐排在活动前面，因为套餐自带小食饮料，比单点划算（实测省 15.5 元）。
        return (dup, pref, is_rich, camp, sel.price)
    if strategy == "tasty":
        # 当季尝鲜：同样先保证是套餐，最后取贵的把预算用满。
        # 注意 is_rich 必须在 camp 之前——否则会挑到当季新品单品，
        # 出现"尝鲜比性价比还便宜"的反直觉结果。
        return (dup, pref, is_rich, camp, -sel.price)
    # share：优先能覆盖多人份的
    return (dup, pref, is_share, is_rich, sel.price)


_COMPLETE_CACHE: Dict[str, bool] = {}
# campaign-calendar 判定为"活动关联"的餐品编码。由输入 JSON 的 campaignCodes 注入。
# 作用：在"同样是套餐"的前提下，活动限定品获得优先级——大家正在吃的就是这些。
#       排序里它排在 is_rich 之后，所以不会把套餐降级成单品。
_CAMPAIGN_CODES: Set[str] = set()


def _is_complete(sel: Selection) -> bool:
    return _COMPLETE_CACHE.get(sel.code, False)


def build_plan(strategy: str, people: List[Person], items: Dict[str, Item],
               details: Dict[str, Detail], budget: float) -> Optional[Plan]:
    global _COMPLETE_CACHE
    _COMPLETE_CACHE = {c: it.is_complete_meal for c, it in items.items()}
    warnings: List[str] = []
    used: Set[str] = set()
    per_person: List[Tuple[Person, Selection]] = []

    if strategy == "share":
        return _build_share_plan(people, items, details, budget, warnings)

    for p in people:
        cands = candidate_selections(p, items, details, used)
        if not cands:
            warnings.append(f"{p.pid}：菜单中找不到同时满足其忌口与偏好的主食，需人工确认")
            return None
        cands.sort(key=lambda s: rank(s, p, strategy, used))
        pick = cands[0]
        used.add(pick.signature())
        per_person.append((p, pick))

    n_side, n_dessert = SHARED_RECIPE[strategy]
    sides = sorted(
        [i for i in items.values() if i.kind == "share_side" and i.price > 0],
        key=lambda i: (0 if i.is_big_share else 1, i.price),
    )
    desserts = sorted([i for i in items.values() if i.kind == "dessert" and i.price > 0],
                      key=lambda i: i.price)
    shared: List[Tuple[Item, int]] = []
    if strategy == "cheapest":
        if sides:
            # 只挑"看起来真的够分"的：拼盘/双拼/鸡薯双全这类，或最便宜的一份
            big = [s for s in sides if s.is_big_share]
            shared.append((big[0] if big else sides[0], 1))
    else:
        for s in sides[:n_side]:
            shared.append((s, 1))
        for s in desserts[:n_dessert]:
            shared.append((s, 1))

    # 人多时共享小食按份数补：4 人以上至少两份像样的共享菜
    if len(people) >= 4 and strategy != "cheapest":
        expanded: List[Tuple[Item, int]] = []
        for it, q in shared:
            if it.kind == "share_side" and it.is_big_share and q == 1:
                expanded.append((it, 2))
            else:
                expanded.append((it, q))
        shared = expanded

    plan = Plan(strategy=strategy, label=STRATEGIES[strategy],
                per_person=per_person, shared=shared,
                headcount=len(people), warnings=warnings)
    _enforce_budget(plan, budget)
    return plan


def _build_share_plan(people: List[Person], items: Dict[str, Item],
                      details: Dict[str, Detail], budget: float,
                      warnings: List[str]) -> Optional[Plan]:
    """
    多人拼单：优先用「一份覆盖 2 人」的双人/分享餐铺满，余下差额用单品补齐。
    关键约束：若某份分享餐对某人的忌口不合法（必选轮次全是辣），就整体放弃它，
    绝不把辣餐端给明确说不吃辣的人。
    """
    share_items = [i for i in items.values() if i.kind == "combo" and i.serves >= 2 and i.price > 0]
    share_items.sort(key=lambda i: i.price / i.serves)

    picked: Optional[Item] = None
    for it in share_items:
        d = details.get(it.code)
        if spicy_conflict(Person("probe"), it.flavour):
            continue
        if d and d.rounds and solve_rounds(d, people[0]) is None:
            continue
        legal = True
        for p in people:
            if spicy_conflict(p, it.flavour):
                legal = False
                break
            if d and d.rounds and solve_rounds(d, p) is None:
                legal = False
                break
        if legal:
            picked = it
            break

    if picked is None:
        warnings.append("没有分享餐能同时满足全组忌口，改用逐人单品方案")
        return build_plan("value", people, items, details, budget)

    d = details.get(picked.code)
    n = len(people)
    qty = -(-n // picked.serves)          # ceil
    base_sel = solve_rounds(d, people[0]) if (d and d.rounds) else None
    unit = base_sel.price if base_sel else picked.price

    groups = [Group(
        members=[p.pid for p in people],
        code=picked.code, name=picked.name, qty=qty, unit_price=unit,
        rounds=base_sel.rounds if base_sel else [],
    )]
    per_person: List[Tuple[Person, Selection]] = []
    for n_p, p in enumerate(people):
        if n_p >= qty * picked.serves:
            cands = candidate_selections(p, items, details, set())
            if not cands:
                warnings.append(f"{p.pid}：找不到满足忌口的主食")
                return None
            cands.sort(key=lambda s: rank(s, p, "value", set()))
            per_person.append((p, cands[0]))

    sides = sorted(
        [i for i in items.values() if i.kind == "share_side" and i.price > 0],
        key=lambda i: (0 if i.is_big_share else 1, i.price),
    )
    desserts = sorted([i for i in items.values() if i.kind == "dessert" and i.price > 0],
                      key=lambda i: i.price)
    n_side, n_dessert = SHARED_RECIPE["share"]
    shared: List[Tuple[Item, int]] = [(s, 1) for s in sides[:n_side]] + [(s, 1) for s in desserts[:n_dessert]]

    plan = Plan(strategy="share", label=STRATEGIES["share"], per_person=per_person,
                shared=shared, groups=groups, headcount=n, warnings=warnings)
    _enforce_budget(plan, budget)
    return plan


def _enforce_budget(plan: Plan, budget: float) -> None:
    """超预算时，先减分享餐份数，再砍共享小食与甜品（从贵到便宜），最后如实上报。"""
    if plan.total <= budget:
        return
    # 共享菜总额不得超过总预算的 SHARED_BUDGET_RATIO，
    # 否则会出现"人均 50 但一半钱花在共享菜上"的方案。
    cap = budget * SHARED_BUDGET_RATIO
    shared_total = sum(it.price * q for it, q in plan.shared)
    if shared_total > cap:
        for entry in sorted(plan.shared, key=lambda x: -x[0].price * x[1]):
            if shared_total <= cap:
                break
            if entry in plan.shared:
                shared_total -= entry[0].price * entry[1]
                plan.shared.remove(entry)

    # 甜品最先砍（最不必要），再砍共享小食，最后才动分享餐份数
    for phase in ("dessert", "share_side"):
        pool = [x for x in plan.shared if x[0].kind == phase]
        for entry in sorted(pool, key=lambda x: -x[0].price):
            if plan.total <= budget:
                break
            if entry in plan.shared:
                plan.shared.remove(entry)
    for g in plan.groups:
        while g.qty > 1 and plan.total > budget:
            g.qty -= 1
    if plan.total > budget:
        floor = min([s.price for _, s in plan.per_person] +
                    [g.unit_price for g in plan.groups] or [0])
        plan.warnings.append(
            f"预算 {budget} 元过紧：砍完共享菜后总价仍约 {plan.total} 元"
            f"（人均下限约 {round(floor, 2)} 元），建议放宽预算或减少人数")


# --------------------------------------------------------------------------
def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("用法: python plan.py <input.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)

    store = data.get("store") or {}
    items = parse_menu(data.get("menu") or {})
    details: Dict[str, Detail] = {}
    tags_by_code = {c: it.tags for c, it in items.items()}
    for code, d in (data.get("details") or {}).items():
        it = items.get(str(code))
        det = parse_detail(d, it.price if it else 0.0, tags_by_code)
        if det:
            details[str(code)] = det

    group = data.get("group") or {}
    people = [
        Person(pid=p.get("id", f"P{i+1}"),
               avoid=list(p.get("avoid") or []),
               prefer=list(p.get("prefer") or []))
        for i, p in enumerate(group.get("people") or [])
    ]
    if not people:
        people = [Person(pid=f"P{i+1}") for i in range(int(group.get("headcount") or 2))]
    budget = float(group.get("budget") or 0) or float("inf")

    # 活动关联餐品：由 campaign.py 产出 campaignCodes 后注入。
    # 必须在这里统一注入一次——build_plan 每个策略都会调用，
    # 若在其内部清空集合，后续策略将看不到任何活动数据。
    _CAMPAIGN_CODES.clear()
    for c in (data.get("campaignCodes") or []):
        _CAMPAIGN_CODES.add(str(c))

    result = {
        "store": store,
        "menuItemCount": len(items),
        "detailCount": len(details),
        "plans": [],
        "notes": [
            "价格来自 MCP currentPrice，最终以 calculate-price 为准。",
            "辣味为名称/标签文本判定，非成分表，不构成过敏建议。",
            "spicyUnknown=true 表示该餐品辣味未确认。",
            "isCampaignItem=true 表示该餐品出现在当期活动文案中。",
        ],
    }
    for st in (data.get("strategies") or list(STRATEGIES.keys())):
        plan = build_plan(st, people, items, details, budget)
        if plan:
            result["plans"].append(plan.to_dict(store))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
