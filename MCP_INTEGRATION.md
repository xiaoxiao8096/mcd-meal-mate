# MCP 集成说明

本项目实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

- **Server**：`https://mcp.mcd.cn`（麦当劳中国远程托管，Streamable HTTP）
- **文档**：[M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server)
- **本项目用到的 Tool 数量**：5 个主用 + 2 个按需

## 一、调用流程

```
用户需求（人数 / 预算 / 门店 / 就餐方式 / 每人口味忌口）
        │
        ├─ 1. query-nearby-stores ──► 定位门店，拿 storeCode
        │      searchType=2, city, keyword, beType
        │      展示候选门店让用户确认；beType=1 时不传 beCode
        │
        ├─ 2. query-store-coupons ──► 当日可用券（仅当用户想用券）
        │      storeCode + orderType + beType
        │      空数组 = 如实告知"今天没有可用券"，不拿卡包券凑
        │
        ├─ 3. query-meals ──────────► 该店当前可售菜单（价格来源）
        │      storeCode + orderType + beType
        │      返回 currentPrice / originalPrice（单位：元）
        │
        ├─ 4. query-meal-detail ────► 含轮次餐品的选配结构（按需，3~5 次）
        │      + code
        │      返回 rounds[].choices[] 与 diffPrice
        │      ★ 不吃辣/想吃鸡的合法性判定依据
        │
        ├─ 5. scripts/plan.py ──────► 本地组合优化（纯离线，不联网）
        │      输入 menu + details + group
        │      输出四套方案 + calculatePriceRequest
        │
        └─ 6. calculate-price ──────► 逐套官方核价 ★价格权威来源
               storeCode + orderType + beType + items[](含 roundList)
               返回单位：分
```

可选 Tool：`list-nutrition-foods`（用户问热量/营养时）、`query-my-account`（积分余额）。

## 二、各 Tool 的实际用途

### `query-nearby-stores` — 定位门店

按城市 + 关键词搜门店。实测"衡阳 / 湖南工商大学南校区"返回 5 家，最近为 `3390023`（864 m）。

**注意**：`beType=1`（到店自取）时返回的门店**不含 `beCode`**，下游调用不能传该字段；`beType=5`（得来速）才有 `beCode`，且必传。

### `query-store-coupons` — 当日可用券

**这是"凑单"功能的数据源。** 实测 2026-10-10 该门店返回 `data: []`，即当天无券——如实告知用户，而不是编一个优惠。

券按日期生效（实测卡包 13 张券全部绑定具体日期，其中 9 张仅限 05:00-10:29 早餐时段），所以"今天有没有券"必须现场查。

### `query-meals` — 菜单与价格

**全流程唯一的价格来源。** 每项返回 `currentPrice`（现价）与 `originalPrice`（划线价），单位是**元**。

这一点决定了架构：可以先在本地按预算筛选，再用 `calculate-price` 核价，而不是靠核价接口反推价格——省配额且快得多。

菜单还会提供 `withOrder`（随单购麦金卡/早餐卡优惠）与 `discountType`，本项目暂未使用，属于后续可扩展点。

### `query-meal-detail` — 套餐选配（最关键）

返回 `rounds[]`，每轮含 `minQuantity`（必选数量）、`maxQuantity`、`choices[]`（候选）、`diffPrice`（相对默认项的差价）、`isDefault`。

**这个 Tool 是本项目解决"忌口"问题的核心。** 麦当劳没有过敏原字段，菜单 `tags` 里也没有"辣/不辣"。但套餐详情的 `choices` 是官方给出的**结构化候选清单**，用户可以直接从中挑：

实测 `人气经典随心配` 蓝区 8 个候选里：
- 不辣的有：高达吉士双牛堡、麦香鱼、那么大鸡排（椒盐风味）
- 鸡肉的有：麦乐鸡5块、麦香鸡
- 其中 4 个的 `diffPrice` 是 **`- ¥1`**，比默认项更便宜

