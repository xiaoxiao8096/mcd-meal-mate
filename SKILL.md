---
name: mcd-meal-mate
description: 给一群人按预算配出各自想吃的麦当劳餐，先选门店再配餐，算出优惠与人均花费，也能按热量目标做减脂搭配。当用户说"我们四个人点麦当劳"、"帮我凑单"、"预算 180 以内怎么吃"、"谁能吃辣谁不吃辣"、"拼餐怎么配划算"时使用。基于麦当劳 MCP 的实时菜单与套餐选配数据，输出性价比首选/极致省钱/当季尝鲜/多人拼单/轻食低卡五套方案，价格由 calculate-price 官方核价，热量由 list-nutrition-foods 核算。
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
5. **城市不许猜。** `query-nearby-stores` 的 `city` 必须来自用户，不能从地名推测。
   （真实踩过：把「湖南工商大学南校区」当成衡阳，实际在长沙，接口照样返回了衡阳门店——
   因为 city 过滤确实生效，错的是填进去的值。）拿到结果后用 `stores.py --city` 反查一遍。
5. **不下单。** 见"边界"。

## 工作流

### 第 1 步：先问人在哪

**流程从选门店开始**，没有门店就没有菜单、没有价格、没有券。

⚠️ **城市必须问，不能猜。** 地名不带城市时尤其容易错——「湖南工商大学南校区」在**长沙**，
不在衡阳。猜错城市会拿到另一个城的门店和菜单，后面全白算。

问清楚这几项，缺哪问哪：

| 要素 | 缺失时 |
|---|---|
| **城市** + 位置关键词（或直接给门店名） | **必须问，绝不推测** |
| 人数、就餐方式（`beType`） | 必须问 |
| 堂食 / 外带 / 得来速 / 外送 | 默认问，别擅自决定 |
| 总预算 | 必须问 |
| 每人口味与忌口 | 至少问忌口 |
| 热量目标（可选，减脂时才问） | 没提就不问 |

### 第 2 步：查附近门店并优选

```
now-time-info         先拿当前时间，后面判营业状态要用
query-nearby-stores   beType + searchType=2 + city + keyword
```

拿到一批店之后交给 `scripts/stores.py`，它会：

- **滤掉此刻已打烊的**（用 `businessStartTime`/`businessEndTime` 比对，跨零点也正确）
- 按距离排序，标出**是否支持预约**、今天还剩哪些时段
- 给一句话推荐

```bash
python scripts/stores.py stores.json --now 13:30 --today 2026-10-10 --city 长沙
```

`--city` 会做一次反向校验：**如果返回的门店名里都不含你填的城市，说明城市填错了**，
先回去问用户，别继续往下算。

**把推荐结果给用户确认后再往下走。** 门店是整单的基准，选错了后面全白算。

`beType=1` 时返回的门店不含 `beCode`，后续调用**不要传** `beCode`，传了会报错。

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

> ⚠️ **详情要拉两轮**：第一轮拉几个候选用来出方案；出方案后**再给方案里
> 实际用到、但还没拉过详情的套餐补拉一次**。因为 `list-nutrition-foods`
> 的营养表里**只有单品、没有套餐**，不补拉详情就没法算套餐热量。

### 第 5 步：识别当季活动（推荐，成本极低）

```
campaign-calendar   可选 specifiedDate=yyyy-MM-dd
```

麦当劳的活动话术会渗进菜单名（活动叫「就「酱」心有所「薯」」，菜单里就多一个「鸡薯双全盒」）。
拉一次活动日历，把结果交给 `scripts/campaign.py`，它会：

- 剥掉「“我就喜欢”」这类引号前缀与「三件套」这类通用后缀，拿核心词匹配活动文案
- 输出 `campaignCodes`，回注给引擎的输入 JSON
- 顺带提取营销话术与谐音梗落点

`campaignCodes` 只在"同样是套餐"时参与排序，排在套餐丰富度之后；`cheapest` 完全不受影响。

### 第 6 步：交给规划引擎

把菜单、详情、群体信息写成 JSON（格式见 `references/input-schema.md`），然后：

```bash
python scripts/plan.py input.json > plans.json
python scripts/render.py plans.json text        # 终端摘要
python scripts/render.py plans.json markdown    # 对比表
python scripts/render.py plans.json request     # 核价请求体
```

引擎会输出**五套**方案：`light`（轻食低卡）、`value`（性价比首选）、`cheapest`（极致省钱）、`tasty`（当季尝鲜）、`share`（多人拼单）。

### 第 7 步：用 calculate-price 逐套核价（不可跳过）

