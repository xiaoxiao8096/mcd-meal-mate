---
name: mcd-meal-mate
description: 给一群人按预算配出各自想吃的麦当劳餐，并算出优惠前后的人均花费。当用户说"我们四个人点麦当劳"、"帮我凑单"、"预算 180 以内怎么吃"、"谁能吃辣谁不吃辣"、"拼餐怎么配划算"时使用。基于麦当劳 MCP 的实时菜单与套餐选配数据，输出极致省钱/均衡/口味优先/多人分享四套方案，总价一律由 calculate-price 官方核价。
---

# 麦麦拼餐师

给一群人配麦当劳餐的规划器。核心不是"推荐好吃的"，而是**让每个人都吃到想吃的，同时把总价压到预算内，并且每一分钱都由麦当劳官方接口核算过**。

## 什么时候用

- "4 个人 180 块以内怎么点"
- "我们仨想点麦当劳，一个不吃辣"
- "帮我算下凑单最省的方式"
- "周末聚会 6 个人，预算 300"

## 什么时候不用

- 单人单份推荐 → 直接用 MCP 查菜单即可，不必上引擎
- 真的要点单下单 → 本 Skill **不调用** `create-order`（见下方"边界"）

## 铁律

1. **不猜价。** 所有单价只能来自 `query-meals` 的 `currentPrice`，最终总价必须由 `calculate-price` 返回。引擎算的是预估值，`calculate-price` 才是权威。
2. **不猜辣味。** 菜单没有成分表。只有拉过 `query-meal-detail`、确认过每一轮候选都不含辣味关键词的餐品，才可以说"这个不辣"。没拉过详情的套餐一律标注"辣味未确认"。
3. **查不到就说查不到。** 门店当天没有可用券、某餐品售罄、某轮次没有合法选项——都要如实说，不要编一个看起来合理的答案。
4. **不承诺过敏安全。** 忌口只做文本启发式匹配，明确告知用户这不构成过敏建议。
5. **不下单。** 见"边界"。

## 工作流

### 第 1 步：把需求问清楚，缺一项就问

必需信息（缺哪项问哪项，不要瞎猜）：

| 要素 | 说明 | 缺失时 |
|---|---|---|
| 人数 | 精确人数 | 必须问 |
| 总预算 | 人民币金额 | 必须问 |
| 门店 | 城市 + 位置关键词，或直接选附近门店 | 必须问 |
| 就餐方式 | 堂食 / 外带（`beType=1`）/ 得来速（`beType=5`）/ 外送 | 默认问，别擅自决定 |
| 每人口味与忌口 | 谁不吃辣、谁想吃鸡、谁吃素 | 至少问忌口 |

### 第 2 步：定位门店

```
query-nearby-stores
  beType     : 1（到店自取）或 5（得来速）
  searchType : 2
  city       : 城市名
  keyword    : 位置关键词（如"湖南工商大学南校区"）
```

把 `storeCode`（`beType=5` 时还要 `beCode`）完整展示给用户，让用户确认门店。
注意：`beType=1` 时返回的门店不含 `beCode`，后续调用**不要传** `beCode`，传了会报错。

### 第 3 步：核对优惠券（用户想用券时才做）

```
query-store-coupons  storeCode + orderType + beType
```

- 返回空数组 → **如实说"该门店今天没有可用优惠券"**，不要拿别的券凑。
- `query-my-coupons` 拿到的卡包券**只作展示**，官方明确说明它不做门店/渠道/下单规则校验，不能承诺可用于当前订单。要判断"这张券能不能用"，只能用 `query-store-coupons`。
- 券是按日期生效的。今天没券不代表明天没有，如实说明有效期即可。

### 第 4 步：拉菜单，必要时拉套餐详情

```
query-meals   storeCode + orderType + beType
```

返回里每项都有 `currentPrice`（现价）和 `originalPrice`（原价），**单位是元**，这是全流程的价格来源。

再对**含轮次选择**的餐品拉详情（随心配、三件套、双人分享餐等）：

```
query-meal-detail   storeCode + orderType + beType + code
```

返回 `rounds[]`，每轮有 `minQuantity`（必选数量）、`choices[]`（候选）、`diffPrice`（相对默认选项的差价，如 `- ¥1`）。
**这些官方候选是解决忌口问题的关键**——不吃辣的人应该在候选里挑，而不是靠猜。

参考：`references/which-details-to-fetch.md` 说明了哪些餐品值得拉详情。

### 第 5 步：交给规划引擎

把菜单、详情、群体信息写成 JSON（格式见 `references/input-schema.md`），然后：

```bash
python scripts/plan.py input.json > plans.json
python scripts/render.py plans.json text        # 终端摘要
python scripts/render.py plans.json markdown    # 对比表
python scripts/render.py plans.json request     # 核价请求体
```

引擎会输出**四套**方案：`cheapest`（极致省钱）、`balanced`（均衡）、`tasty`（口味优先）、`share`（多人分享）。

### 第 6 步：用 calculate-price 逐套核价（不可跳过）

把 `render.py ... request` 输出的每个策略请求体，原样丢给 `calculate-price`：

```
calculate-price   storeCode + orderType + beType + items[]
```

- 返回金额**单位是分**，展示前必须 ÷100。
- `productList[]` 是逐项小计，用来核对引擎的分摊有没有算错。
- `discount` 是优惠金额；`enjoyable.balance` 是"门槛差额"，即还差多少钱能用券——这是凑单提示最实用的数据。
- **官方价与引擎预估不一致时，以官方价为准**，并如实告诉用户差在哪。

### 第 7 步：输出

每套方案必须包含：

1. 每个人点什么（写明轮次选配，如"随心配：高达吉士双牛堡 + 可乐麦炫酷"）
2. 哪些是共享的、各几份
3. 优惠前后总价与人均（**用 `calculate-price` 的官方值**）
4. 没能满足的部分（如"P4 想吃鸡，但今天没有合规的鸡肉套餐可选"）
5. 辣味未确认的餐品要显式标注

最后给一句可执行的下一步（换方案 / 改预算 / 去核价），不要替用户下单。

## 边界（重要）

- **本 Skill 只到"核价"为止，不调用 `create-order`。** 真要下单时，必须先把门店、餐品、选配、优惠、最终金额完整展示，等用户明确确认后再由用户或上层流程调用 `create-order`。
- 不承诺"绝对无过敏原""绝对安全"。
- 不代表麦当劳官方，不承诺价格与供应状态——一切以官方渠道实时结果为准。
- 遵守 MCP 限流：每个 Token 每分钟最多 600 次请求。一次拼餐规划通常 3~8 次调用，够用；不要为了穷举组合而打满配额。

## 文件

```
scripts/plan.py                    规划引擎（纯离线，无网络）
scripts/render.py                  方案渲染（文本 / Markdown / 核价请求体）
data/sample-case-4p-180.json       真实抓取样本，用于离线自测
references/input-schema.md         引擎输入格式
references/output-schema.md        引擎输出格式
references/mcp-tools.md            MCP 调用规范与踩坑记录
references/which-details-to-fetch.md  该拉哪些套餐详情
references/verified-run-2026-10-10.md  一次真实跑通的完整记录
```

自测：

```bash
python scripts/plan.py data/sample-case-4p-180.json > /tmp/plans.json
python scripts/render.py /tmp/plans.json text
```

引擎是纯计算，不联网、不需要 Token，可直接离线运行。
