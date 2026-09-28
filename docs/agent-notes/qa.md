# Agent E（qa）交接（2026-09-28）

## 范围与基线

- 基线提交：`0559f48 feat(release): prepare suicardgame v1.2`。
- 当前分支：`codex/suicardgame-v1.2`；工作区存在 A/B/主线程并行未提交产品改动，QA 未修改产品实现。
- 审计附件只作为失败证据。八项语义已迁移到 `backend/tests/acceptance/test_audit_semantics.py`，未沿用附件截图作为本轮证据。
- 首次定向旧回归（16 个相关旧测试文件）：`19 passed, 60 failed`，失败主体为旧夹具未让全员真实 `READY`；另有 +4/有岁后继窗口旧预期差异。

## 本轮测试迁移

- 新增 `backend/tests/ready_helpers.py`：通过真实 `READY`/`RESPOND_TO_PROMPT` 命令准备玩家、完成可选有岁质疑链，不 monkeypatch `start_game`，不直接改 `Player.ready`。
- 旧成功开局夹具改为房主和所有在座者真实 READY；“无需 READY 可开局”旧测试改为先断言 `PLAYERS_NOT_READY`，再全员 READY 后开局。
- reset/rematch 后明确重新 READY；第六人拒绝与 5 个唯一座位已在 `test_api_concurrency.py`/现有容量测试中保持业务断言。
- 普通 UNO/+4 旧测试适配新的完整回合语义：动作结束先进入 `HAS_SUI_CHALLENGE`，由真实响应命令放弃后再断言下一行动人；旧 prompt 重放仍断言 `STALE_PROMPT`，未删除单次消费检查。
- `frontend/playwright.config.ts` 与 `scripts/run_tests.sh` 已有可移植路径改动，但首轮未启动浏览器或执行全量脚本。

## 八项审计语义映射

`backend/tests/acceptance/test_audit_semantics.py` 包含 8 个独立行为验收：

1. 完整回合后手里仍有岁牌，开启有岁质疑。
2. 年牌必选弃牌到期保留步骤并暂停。
3. 吃申报不会阻止后续更高优先级杠。
4. 望控制链允许嵌套 +4 并恢复/结束父链。
5. 令在修改目标手牌前开启左乐/规避响应。
6. +4 到期由服务端消费并罚摸。
7. 到期生成的后继窗口继续进入调度表。
8. 普通回合具有 90 秒 deadline，超时暂停且不改手牌/行动人。

## 当前验证证据

### 定向旧回归

命令（每次设置唯一 `%TEMP%/suicardgame-qa-targeted-<GUID>` 数据目录）：

```powershell
python -m pytest -q backend/tests/test_http_command_auth.py backend/tests/test_multiplayer_flow.py backend/tests/test_persistence.py backend/tests/test_reconnection.py backend/tests/test_response_window_foundation.py backend/tests/test_response_window_lifecycle.py backend/tests/test_response_window_security.py backend/tests/test_room_lifecycle.py backend/tests/test_room_lifecycle_start_regression.py backend/tests/test_session_identity_binding.py backend/tests/test_test_mode.py backend/tests/test_uno_core_rules.py backend/tests/test_uno_deck_and_game_end.py backend/tests/test_uno_wild_and_challenge.py backend/tests/test_websocket_auth.py backend/tests/test_wild_draw_four_challenge.py
```

结果：`79 passed, 1 warning in 3.71s`。warning 为 FastAPI/Starlette `httpx` 弃用提示，与本轮行为无关。

### 八项 acceptance

```powershell
python -m pytest -q backend/tests/acceptance/test_audit_semantics.py
```

结果：`8 passed in 1.18s`。

## 未执行/未通过门槛