把 `render.py ... request` 输出的每个策略请求体，原样丢给 `calculate-price`：

```
calculate-price   storeCode + orderType + beType + items[]
```

- 返回金额**单位是分**，展示前必须 ÷100。
- `productList[]` 是逐项小计，用来核对引擎的分摊有没有算错。
- `discount` 是优惠金额；`enjoyable.balance` 是"门槛差额"，即还差多少钱能用券——这是凑单提示最实用的数据。
- **官方价与引擎预估不一致时，以官方价为准**，并如实告诉用户差在哪。

### 第 8 步：算热量（用户提了减脂/热量就必须做）

```
list-nutrition-foods
```

**这是一个循环，必须跑到闸门通过为止**，不是"顺手算一下"：

```bash
python scripts/nutrition.py nutrition.json menu.json plans.json --target 1800 --strict
```

返回里有两段信息，含义完全不同：

| 字段 | 含义 | 怎么办 |
|---|---|---|
| `coverage.needDetails` | 方案里的套餐**还没拉过详情** | **必须去补拉** `query-meal-detail`，把结果并入 `menu.json` 的 `details` 再重跑 |
| `coverage.unknownItems` | 拉了详情，但组件在营养表里查不到 | **无法修复**，如实标"热量未知"（见下方边界） |

`--strict` 在未补全时以**退出码 3** 结束。**没拿到退出码 0 就不要往下走**，
也别把 `totalKcal` 当成全单真实值报给用户——这个坑已经踩过两次。

会给出：

- 每道菜的热量与**套餐各组件的累加过程**
- 方案总热量 / 人均热量
- 与用户给定热量目标的对比和提醒
- **低卡替换建议**（例如 可乐中杯 147 kcal → 无糖可口可乐 0 kcal，这个换有据可依）
- **去酱建议**：从 `modification` 里挑出可以去掉的酱料名

四条诚实边界，务必守住：

1. 营养表**没有套餐**，套餐热量只能按轮次组件累加；**任何组件查不到就整体标未知**，
   绝不用"同类套餐大概多少"估算。
2. **营养表有滞后**。实测 2026-10-10 的 160 条里**查不到**当季新联名的
   `龙焰鸡腿堡`、`高达吉士双牛堡`，也查不到 `可乐麦炫酷`、`“我就喜欢”鸡薯双全盒`、
   `灰焰圆筒`。新品上线后热量进表有延迟，这部分**只能标未知，不要估**。
3. **"去掉酱料能省多少大卡"接口没给**，只能推荐"可以去掉巨无霸酱"，
   不能承诺"省 200 大卡"。
4. 热量是**参考值**，不构成营养或医疗建议。

若用户给了 `calorieTarget`，把它写进输入 JSON 的 `group.calorieTarget`，
引擎会在 `light` 策略下按热量升序排，并超标时自动提醒。

### 第 9 步：分账（可选但强烈建议）

```
python scripts/split_bill.py plans.json <策略名> [--discount 13.5]
```

整数分运算的零尾差分摊：个人餐归本人、共享餐全桌均分、分享餐在成员间分、
整单优惠按人数均摊。每一步都断言合计与实付分毫不差。

把 `--discount` 填上 `query-store-coupons` 查到的优惠金额。

### 第 10 步：输出

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
scripts/stores.py                  门店优选：滤打烊、按距离、标预约
scripts/plan.py                    规划引擎（纯离线，无网络）
scripts/campaign.py                活动感知：识别当季活动限定品 + 提取营销话术
scripts/nutrition.py               营养热量：套餐组件累加、低卡替换、去酱建议
scripts/split_bill.py              零尾差 AA 分账（整数分运算）
scripts/render.py                  方案渲染（文本 / Markdown / 核价请求体）
data/sample-case-4p-180.json       真实抓取样本（菜单 + 套餐详情）
data/sample-campaigns.json         真实抓取样本（活动日历）
data/sample-nutrition.json         真实抓取样本（营养表）
data/sample-stores.json            真实抓取样本（门店列表）
tests/                             162 项自测（规划 / 活动 / 分账 / 营养 / 门店）
references/input-schema.md         引擎输入格式
references/output-schema.md        引擎输出格式
references/mcp-tools.md            MCP 调用规范与踩坑记录
references/which-details-to-fetch.md  该拉哪些套餐详情
references/verified-run-2026-10-10.md  一次真实跑通的完整记录
```

自测：

```bash
python tests/test_plan.py && python tests/test_campaign.py && python tests/test_split_bill.py && python tests/test_nutrition.py
```

引擎是纯计算，不联网、不需要 Token，可直接离线运行。
