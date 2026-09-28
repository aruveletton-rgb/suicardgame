# 测试、浏览器与资源报告

日期：2026-09-28。

## 环境

- 工作区：`E:\suicardgame`
- 分支：`codex/suicardgame-v1.2`
- 基线提交：`0559f48`
- Python：3.13.5
- Node.js：25.9.0
- 前端：TypeScript / Vite 8.0.16 / Chromium Playwright
- 测试数据：每次使用独立系统临时目录；未指向 `runtime/data/rooms` 或附件数据。

## 当前集成版本最终命令

```powershell
python -m pytest -q backend/tests
python scripts/validate-card-assets.py
npm --prefix frontend run build
git diff --check
```

结果：

- 后端：`261 passed, 1 warning in 17.56s`。
- Warning：FastAPI/Starlette TestClient 的 httpx 弃用提示；无功能失败。
- 素材：`68 manifest assets, 13 card crops and 12 avatars`。
- 构建：1761 modules；CSS 51.90 kB（gzip 10.52 kB），JS 270.59 kB（gzip 87.82 kB）。
- `git diff --check`：通过，仅有 Windows LF→CRLF 提示。

## 浏览器验收

已通过的 Chromium 流程：

- `agent_product`：2 tests，入口/头像/大厅/邀请/图鉴。
- `agent_table`：1 test，竖屏→横屏旋转、可见颜色/多选/商店支付与核心操作。
- batch1：2 tests，易/令的可见多选、真实响应与隐私。
- batch2：6 tests，黍的颜色/余牌目标/真实响应、无效输入、UNO/结果。
- response-window：1 test，竞争、到期、重连、隐私、reset 确认。
- multiplayer：1 test，真实 READY、实时状态、+4/有岁响应、DRAWN_CARD_DECISION、重连。
- visual layouts：1 test，5 人/25 手牌/8 商品的桌面、竖屏和横屏截图。
- expanded acceptance：4 tests，全部 4 项通过（45.6s）：13 张角色卡面浏览器加载与分段截图、手机真实操作/30 秒暂停恢复、胜负→REMATCH→重新准备、全部指定视口截图。

代表日志在 `artifacts/acceptance/playwright-*-20260928*.log`。

当前截图：

- `layout-desktop-1366x768.png`
- `layout-desktop-1920x1080.png`
- `layout-portrait-360x640-top.png`
- `layout-portrait-360x640.png`
- `layout-portrait-390x844-top.png`
- `layout-portrait-390x844.png`
- `layout-landscape-844x390-top.png`
- `layout-landscape-844x390.png`
- `mobile-portrait-multiselect-390x844.png`
- `mobile-landscape-shop-844x390.png`
- `mobile-landscape-pause-844x390.png`
- `mobile-portrait-pause-390x844.png`
- `card-gallery-crops-top-1920x1080.png`
- `card-gallery-crops-middle-1920x1080.png`
- `card-gallery-crops-bottom-1920x1080.png`

截图确认桌面 Host 座位不再覆盖商品；反馈条桌面定位修复后不再遮挡回合信息。手机顶部截图在 `scrollY=0` 断言后生成。13 张角色裁切图均在浏览器中完成加载断言，并通过图鉴顶部/中部/底部分段截图复核。

## 本地资源采样

证据：`artifacts/acceptance/resource-sample-windows-20260928.json`。

- 环境：Windows 开发机，16 逻辑处理器、约 32 GiB 内存。
- 后端：明确归属的 Uvicorn PID 36316，单进程。
- 负载：1 房间、5 玩家、5 条已认证 WebSocket；每连接每 0.2 秒 ping/pong。
- 时长：15 秒，0.5 秒间隔，30 个样本。
- CPU：按“单逻辑核百分比”口径，平均 1.2%，峰值 6.1%。
- RSS：平均 59.8 MiB，峰值 59.84 MiB。
- 采样后只精确关闭该后端 PID 和其包装进程；没有宽泛停止其他服务。

该采样仅证明本地单房间有界负载可运行，不能推导房间容量，也不能替代 Ubuntu 22.04、2 vCPU / 2 GiB 目标机验证。因此 G8 仍为未通过。

## 未执行/未通过

- 未部署或验证任何线上服务器。
- 未在目标 Ubuntu 机器采样 CPU/RSS/峰值。
- 未运行多房间容量压测。
- G4/G5/G6 当前开发机浏览器验收已通过；仍未通过的门槛仅为 G8 目标机资源证据，以及 G2 中等待用户裁决的三个规则顺序边界。
