#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦拼餐师 · 活动感知模块
========================
把「当前正在跑的活动」和「菜单里的餐品」对上号。

为什么需要
----------
麦当劳的活动话术会渗进菜单名：「就「酱」心有所「薯」」→ 出了「鸡薯双全盒」，
「“韩”风刮到了四件套」→ 出了「龙焰鸡腿堡」。拼餐时推当季限定品，比推一个
常规款更有价值——大家正在吃的就是这些。

设计成**活动无关**
------------------
不写死「世界杯」「春节」这类具体活动。输入是 campaign-calendar 的实时返回，
当期换成任何活动（联名、节庆、暑期）都自动生效，无需改代码。

匹配规则
--------
1. 剥掉餐品名里的通用后缀（三件套/四件套/套餐/单品/双人餐…），取核心词
2. 核心词若出现在某条活动的标题或正文里 → 判定为该活动的关联餐品
3. 核心词短于 2 个字不做匹配，避免「派」「薯」这类单字误命中

诚实边界
--------
这是**文本匹配**，不是官方标注。匹配上只能说"活动文案里提到过它"，
不能断言"这就是活动限定款"。所以输出统一叫「活动关联」而不是「限定」。
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

# 剥掉这些后缀，剩下的才是"核心词"
SUFFIXES = (
    "三件套", "四件套", "五件套", "八件套", "双人餐", "两人餐", "分享餐",
    "多人餐", "全家桶", "套餐", "单品", "精选", "心动", "随心拼", "组合",
    "新升级", "全新升级",
)

# 活动标题里这些符号框起来的，是麦当劳的营销话术
QUOTE_PAIRS = (("「", "」"), ("『", "』"), ("“", "”"), ("《", "》"))

# 最小核心词长度，低于此不参与匹配
MIN_CORE_LEN = 2

# 去掉标题里的 emoji 与装饰符号，只留中文文案
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\u2B00-\u2BFF\u2190-\u21FF\uFE0F\u200D]+"
)
emoji = EMOJI


@dataclass
class Campaign:
    date: str
    label: str
    title: str
    content: str

    @property
    def blob(self) -> str:
        return f"{self.title} {self.content}"

    @property
    def slogan(self) -> str:
        """去掉 emoji 后的完整标题，这才是麦当劳真正的营销话术。"""
        s = emoji.sub("", self.title or "")
        s = s.strip().strip("!！~～-—·")
        return re.sub(r"\s{2,}", " ", s)

    @property
    def puns(self) -> List[str]:
        """「」与引号里的单字，是谐音梗的落点（如 就「酱」心有所「薯」）。"""
        out: List[str] = []
        for a, b in QUOTE_PAIRS:
            for m in re.finditer(re.escape(a) + r"(.+?)" + re.escape(b), self.title or ""):
                s = m.group(1).strip()
                if s:
                    out.append(s)
        return out


@dataclass
class CampaignHit:
    code: str
    name: str
    core: str
    campaign_title: str
    date: str
    status: str          # today | upcoming | past

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "core": self.core,
            "campaign": self.campaign_title,
            "date": self.date,
            "status": self.status,
        }


# 麦当劳常在商品名里加一段引号前缀，例如「“我就喜欢”鸡薯双全盒」
# 这类前缀不含菜品信息，匹配前必须剥掉，否则核心词永远对不上活动文案。
BRACKET_PREFIX = re.compile(
    r"^(?:[“「『【\[][^”」』】\]]{0,12}[”」』】\]]\s*)+"
)


def core_name(name: str) -> str:
    """剥掉引号前缀与通用后缀，得到核心词。"""
    s = (name or "").strip()
    prev = None
    while prev != s:                      # 允许连续剥多层，如 「“A”「B”」鸡腿堡
        prev = s
        s = BRACKET_PREFIX.sub("", s).strip()
    for suf in SUFFIXES:
        s = s.replace(suf, "")
    return s.strip()


def _peek(path: str) -> Dict[str, Any]:
    """只读出 queryDate，避免为了一个字段把整个文件解析两遍。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_campaigns(path: str, today: Optional[str] = None) -> List[Campaign]:
    """读 campaign-calendar 的落地 JSON，返回活动列表。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    today = today or data.get("queryDate")
    out: List[Campaign] = []
    for day in data.get("days") or []:
        for c in day.get("campaigns") or []:
            out.append(Campaign(
                date=day.get("date", ""),
                label=day.get("label", ""),
                title=c.get("title", ""),
                content=c.get("content", ""),
            ))
    return out


