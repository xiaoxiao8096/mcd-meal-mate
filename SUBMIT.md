# 提交清单

打勾式。做完每一项就能提交，全部完成即报名成功。

## 一、本地已完成 ✅

- [x] `SKILL.md` — Skill 入口（工作流 + 五条铁律）
- [x] `README.md` — 项目介绍 / 安装 / 使用示例 / 目标用户
- [x] `MCP_INTEGRATION.md` — MCP Server、Tool、调用流程、业务价值
- [x] `CONTEST_DECLARATION.md` — 官方原文，**一字未改**
- [x] `mcp-config.example.json` — 仅 `${MCD_MCP_TOKEN}` 占位符
- [x] `workbuddy.md` — WorkBuddy 联动记录，**Token 已脱敏**
- [x] `scripts/plan.py` — 规划引擎（离线，仅标准库）
- [x] `scripts/render.py` — 方案渲染
- [x] `tests/test_plan.py` — 42 项自测，全通过
- [x] `data/sample-case-4p-180.json` — 真实抓取样本
- [x] `references/` — 5 份参考文档
- [x] `LICENSE` / `.gitignore`
- [x] 安全扫描：真实 Token / 硬编码 Bearer / 会员账号 ID，**均 0 命中**

## 二、推仓库前请手动确认

- [ ] `.gitignore` 里 `out/`、`mcp.json`、`.env` 都在排除列表
- [ ] 再跑一次安全扫描（防止临时文件混入）

  ```bash
  grep -rn -E "Bearer [A-Za-z0-9]{20,}" . | grep -v REDACTED | grep -v MCP_TOKEN
  ```

## 三、建仓与推送（需你的 GitHub 账号）

- [ ] 新建仓库，名字建议 `mcd-meal-mate`
- [ ] **Visibility 必须选 Public**（私有不算数）
- [ ] 不要勾选 "Add a README file"（本地已有，避免冲突）
- [ ] 推送：

  ```bash
  cd mcd-meal-mate
  git init
  git add .
  git commit -m "feat: 麦麦拼餐师 - 基于麦当劳 MCP 的群体拼餐规划 Skill"
  git branch -M main
  git remote add origin https://github.com/你的用户名/mcd-meal-mate.git
  git push -u origin main
  ```

- [ ] ⚠️ **仓库创建时间必须在 2025-12-25 00:00 ~ 2026-10-25 23:59 之间**（现在建没问题）

## 四、发 Issue 报名

- [ ] 打开 https://github.com/M-China/mcd-developer-innovation-challenge/issues → New issue → Blank issue
- [ ] 标题自定义，正文照抄 [`SUBMIT_ISSUE.md`](./SUBMIT_ISSUE.md) 里的方案 A 或 B
- [ ] ⚠️ 正文 **≤1000 字**、**绝对不能带图片**
- [ ] 等机器人回复确认报名成功
- [ ] 若失败，按 `SUBMIT_ISSUE.md` 里的对照表改完重发

## 五、拉 Star（决定排名）

- [ ] 去官方仓库 Issues 里发帖求 Star
- [ ] 分享给朋友 / 技术群
- [ ] ⚠️ **同一账号多个项目只取 Star 最高的那个进榜**，集中做一个
- [ ] 去 `RANKING.md` 查实时排名

## 六、时间节点

| 事项 | 时间（北京时间） |
|---|---|
| 报名截止 | **2026-10-25 23:59** |
| 排名锁定（按此刻累计 Star） | **2026-10-26 00:00** |
| 领奖信息提交截止 | 2026-11-14 |
| 实物奖品寄出 | 提交收货信息后约 2 周 |

⚠️ 领奖要用**麦当劳会员手机号**，且 GitHub 仓库 Owner 的邮箱要能收到通知——
建议提前在 GitHub 公开邮箱，否则麦当劳会发起 OAuth 授权申请。

## 七、比赛结束后

- [ ] 去 https://open.mcd.cn/mcp 控制台**重新生成 MCP Token**，作废当前这个
      （当前 Token 曾以明文形式出现在对话中，赛后立即轮换最稳妥）
- [ ] 兑换 WorkBuddy 积分（同一账号仅限 1 份）