- 已运行一次全部 `backend/tests`，但当时仍有产品与夹具失败，因此 G1 尚未通过；需 B 修复 Shu 产品链后重新运行并记录最终准确总数。
- 未运行前端 build、素材校验、Playwright 列表或浏览器 E2E；G4/G5/G6/G7 尚未验收。
- 未做 1366×768、1920×1080、360×640、390×844、844×390 的真实 UI 操作与当前截图。
- 未做 5 人真实浏览器流程、25 张手牌、购物、响应、暂停恢复、断线重连、结算/再来一局。
- 未采样可归属后端 PID 的 CPU/RSS；G8 尚未通过，开发机短测试不能替代目标机 2 vCPU/2 GiB 证据。
- response-window 测试已改用 `tempfile.mkdtemp(...)` 创建独立测试目录，不再硬编码 Linux `/tmp` 或生产 `data/rooms`。

## Wave 3 完整后端与缺陷闭环

首次完整运行命令：

```powershell
python -m pytest -q backend/tests --junitxml=artifacts/acceptance/backend-full.xml
```

- 使用独立 `SUICARDGAME_DATA_DIR`，未读写附件或原有 `data/rooms`。
- 结果：`182 passed, 73 failed, 1 warning in 16.07s`，总计 255 项。
- 证据：`artifacts/acceptance/backend-full.log`、`artifacts/acceptance/backend-full.xml`。
- 继续迁移 READY、发动前响应、有岁后置窗口、可移植临时目录后，相关九文件收敛到 `64 passed, 15 failed, 1 warning in 8.56s`。

已确认并迁移的旧规则预期：

- 令以发动前快照最大手牌数为目标；三人发动前均为 3 张时，令进入弃牌堆后发动者需补 1 张，最终为 `[3, 3, 3]`。
- 年牌申报收集完全部合法响应后再按“杠＞碰＞吃、同级方向距离”裁决；碰申报后由剩余响应者 `pass`，不能按先到先得立即结束。
- 黍完整关联效果与有岁窗口结束后，当前行动人已推进到下一玩家；旧测试不再要求发动者仍为当前玩家。

迁移后的令/年定向复验：`2 passed, 1 warning in 1.44s`。

当前阻塞为 B/rules 产品问题，QA 未通过助手掩盖：

- `_activate_shu` 会把用户显式提交的非法 `remainder_player_id` 静默改写为唯一合法接收者，导致非法命令返回成功。
- 无效黍激活在发动前响应完成后才失败，已经改变 `state_version`、prompt、当前行动人与 processed action，破坏无效命令原子性及 action-id replay。
- 黍剩 1 张未建立 UNO pending；清空手牌后仍为 `ACTIVE`，末牌完成链未结算。
- 最小复现包括 `test_shu_reject_invalid_remainder_recipient`、`test_step7r_invalid_remainder_recipient_rejected_without_state_change[non_minimum]`、`test_shu_distributes_selected_color_and_validates_remainder_target`。

协调线程已将以上问题回派 B/rules；修复前不放宽对应断言，也不继续扩大测试改写。

## 最终集成复验建议顺序

1. 八项 acceptance + A/B agent 定向测试。
2. 全部后端测试，确认无自动 READY、无新增 skip/xfail。
3. 素材验证与前端构建。
4. Playwright `--list` 后再执行真实多视口、多玩家 E2E。
5. 对实际后端 PID 进行有界 CPU/RSS 采样，并把开发机和目标机结果分开报告。

## 最终集成复验（2026-09-28）

### 当前版本证据

- 后端全量：`python -m pytest -q backend/tests --junitxml=artifacts/acceptance/backend-full-20260928-wave3.xml`
  - `258 passed, 1 warning in 14.32s`，无 skip/xfail；证据为 `backend-full-20260928-wave3.log` / `.xml`。
- 八项审计语义：`8 passed in 1.18s`；rules 专属行为：`10 passed`；runtime 专属行为：`17 passed`。
- 真实多人浏览器流程：`frontend/e2e/multiplayer.spec.ts` 最终 `1 passed (19.8s)`。
  - 旧流程在摸牌后直接期待下一玩家可操作；当前规则会先开启完整回合结束的 `HAS_SUI_CHALLENGE`。测试已改为通过页面按钮真实拒绝该窗口，再验证下一玩家，未使用 API 跳过待验操作。