def match_menu(campaigns: Iterable[Campaign], items: Dict[str, Any],
               today: Optional[str] = None) -> List[CampaignHit]:
    """
    把菜单项与活动对上号。items 可以是 plan.Item 的 {code: Item} 映射。
    """
    camps = list(campaigns)
    if not camps:
        return []
    blobs = [(c, c.blob) for c in camps]
    hits: List[CampaignHit] = []
    for code, it in (items or {}).items():
        name = getattr(it, "name", None) or (it.get("name") if isinstance(it, dict) else "")
        if not name:
            continue
        core = core_name(name)
        if len(core) < MIN_CORE_LEN:
            continue
        for c, blob in blobs:
            if core in blob:
                hits.append(CampaignHit(
                    code=code, name=name, core=core,
                    campaign_title=c.title, date=c.date,
                    status=_status(c.date, today),
                ))
                break
    return hits


def _status(date: str, today: Optional[str]) -> str:
    if not today:
        return "unknown"
    if date == today:
        return "today"
    return "upcoming" if date > today else "past"


def summarize(campaigns: Iterable[Campaign], today: Optional[str] = None) -> Dict[str, Any]:
    """活动概览：今日在跑什么、有哪些营销话术、周边类活动什么时候开售。"""
    camps = list(campaigns)
    today_c = [c for c in camps if _status(c.date, today) == "today"]
    upcoming = [c for c in camps if _status(c.date, today) == "upcoming"]
    slogans: List[str] = []
    puns: List[str] = []
    for c in camps:
        if c.slogan and c.slogan not in slogans:
            slogans.append(c.slogan)
        for x in c.puns:
            if x not in puns:
                puns.append(x)
    return {
        "todayCount": len(today_c),
        "todayTitles": [c.title for c in today_c],
        "upcomingTitles": [c.title for c in upcoming],
        "slogans": slogans,
        "puns": puns,
        "note": "活动关联为文本匹配结果，表示活动文案中提及过该餐品，不等同于官方标注的限定款。",
    }


def annotate_plan(plan: Dict[str, Any], hits: List[CampaignHit]) -> Dict[str, Any]:
    """给一份方案里的餐品打上活动关联标记。"""
    by_code = {h.code: h for h in hits}
    tagged = 0
    for a in plan.get("assignments", []):
        h = by_code.get(a.get("itemCode"))
        if h:
            a["campaign"] = h.campaign_title
            a["campaignStatus"] = h.status
            tagged += 1
    for g in plan.get("groups", []):
        h = by_code.get(g.get("itemCode"))
        if h:
            g["campaign"] = h.campaign_title
            g["campaignStatus"] = h.status
            tagged += 1
    for s in plan.get("shared", []):
        h = by_code.get(s.get("code"))
        if h:
            s["campaign"] = h.campaign_title
            s["campaignStatus"] = h.status
            tagged += 1
    plan["campaignTaggedItems"] = tagged
    return plan


def main(argv: List[str]) -> int:
    if len(argv) not in (3, 4):
        print("用法: python campaign.py <campaigns.json> <menu.json> [plans.json]", file=sys.stderr)
        return 2
    import plan as P  # 复用菜单解析
    camps = load_campaigns(argv[1])
    today = data.get("queryDate") if (data := _peek(argv[1])) else None
    with open(argv[2], "r", encoding="utf-8") as f:
        menu = json.load(f)
    items = P.parse_menu(menu.get("menu") or menu)
    hits = match_menu(camps, items, today)
    result = {
        "summary": summarize(camps, today),
        "campaignCodes": [h.code for h in hits],
        "queryDate": today,
        "hits": [h.to_dict() for h in hits],
        "hitCount": len(hits),
    }
    if len(argv) == 4:
        with open(argv[3], "r", encoding="utf-8") as f:
            plans = json.load(f)
        for p in plans.get("plans", []):
            annotate_plan(p, hits)
        result["plans"] = plans.get("plans", [])
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
