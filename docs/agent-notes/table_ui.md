# Agent C `table_ui` 交接记录（2026-09-28）

## 范围与基线

- 基线提交：`0559f48 feat(release): prepare suicardgame v1.2`
- 遵循：`docs/agent-notes/contract.md` v1.1
- 只修改 C 的所有权文件：`frontend/src/App.tsx`、`frontend/src/styles/app.css`，以及新增 `frontend/src/components/table/`、`frontend/src/hooks/game/`、`frontend/e2e/agent_table/`。
- 未修改共享 `types.ts` / `api.ts`、D 的组件内部、后端或 E 拥有的旧 E2E。

## 已实现

1. 桌面围桌：玩家按真实 `seat_index` 排序，并以自己为底部参照布置最多四名对手；当前回合座位独立高亮。
2. 手机竖屏：座位横向滚动、紧凑牌桌、可展开商店、两列上下文操作和可滚动手牌。
3. 手机横屏：独立左侧座位轨道 + 中央短牌桌；商店、响应、颜色、目标、多选、支付和核心按钮均保留可达，不再使用旧版 `display:none` 省空间。
4. 统一选牌：手牌区提供明确的“主牌 / 多选牌 / 支付牌”模式；点击整张牌完成选择，不依赖隐藏复选框。旋转视口不重置状态。
5. 上下文操作：颜色和目标使用触控按钮；左乐目标列表保留自己；易/余/吃碰杠/响应所需的单选和多选均从同一模型取值。
6. 商店：桌面商品常驻；移动横竖屏均有展开入口。先选商品、再选支付牌、查看预览状态并确认交换；缺少商品或支付牌时不给出无效命令。
7. 响应条：显示来源、必选/可选、状态、提示和服务端倒计时。客户端显示 0 秒后不永久禁用响应按钮，而是等待服务端窗口转换/暂停。
8. 暂停：读取 `pause_state`；房主可发送 `CONTINUE_WAITING` 或确认后发送 `ABORT_GAME`，非房主看到等待说明。
9. 结算：接入 D 的 `GameResult`，显示胜者或“中止无胜者”、每名玩家剩余牌数、`REMATCH` 返回大厅并重新准备的入口；非房主按钮禁用并显示等待房主。
10. 轻量反馈：根据真实快照差异显示出牌、摸牌、回合转移提示；支持 `prefers-reduced-motion`。
11. 危险操作：进行中离开、房主重置、暂停中止均增加确认。
12. 产品组件集成：接入 D 的 `EntryPanel`、`RulesGallery`、`GameResult` 和增强 `LobbyDashboard`；头像随 create/join API 提交，邀请链接/二维码仅包含公开房间号，并在 `App.tsx` 导入 `product.css`。
13. 桌面商店/座位分区修复：1366×768 下牌桌高度改为有界自适应，中央区域显式分为回合、牌堆、商店三行；商店再分为标题/商品/确认三列，自己的座位保留独立底部车道，避免 5 人、25 张手牌场景中覆盖商品卡和标签。

## 可操作项清单

| 功能 | 桌面 | 竖屏 360×640 / 390×844 | 横屏 844×390 |
|---|---|---|---|
| 主牌选择与确认 | 可达 | 可达 | 可达 |
| 易/吃碰杠等多选 | 明确模式 | 明确模式 | 明确模式 |
| 余/通配颜色 | 触控按钮 | 触控按钮 | 触控按钮 |
| 望/左乐/黍目标 | 触控按钮 | 触控按钮 | 触控按钮 |
| 响应窗口 | 完整提示与按钮 | 完整提示与按钮 | 完整提示与按钮 |
| 商店支付/确认 | 商品常驻 | 展开后完成 | 展开后完成 |
| 暂停继续/中止 | 可达 | 可达 | 可达 |
| 手牌 25 张 | 横向滚动/重叠 | 横向滚动/重叠 | 横向滚动/重叠 |

## 验证

- 命令：`cd frontend && npm run build`
- 结果：通过；`tsc` 与 Vite 均成功，Vite 8.0.16 转换 1753 modules，构建约 0.91 秒（命令总耗时约 5.47 秒）。
- 产物摘要：CSS 35.87 kB（gzip 7.74 kB），JS 236.18 kB（gzip 75.44 kB）。
- 命令：`git diff --check -- frontend/src/App.tsx frontend/src/styles/app.css frontend/src/components/table frontend/src/hooks/game frontend/e2e/agent_table`
- 结果：通过；仅报告 Git 的 LF→CRLF 工作区提示，无空白错误。
- 命令：`cd frontend && npx tsc --noEmit`（D 产品组件集成后）
- 结果：通过，退出码 0。
- 新增 Playwright 规格：`frontend/e2e/agent_table/table-layout-accessibility.spec.ts`，覆盖竖屏到横屏旋转后的颜色、多选、商店商品/支付和操作可达性。
- QA 复验修复：创建房间后先等待 6 位房间号进入大厅，并轮询确认 localStorage 会话已有 `player_id`，消除 READY 请求使用空 host 会话的竞态。
- 命令：`SUICARDGAME_E2E_BACKEND_PORT=18122 SUICARDGAME_E2E_FRONTEND_PORT=15174 npx playwright test agent_table/table-layout-accessibility.spec.ts --project=chromium --reporter=line`（PowerShell 中使用等价 `$env:` 设置）。
- 结果：`1 passed (5.8s)`，命令退出码 0。首次使用默认端口执行因 8122 已占用而未进入测试；未终止现有进程，改用上述隔离端口后通过。
- 桌面重叠复验命令：`SUICARDGAME_E2E_BACKEND_PORT=18123 SUICARDGAME_E2E_FRONTEND_PORT=15175 npx playwright test acceptance/visual-layouts.spec.ts --project=chromium --reporter=line`（PowerShell 使用等价 `$env:` 设置）。
- 结果：`1 passed (5.9s)`，退出码 0；重新生成 `artifacts/acceptance/layout-desktop-1366x768.png`、竖屏和横屏截图。
- 1366×768 当前截图检查：5 名玩家、Host 25 张手牌、8 个商店商品均可见；Host 座位与商店商品/标签无交叠，商店确认文案未被遮挡，操作区与手牌仍在当前截图视口内。

## 未验证与后续集成

- Agent C 专属 Chromium 规格与 E 的 5 人视觉布局规格均已在隔离端口执行通过；其他规则响应、暂停恢复和完整多会话操作矩阵仍需 E 继续验收。
- D 的产品组件已按实际导出完成集成并通过 TypeScript 检查；最终 `npm run build` 由主线程统一执行，避免与其他重任务并行。
- 已完成 5 人/25 张手牌和商店的当前运行截图；尚未在该视觉规格中覆盖真实响应链、暂停恢复或目标机资源采样。
