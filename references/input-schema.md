# 引擎输入格式

`scripts/plan.py` 只吃一个 JSON 文件，结构如下。所有字段都来自 MCP 返回，本项目不生成、不修改菜单数据。

```jsonc
{
  "store": {
    "storeCode": "3390023",          // 必填，来自 query-nearby-stores
    "storeName": "麦当劳衡阳船山餐厅",
    "beType": 1,                      // 必填 1=到店自取 2=麦乐送 5=得来速 6=团餐
    "orderType": 1                    // 必填 1=到店 2=外送
  },

  // 必填：query-meals 返回的 data 原样放进来了
  "menu": {
    "categories": [
      { "name": "随心配1+1",
        "meals": [ { "code": "9900013304", "tags": ["超值百种组合随心配"] } ] }
    ],
    "meals": {
      "9900013304": {
        "name": "人气经典随心配",
        "currentPrice": "14.9",       // 必填，现价，单位元
        "originalPrice": "14.9"       // 选填，划线价
      }
    }
  },

  // 选填：query-meal-detail 的 data，key 是餐品编码
  // 只放"含轮次选择"的餐品；引擎会对这些餐品解算选配
  "details": {
    "9900013304": {
      "code": "9900013304",
      "name": "人气经典随心配",
      "rounds": [
        {
          "id": 1,
          "name": "蓝区",
          "minQuantity": 1,           // >=1 表示必选，引擎必须给它选一个
          "maxQuantity": 1,
          "choices": [
            { "code": "1450", "name": "麦香鸡", "diffPrice": "- ¥1", "isDefault": 0 }
          ]
        }
      ]
    }
  },

  // 必填
  "group": {
    "headcount": 4,
    "budget": 180,                    // 人民币元
    "takeaway": "堂食",                // 仅用于记录
    "people": [
      { "id": "P1", "avoid": ["spicy"] },
      { "id": "P2", "avoid": ["spicy"] },
      { "id": "P3", "prefer": ["chicken"] },
      { "id": "P4" }
    ]
  },

  // 选填：只要其中几个策略，默认四个全出
  "strategies": ["cheapest", "balanced", "tasty", "share"]
}
```

## 约束词表

| 字段 | 支持取值 | 含义 |
|---|---|---|
| `avoid` | `"spicy"` | 避开辣味 |
| `prefer` | `"chicken"` / `"fish"` / `"beef"` | 优先命中对应食材 |

命中不了偏好不会导致方案失败，只会被降权；命中不了的**忌口**会导致该餐品被排除（对含轮次的餐品，若某必选轮次所有候选都违反忌口，则整份餐品弃用）。

## 关于 `people` 省略

若省略 `people`，引擎会按 `headcount` 生成 `P1..Pn` 无约束的人。此时所有策略都能跑，但不会有忌口过滤。
