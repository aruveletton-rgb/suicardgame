# suicardgame 第三轮修复与验收报告

日期：2026-09-29  
工作区：`E:/suicardgame`  
分支：`codex/suicardgame-v1.2`  
最终候选：`a7f7ac183374d140ee962b7bc5cbc2e00e8bf535` (`a7f7ac1`)  
第二轮最终提交：`9b562c0ae2b861d169a3add45f6a4e52ae1249ba`  
第二轮基线：`0c61d811d7cfe632466b3fe8965b1a503069384f`

## 结论摘要

本轮关闭了第二轮要求的本地可执行缺口：

1. 补跑遗漏的 batch1 2 项和 batch2 6 项，最终候选上全部通过。
2. 增加生产 dist + 独立后端的真实 CardView 验收，实际读取 React 生成的手牌、弃牌堆、商店 thumbnail，覆盖四色、wild/+4、数字/功能牌、选中和购买禁用状态。
3. 修复暂停面板泄露内部 `NIAN_TURN_END_DISCARD` 枚举的问题，显示“年牌弃牌步骤”；修复重连成功提示被 WebSocket 连接提示覆盖的时序竞态。
4. 将 shell/模拟脚本的旧 `/home/suicardgame`、`/home/miniconda3` 依赖改为仓库相对路径和可选 `CONDA_SH`/`PYTHON_BIN`，并让源码归档排除生成物、保留 shell 执行位。
5. 最终候选上的后端、素材、构建、原有 17 项浏览器和新增生产 CardView 1 项均通过。

没有部署、远端写入、生产房间操作或目标机资源测试。

## G1–G8

| 门槛 | 状态 | 本轮证据与边界 |
|---|---|---|
| G1 后端回归 | passed | `backend-full-20260929-round3-final2.log/xml`：266 passed，0 failed，0 errors，0 skipped，1 个既有 Starlette 弃用 warning，退出码 0。 |
| G2 关键规则 | passed | 有岁真实失败质疑、隐私对照、成功/无效交付、放弃/到期/重复/旧 prompt/重连及相邻结算仍在最终 266 项中通过；新增浏览器 batch1/batch2 也通过。沿用第二轮已确认的实现假设，不重新定义多人排序/嵌套规则。 |
| G3 时间/暂停 | passed | 后端 deadline/runtime 套件通过；最终浏览器手机暂停恢复通过，暂停文案不再显示内部枚举。 |
| G4 界面操作 | passed | 原有 17 项最终全通过，单 worker；覆盖 1366×768、1920×1080、360×640、390×844、844×390。batch1 2/2、batch2 6/6。 |
| G5 产品完整性 | passed | 入口、大厅、5 席、图鉴、胜负/Rematch、多人响应/重连均在 17 项最终运行中通过。 |
| G6 渲染 | passed | 新增生产 preview 规格 1/1 通过；从真实 DOM computed style 读取红/黄/绿/蓝和 wild/+4，实际覆盖 hand/table/thumbnail 及商店 UI；生产截图见 `production-card-render-*.png`。保留第二轮探针作为历史辅助，不将其当作本轮真实组件证据。 |
| G7 交付/协议 | partial | Windows Python 3.13.5、Node 25.9.0/npm 11.12.1、Playwright 1.61.1 下后端/素材/构建/浏览器/脚本检查通过；源码 ZIP 276 成员、无 forbidden 生成目录、无反斜线成员、shell ZIP 属性 755，并提供 mode-preserving tar。WSL Ubuntu 26.04 清洁副本的 shell/LF/path/help 通过，但缺 `python3-venv/pip`、Linux Node 和浏览器；默认 `run_tests.sh` 因 pytest 缺失退出 1，无法宣称 Linux 默认链通过。 |
| G8 目标机资源 | not_verified | 没有明确目标主机或本轮远端授权执行；未部署、未 SSH、未采样 CPU/RSS、未验证五人/第六人隔离契约。 |

## 第二轮缺口逐项关闭

### 浏览器遗漏

