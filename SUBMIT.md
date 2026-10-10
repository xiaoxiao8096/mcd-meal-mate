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

## 三、建仓与推送

### 3.1 你先建仓（约 30 秒）

**点这个预填链接**（owner / 仓库名 / 描述 / Public 都已填好）：

<https://github.com/new?owner=xiaoxiao8096&name=mcd-meal-mate&description=%E9%BA%A6%E9%BA%A6%E6%8B%BC%E9%A4%90%E5%B8%88%20%E2%80%94%20%E5%9F%BA%E4%BA%8E%E9%BA%A6%E5%BD%93%E5%8A%B3%20MCP%20%E7%9A%84%E7%BE%A4%E4%BD%93%E6%8B%BC%E9%A4%90%E8%A7%84%E5%88%92%20Skill%E3%80%82%E5%9B%9B%E5%A5%97%E6%96%B9%E6%A1%88%E9%87%91%E9%A2%9D%E5%9D%87%E7%94%B1%20calculate-price%20%E5%AE%98%E6%96%B9%E6%A0%B8%E9%AA%8C%E3%80%82%E9%BA%A6%E5%BD%93%E5%8A%B3%E7%A8%8B%E5%BA%8F%E5%91%98%E5%88%9B%E6%84%8F%E5%BC%80%E5%8F%91%E5%A4%A7%E8%B5%9B%E5%8F%82%E8%B5%9B%E4%BD%9C%E5%93%81%E3%80%82&visibility=public>

或手动打开 <https://github.com/new>，按此填：

| 字段 | 填什么 |
|---|---|
| Owner | `xiaoxiao8096` |
| Repository name | `mcd-meal-mate` |
| Description | 麦麦拼餐师 — 基于麦当劳 MCP 的群体拼餐规划 Skill |
| **Visibility** | **Public** ← 私有不算数，请务必确认 |
| README / .gitignore / license | **全部不要勾**（本地已有，避免冲突） |

点 **Create repository**。

> ⚠️ **仓库创建时间必须落在 2025-12-25 00:00 ~ 2026-10-25 23:59 之间**，现在建完全没问题。

<details>
<summary>为什么这一步必须你手动？（已实测确认）</summary>

| 尝试路径 | 结果 |
|---|---|
| GitHub 连接器 `create_repository` | `403 Resource not accessible by integration` —— App 令牌在权限模型上无法创建用户仓库 |
| SSH 推送 | 无 `~/.ssh` 目录，`git@github.com` 返回 `Permission denied (publickey)` |
| `gh` CLI | 未安装；git 也未配置 `credential.helper` |

</details>

### 3.2 推送（本地提交已就绪，remote 已配好）

> ⚠️ **必须走代理**。2026-10-10 14:35 实测：直连 `github.com:443` **21 秒超时失败**，
> 走本地代理 `127.0.0.1:7897` 正常（curl 返回 HTTP 200）。
> 直连命令会卡住然后失败。

**方式一：PAT**

PAT 在 <https://github.com/settings/tokens> 生成，勾 `repo` 权限。

```bash
cd C:/Users/14549/Desktop/麦麦/mcd-meal-mate
git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 \
    push -u https://你的PAT@github.com/xiaoxiao8096/mcd-meal-mate.git main
```

推完把 remote 里的 PAT 清掉：

```bash
git remote set-url origin https://github.com/xiaoxiao8096/mcd-meal-mate.git
```

> 如果代理端口变了，先测一下哪个通：
> `HTTPS_PROXY=http://127.0.0.1:7897 curl -s -o /dev/null -w "%{http_code}" https://github.com`
> 返回 200 就是通的。

**方式二：GitHub Desktop**

打开 GitHub Desktop → Add existing repository → 选 `C:\Users\14549\Desktop\麦麦\mcd-meal-mate` → Publish 上传（确认勾 Public）。GitHub Desktop 走系统代理，一般不用额外配置。

### 3.3 推完验证

仓库地址应为：**https://github.com/xiaoxiao8096/mcd-meal-mate**

打开页面确认这 4 样都在：
- [ ] `CONTEST_DECLARATION.md`
- [ ] `MCP_INTEGRATION.md`
- [ ] `mcp-config.example.json`
- [ ] `README.md`
- [ ] **仓库是 Public**

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
