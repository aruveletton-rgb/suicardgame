# suicardgame 第二轮修复与验收报告

日期：2026-09-29
工作区：`E:/suicardgame`
分支：`codex/suicardgame-v1.2`
基线提交：`0c61d81 fix(acceptance): finalize v1.2 rules and evidence`
本轮测试对象：基线提交加当前工作区源码补丁；最终提交将在本报告封存后创建。

## 结论摘要

本轮完成了独立审计指出的三个修复：

1. 恢复正常完整回合中“无岁”错误质疑的服务端失败路径：质疑窗口不再因私有岁牌集合为空而消失；错误质疑者真实摸四张，来源玩家不交牌、不被罚摸。
2. 移除后加载的旧 UNO 灰色背景覆盖，使红、黄、绿、蓝和 wild 的生产构建计算样式恢复为产品卡面颜色与底纹/渐变。
3. 为 shell 入口增加 LF 持久约束并验证全部脚本的 Bash 语法及 `run_tests.sh --help`。

当前本地验收结论：G1、G2、G3、G4、G5、G6、G7 通过；G8 未验证。本轮没有部署、重启或修改远端服务。

## G1–G8

| 门槛 | 状态 | 当前证据 |
|---|---|---|
| G1 后端回归 | 通过 | `artifacts/acceptance/backend-full-20260929-round2-final.xml`：266 tests，0 failures，0 errors，0 skipped；日志显示 266 passed、1 warning。基线 264 项，本轮新增/迁移 2 项行为回归，数量变化有解释。 |
| G2 关键规则 | 通过 | `backend/tests/acceptance/test_audit_semantics.py` 与 `backend/tests/agent_rules/test_rule_windows.py` 覆盖八项审计语义、有岁失败/成功、公开窗口隐私、交付/到期/幂等及相邻结算。错误质疑测试走真实 PLAY_CARD→HAS_SUI_CHALLENGE→challenge 命令链。 |
| G3 时间/暂停 | 通过（自动化） | 现有 runtime/acceptance 回归覆盖 90/30/15/10、必选暂停、可选到期、后继调度、旧任务隔离；本轮未改统一计时器。 |
| G4 界面操作 | 通过（本地 Chromium） | 本轮真实 Playwright：核心 acceptance 4 项、产品/布局 3 项、多人/响应 2 项，共 9 项通过；手机颜色、多选、目标、响应、商店、暂停恢复及桌面/横竖屏流程均在测试中执行。 |
| G5 产品完整性 | 通过（本地 Chromium） | 入口/昵称/头像/5 席大厅/图鉴、胜负→REMATCH→重新 READY、多人重连均通过；证据见 `playwright-product-table-round2-final.log`、`playwright-acceptance-round2-final.log`、`playwright-multiplayer-round2-final.log`。
- 截图：`artifacts/acceptance/round2-*.png`（与旧命名截图分离）。 |
| G6 渲染 | 通过（本地开发/生产） | 生产构建页面 computed-style 探针确认四色背景和底纹、wild conic-gradient；4 项视觉/卡图测试通过，当前截图已另存为 artifacts/acceptance/round2-*.png。 |
| G7 交付/协议 | 通过 | 68 manifest、13 card crops、12 avatars 校验通过；Vite 1761 modules 构建通过；公开/私有窗口回归通过；11 个 shell 脚本 LF、`bash -n` 和入口帮助通过。 |
| G8 目标机资源 | 未验证 | 本轮未通过 SSH 或远端部署执行；没有把历史远端结果或旧证据当作当前候选版本证据。 |

## 三项问题逐项闭环

### 1. 有岁错误质疑与隐私

根因是 `open_has_sui_challenge` 先计算私有 `eligible_card_ids`，为空就不创建公开窗口；下游失败处罚因此不可达。当前实现仅在来源已空手时跳过无意义终局窗口；只要来源仍有牌，公开创建统一的 10 秒 `HAS_SUI_CHALLENGE`。合格岁牌 ID 在 effect 内冻结，初始公开 prompt 不包含 `private_option_card_ids`、持岁标志或数量。提交错误质疑后，服务端依据冻结集合进入失败路径并让质疑者摸四张；成功路径仍进入被质疑者 30 秒必选交付。

回归证据：

- `test_has_sui_wrong_challenge_after_real_play_draws_four`
- 公开手牌数相同、仅私有持岁类别不同的 prompt 隐私对照
- 有岁成功交付、非法交付、重复 action/prompt、重连及继续等待隔离

### 2. UNO 卡面颜色覆盖

根因是 `app.css` 后加载的通用 `.uno-card-face { background: #616e73; }` 与产品卡面类同特异性，覆盖 `product.css` 的四色和 wild。当前删除该旧背景声明，保留布局/边框/状态规则，由 `product.css` 单独拥有卡面颜色语义。生产页面 computed style 证据显示：红 `rgb(187,57,60)`、黄 `rgb(208,165,36)`、绿 `rgb(37,128,96)`、蓝 `rgb(45,104,157)`，wild 使用四色 conic-gradient，均保留底纹/渐变。

### 3. Linux 入口

新增 `.gitattributes`：`scripts/*.sh text eol=lf`。11 个 shell 文件均无 CRLF、shebang 为 env bash，Git Bash 下全部 `bash -n` 通过；`bash scripts/run_tests.sh --help` 退出码 0，脚本使用仓库相对路径、可配置 Python 和隔离临时数据目录。

## 子 Agent 交接说明

本轮按用户要求启动了 A（规则/运行时）、B（前端 CSS）、C（Linux 脚本）、D（独立 QA）四个角色。当前会话的子 Agent 运行环境没有 shell/文件读写能力，且 CUA 浏览器接口最初因认证方式不可用，因此它们没有直接编辑或运行项目；各角色提供了根因、测试和验收建议。实际修改、集成、测试和最终判断由协调线程完成；不把子 Agent 自报完成当作验收证据。

## 未验证项与边界

- G8：未在 Ubuntu 22.04 / 2 vCPU / 2 GiB 目标机运行本轮候选版本，资源门槛与远端五人/第六人契约均不宣称通过。
- 未部署、未修改 systemd/Nginx/防火墙、未读写远端真实房间数据。
- 浏览器证据为本地现有 Chrome/Playwright，不能替代目标机资源验证。
- Starlette/anyio 产生 1 条弃用 warning；本轮未升级无关依赖。

## 证据索引

- 后端：`artifacts/acceptance/backend-full-20260929-round2-final.log`、`backend-full-20260929-round2-final.xml`
- 素材：`asset-validation-20260929-round2-final.log`
- 构建：`frontend-build-20260929-round2-final.log`
- 生产计算样式：`production-card-computed-style-20260929-round2.log`
- 浏览器：`playwright-acceptance-round2-final.log`、`playwright-product-table-round2-final.log`、`playwright-multiplayer-round2-final.log`
- 测试发现：`e2e-list-20260929-round2.log`
- Linux：`bash-portability-20260929-round2-final.log`
- 机器摘要：`artifacts/acceptance/final-gates-20260929-round2.json`
