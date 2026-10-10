#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把本次实测（2026-10-10 18:13，衡阳船山餐厅 3390023）的菜单落成引擎可读的 case。
菜单主体沿用样本（同一门店），并补进本次新增的 36 个餐品。
"""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(BASE, "data", "sample-case-4p-180.json")
LIVE = os.path.join(BASE, "data", "live-store-3390023.json")
OUT = os.path.join(BASE, "data", "case-live-3390023.json")

with open(SAMPLE, encoding="utf-8") as f:
    base = json.load(f)
with open(LIVE, encoding="utf-8") as f:
    live = json.load(f)

base["store"] = live["store"]
base["_source"] = live["_source"]

menu = base["menu"]
meals = menu.setdefault("meals", {})
cats = menu.setdefault("categories", [])

# 本次新增餐品挂到对应分类
CAT_OF = {
    "9900016077": "蘸酱炸鸡", "9900016078": "蘸酱炸鸡", "9900016079": "蘸酱炸鸡",
    "9900016096": "蘸酱炸鸡", "9900015729": "小食拼盘\n/多人餐",
    "521966": "小食甜品\n/其他", "521917": "小食甜品\n/其他",
    "506189": "小食甜品\n/其他", "521743": "小食甜品\n/其他",
    "9900016057": "开心乐园", "9900016058": "开心乐园", "9900016056": "开心乐园",
    "9900016055": "开心乐园", "9900005439": "开心乐园",
    "9900004236": "精选单人餐", "9900010110": "精选单人餐",
    "9900006957": "精选单人餐", "9900011056": "小食拼盘\n/多人餐",
    "9900000888": "巨无霸\n牛鱼肉堡", "9900000886": "巨无霸\n牛鱼肉堡",
    "9900000885": "巨无霸\n牛鱼肉堡", "9900000884": "巨无霸\n牛鱼肉堡",
    "9900000890": "鸡肉汉堡\n/卷", "9900000891": "鸡肉汉堡\n/卷",
    "9900016309": "鸡肉汉堡\n/卷", "9900016310": "鸡肉汉堡\n/卷",
    "9900016301": "精选单人餐", "9900000882": "安格斯MAX\n厚牛堡",
    "9900000881": "安格斯MAX\n厚牛堡", "9900000893": "巨无霸\n牛鱼肉堡",
    "9900005321": "小食拼盘\n/多人餐", "9900005413": "巨无霸\n牛鱼肉堡",
    "9900005460": "巨无霸\n牛鱼肉堡", "9900005428": "安格斯MAX\n厚牛堡",
    "9900005430": "安格斯MAX\n厚牛堡", "9900003586": "巨无霸\n牛鱼肉堡",
}
TAG_OF = {
    "9900016077": ["新品"], "9900016078": ["新品"], "9900016079": ["新品"],
    "9900016096": ["新品"], "9900015729": ["新品"],
    "521966": ["蘸酱"], "521917": ["新品"],
}
# 四件套/随心选都是麦金卡随单购，引擎暂不建模，只标个标签
for code, _n, _p, _o in live["newItemsVsSample"]:
    c = str(code)
    if c in meals:
        continue
    meals[c] = {"name": _n, "currentPrice": str(_p), "originalPrice": str(_o)}
    cat = CAT_OF.get(c, "小食甜品\n/其他")
    tgt = next((x for x in cats if x["name"] == cat), None)
    if tgt is None:
        tgt = {"name": cat, "meals": []}
        cats.append(tgt)
    tgt.setdefault("meals", []).append({"code": c, "tags": TAG_OF.get(c, [])})

# 本次实测到的组合（用于热量组件累加）
base["details"] = {
    "9900005456": {
        "code": "9900005456", "name": "麦辣鸡腿汉堡三件套",
        "rounds": [
            {"id": 1, "name": "麦辣鸡腿汉堡", "quantity": 1, "minQuantity": 1, "maxQuantity": 1,
             "choices": [{"code": "1440", "name": "麦辣鸡腿汉堡", "isDefault": 1, "diffPrice": "+ ¥0"}]},
            {"id": 2, "name": "选择套餐内小食", "quantity": 1, "minQuantity": 1, "maxQuantity": 1,
             "choices": [{"code": "4810", "name": "中薯条", "isDefault": 1, "diffPrice": "+ ¥0"},
                         {"code": "4437", "name": "小杯玉米杯", "isDefault": 0, "diffPrice": "- ¥1"},
                         {"code": "514782", "name": "脆脆薯条", "isDefault": 0, "diffPrice": "+ ¥2"}]},
            {"id": 3, "name": "选择套餐内饮料", "quantity": 1, "minQuantity": 1, "maxQuantity": 1,
             "choices": [{"code": "3050", "name": "可乐中杯", "isDefault": 1, "diffPrice": "+ ¥0"},
                         {"code": "3071", "name": "无糖可口可乐中杯", "isDefault": 0, "diffPrice": "+ ¥0"},
                         {"code": "4437", "name": "玉米杯", "isDefault": 0, "diffPrice": "+ ¥0"}]},
        ],
    }
}
# 券：本次实测 data 为空
base["coupons"] = []
base["_couponNote"] = "2026-10-10 18:13 实测 query-store-coupons 返回 data: []，当日无可用券"

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(base, f, ensure_ascii=False)
print(f"已生成 {OUT}")
print(f"菜单餐品数: {len(meals)}（新增 {len(live['newItemsVsSample'])}）")