于是"不吃辣的人"和"想吃鸡的人"都能各自合法地挑到合适的一份，**不需要靠关键词去猜套餐里到底有什么**。

### `calculate-price` — 官方核价（价格权威）

入参 `storeCode` + `orderType` + `beType` + `items[]`；含轮次选择的餐品必须带 `roundList`：

```jsonc
{
  "productCode": "9900013304",
  "quantity": 1,
  "roundList": [
    { "round": "1", "comboItemList": [{ "code": "521316", "quantity": 1 }] },
    { "round": "2", "comboItemList": [{ "code": "521328", "quantity": 1 }] }
  ]
}
```

**返回单位是分**（`price: 8740` 表示 87.40 元），这个坑踩过一次就够了。

返回字段里有两个对业务特别有用：

| 字段 | 含义 | 业务价值 |
|---|---|---|
| `productList[].subtotal` | 逐项小计 | 核对引擎分摊有没有算错 |
| `enjoyable.balance` | 门槛差额（单位分） | **"还差多少钱能用券"**，凑单提示直接用它 |
| `discount` | 优惠金额 | 优惠前后对比 |
| `takeWayList` | 堂食/外带 | MCP 原生支持就餐方式，无需自己建模 |

## 三、引擎与 MCP 的分工

| 环节 | 谁做 | 原因 |
|---|---|---|
| 取菜单、取券、取详情 | WorkBuddy Agent 调 MCP | 需要联网与用户 Token |
| 组合优化、四策略排序、预算裁剪 | `scripts/plan.py` 离线计算 | 纯函数，可单测，不烧配额 |
| 最终定价 | `calculate-price` | 官方口径，不可替代 |

这样切分带来三个好处：

1. **可离线自测** —— 引擎不联网、不需要 Token，`data/sample-case-4p-180.json` 是真实抓取样本，直接跑就能回归。
2. **省配额** —— 限额 600 次/分钟，一次规划 3~8 次调用。组合枚举放在本地做，不用拿接口当计算器。
3. **价格不会被算错** —— 引擎输出的是"预估"，必须经 `calculate-price` 复核，且**不一致时以官方为准**。

## 四、实测一致性验证

2026-10-10 用真实门店数据跑四套方案，引擎预估值与 `calculate-price` 返回值**四套全部一致**：

| 策略 | 引擎预估 | `calculate-price` 返回 | 一致 |
|---|---:|---:|:--:|
| 性价比首选 | ¥138.40 | 13840 分 | ✅ |
| 极致省钱 | ¥71.50 | 7150 分 | ✅ |
| 当季尝鲜 | ¥175.80 | 17580 分 | ✅ |
| 多人拼单 | ¥120.70 | 12070 分 | ✅ |

完整记录见 [`references/verified-run-2026-10-10.md`](./references/verified-run-2026-10-10.md)。

## 五、发现的业务机会（未实现，供后续）

1. **套餐比单点便宜 15.5 元**：`巨无霸三件套`（选 `小杯玉米杯`，-¥1）¥36.5 vs `巨无霸单品 + 脆脆薯条 + 可乐` ¥52.0。引擎已优先套餐，但还能做得更细（逐套餐比价）。
2. **`enjoyable.balance` 驱动的凑单建议**：告诉用户"再加 3.5 元就能省 5 元"，比泛泛推荐有用得多。当前只做了展示，未做主动凑单。
3. **券的日期感知**：`query-my-coupons` 的券带有效期，可提前提醒"你卡里有张券 10/12 才生效"。
4. **营养维度**：`list-nutrition-foods` 已验证可用，可加"要控热量"这一维度。当前刻意未纳入 V1，避免把选择维度做得过载。

## 六、合规声明

- 本项目**不调用** `create-order`，**不下单**。
- 金额单位在代码与文档中均已明确标注（元 / 分），避免 100 倍误差。
- 所有价格、库存、供应状态以麦当劳官方渠道实时结果为准，本项目不做任何承诺。
- 本项目为参赛作品，非麦当劳官方产品。