最终运行：`playwright-all-existing-20260929-round3-final3.log`，17/17 通过。遗漏项由 `playwright-batch1-batch2-20260929-round3.log` 和最终全量共同覆盖：

- `e2e/batch1-special-cards.spec.ts`：易牌、令牌，2/2。
- `e2e/batch2-shu.spec.ts`：黍牌平均分配、唯一最少余牌、并列最少选择、非法输入、UNO 临界、空手胜负，6/6。

### 真实生产 CardView

规格：`frontend/e2e/acceptance/production-card-render.spec.ts`。命令：`npm run test:e2e:production-card`；配置使用 backend + `vite preview`，`preview.proxy` 让 dist 页面通过真实 `/api` 和 WebSocket 连接隔离后端。TEST_MODE 只建立确定性初始手牌；商品、支付牌和确认购买均由 UI 完成。未插入假 DOM、未注入 CSS、未删除状态类。

截图：

- `artifacts/acceptance/production-card-render-1366x768.png`
- `artifacts/acceptance/production-card-render-mobile-390x844.png`
- `artifacts/acceptance/round3-*.png`（最终 17 项中的桌面、竖屏、横屏、商店、暂停截图）

### 文案与重连

`PausePanel` 对 `TURN_MAIN`、`NIAN_TURN_END_DISCARD`、`NIAN_CLAIM_WINDOW`、`HAS_SUI_CHALLENGE`、`WILD_DRAW_FOUR_CHALLENGE`、`SUI_PLAYER_RESPONSE` 提供面向玩家的中文标签，未知值回退为“当前必选步骤”，协议值不变。手机规格新增断言：显示“年牌弃牌步骤”，不包含 `NIAN_TURN_END_DISCARD`。

重连提示修复分两处保持 notice：socket `onopen` 和首个 `private_snapshot` 只有在 notice 为空时写入连接提示，避免覆盖“已恢复上次牌局”。修复前全量首跑的 1 次失败和根因保留在 `playwright-all-existing-20260929-round3-final.log`；修复后定向与最终全量均通过。

## Linux 与归档

Git Bash：11 个 `.sh` 均 LF、`#!/usr/bin/env bash`、`bash -n=0`、执行位 755；`bash scripts/run_tests.sh --help` 退出 0。  
WSL：Ubuntu 26.04 LTS / WSL2，清洁副本无旧绝对路径，shell 检查和 help 通过；最终源码 ZIP 解压路径检查通过，另附 `SUICARDGAME_SOURCE_a7f7ac1_modes.tar.gz` 保留执行位。WSL 账户无免密 sudo，无法安装 `python3-venv/pip`、Node 或浏览器；因此 requirements/npm ci/默认入口仍未在 Linux 通过，证据见 `linux-source-package-20260929-round3-final.log` 和 `linux-portability-20260929-round3-final2.log`。

源码 ZIP：`artifacts/SUICARDGAME_SOURCE_a7f7ac1.zip`  
SHA-256：`f4e90fa890627efae6415e5da86a92a9fa1480b22e78e7907fccafb688e36b50`  
执行位附加归档：`artifacts/SUICARDGAME_SOURCE_a7f7ac1_modes.tar.gz`  
SHA-256：`92e2cbc4a6f41a74e62fae9f8415d7a31ebc612ecd42f99a93466a2b295471ba`

## 规则与资源边界

2–5 人、READY、年牌杠＞碰＞吃、90/30/15/10 秒、必选暂停、可选到期放弃、有岁成功交一张摸四张、失败质疑者摸四张和罚摸不倒算均沿用现有实现和第二轮证据边界。本轮没有新增规则确认，也没有把沿用实施假设写成用户已确认规则。G8 不以历史远端采样替代。

工作区保留用户已有的第二轮 ZIP、`audit/`、`temp/` 和 `%SystemDrive%/` 未跟踪内容；它们未进入候选提交和源码 ZIP。当前分支 tracked tree clean，未跟踪文件仅为证据/历史用户内容及本轮交付物。