- 产品入口/大厅/图鉴：`agent_product/product-entry-lobby-rules.spec.ts` 最终 `2 passed (5.3s)`。
- 三布局与 5 人/25 张手牌：`acceptance/visual-layouts.spec.ts` 最终 `1 passed (5.6s)`；新增并实际生成 `layout-portrait-360x640-top.png`、`layout-landscape-844x390-top.png`，截图前断言 `window.scrollY === 0`。
- 手机旋转与上下文选牌/商店：`agent_table/table-layout-accessibility.spec.ts` 隔离端口复验 `1 passed (5.8s)`。
- 素材校验：`validated 68 manifest assets, 13 card crops and 12 avatars`。
- 前端生产构建：`tsc && vite build` 通过，Vite 8.0.16 转换 1761 modules，`built in 430ms`。
- 开发机资源样本：实际 PID `36316`，1 个 5 人房间、5 个已认证 WebSocket、15 秒、每连接 0.2 秒 ping/pong；平均/峰值单逻辑核 CPU `1.2% / 6.1%`，平均/峰值 RSS `59.8 / 59.84 MiB`。采样结束后仅按已核对命令行精确终止 PID 36316 及其启动包装进程 24608。

### G1–G8 独立结论

| 门槛 | 结论 | 当前证据与缺口 |
|---|---|---|
| G1 后端回归 | 通过 | 正式 READY 迁移后的全量 `258 passed`；无自动 READY monkeypatch、无 skip/xfail。 |
| G2 关键规则 | 通过（已决定范围） | 八项审计语义全部通过；有岁、规避、年竞争、望嵌套、左乐即时响应均有 rules/acceptance 测试。多人同时有岁质疑等用户尚未裁决边界仍按 `RULE_DECISION_REQUIRED` 暂停，不伪造结论。 |
| G3 时间/暂停 | 通过（自动化） | runtime 17 项与八项 acceptance 覆盖 90/30/15/10、必选暂停、可选默认、后继调度、旧 timer/重置隔离、重连恢复；使用可注入时钟，不做真实几十秒 sleep。 |
| G4 界面操作 | 部分通过 | 当前 Chromium 已通过桌面多人流程、手机横竖旋转、颜色、多选、商店展开/支付选择和核心按钮可达；尚未以手机视口逐项完成目标选择、真实响应、购买确认、暂停恢复的全业务矩阵。 |
| G5 产品完整性 | 部分通过 | 昵称记忆、头像、公开邀请/二维码、5 座位、结构化图鉴有当前浏览器证据；结算/再来一局/重新准备已有代码与后端回归，但未完成浏览器端完整胜负到重开流程。 |
| G6 渲染 | 部分通过 | 有当前 1366×768、360×640 顶部/操作区、844×390 顶部/操作区截图；5 人、25 张手牌、8 商品无座位覆盖。缺 1920×1080、390×844 的本轮截图及全卡逐张浏览器目视。 |
| G7 构建与协议 | 通过 | 当前素材校验与生产构建通过；后端全量含授权、幂等、快照隐私/重连回归，`private_option_card_ids` 与 TypeScript 构建一致。 |
| G8 资源 | 未通过目标机门槛 | 本机可归属 PID 的有界样本有效，但环境是 Windows 16 逻辑核/约 32 GiB，不是 Ubuntu 22.04、2 vCPU / 2 GiB，不能作为目标机容量证明。 |

最终总体结论：G1、G2、G3、G7 通过；G4、G5、G6 部分通过；G8 未通过目标机证据门槛。旧失败日志保留为迁移过程证据，最终结论以带 `-final` 或 `-wave3` 的当前日志为准。
