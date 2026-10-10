# 引擎输出格式

`scripts/plan.py` 输出一个 JSON，`scripts/render.py` 把它渲染成三种形态。

## 顶层

```jsonc
{
  "store": { ... },                  // 原样回显
  "menuItemCount": 82,               // 解析出的菜单项数
  "detailCount": 3,                  // 解析出的套餐详情数
  "plans": [ ... ],                  // 五套方案
  "notes": [ ... ]                   // 固定提示语
}
```

## 单套方案

```jsonc
{
  "strategy": "value",               // value | cheapest | tasty | share
  "label": "性价比首选",
  "estimatedTotal": 87.4,            // 引擎预估值（元）——不是权威值
  "perCapita": 21.85,
  "assignments": [                   // 每人一份主食
    {
      "person": "P1",
      "avoid": ["spicy"],
      "prefer": [],
      "itemCode": "9900013304",
      "itemName": "人气经典随心配",
      "rounds": [
        { "round": "1", "code": "521316", "name": "高达吉士双牛堡", "diff": -1.0 },
        { "round": "2", "code": "521328", "name": "可乐麦炫酷",     "diff": 0.0 }
      ],
      "price": 13.9,
      "spicyUnknown": false           // true = 没拉过详情，无法确认辣味
    }
  ],
  "groups": [                        // 一份覆盖多人的餐（仅 share 策略）
    {
      "members": ["P1", "P2", "P3", "P4"],
      "itemCode": "9900015151",
      "itemName": "麦麦周末双人餐",
      "qty": 2,
      "unitPrice": 49.9,
      "subtotal": 99.8,
      "rounds": []
    }
  ],
  "shared": [                        // 共享小食与甜品
    { "code": "9900016076", "name": "“我就喜欢”鸡薯双全盒",
      "qty": 2, "unitPrice": 15.9, "subtotal": 31.8 }
  ],
  "warnings": ["预算 180 元过紧：……"],
  "calculatePriceRequest": {         // 原样丢给 MCP calculate-price 即可
    "storeCode": "3390023",
    "orderType": 1,
    "beType": 1,
    "items": [
      { "productCode": "9900013304", "quantity": 1,
        "roundList": [
          { "round": "1", "comboItemList": [{ "code": "521316", "quantity": 1 }] },
          { "round": "2", "comboItemList": [{ "code": "521328", "quantity": 1 }] }
        ] },
      { "productCode": "9900016076", "quantity": 2 }
    ]
  }
}
```

## 两个必须记住的换算

| 来源 | 单位 | 处理 |
|---|---|---|
| `query-meals` 的 `currentPrice` | **元**（字符串，如 `"14.9"`） | 直接用 |
| `calculate-price` 的 `price` / `discount` 等 | **分**（整数，如 `8740`） | 展示前 ÷100 |

## 渲染模式

```bash
python scripts/render.py plans.json text      # 人读的摘要，带 ⚠ 标注
python scripts/render.py plans.json markdown  # 贴 README 的对比表
python scripts/render.py plans.json request   # 五套核价请求体
```
