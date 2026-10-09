# Agent E（qa）交接（2026-09-28）

> 历史记录说明：本文保留执行时记录；其中“三项集中裁决”的措辞已由 `docs/RULE_AMBIGUITIES.md` 取代。当前口径是实施假设，非新增用户裁决。

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

## Wave 3 阶段性集成复验（2026-09-28，已由后续补充验收更新）

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
- 前端生产构建：`tsc && vite build` 通过，Vite 8.0.16 转换 1761 modules；CSS 定位修复后的最终复核为 `built in 420ms`。
- 开发机资源样本：实际 PID `36316`，1 个 5 人房间、5 个已认证 WebSocket、15 秒、每连接 0.2 秒 ping/pong；平均/峰值单逻辑核 CPU `1.2% / 6.1%`，平均/峰值 RSS `59.8 / 59.84 MiB`。采样结束后仅按已核对命令行精确终止 PID 36316 及其启动包装进程 24608。

### 阶段性 G1–G8 结论（最终状态见下节）

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

最终总体结论（已由后续补充验收更新）：G1–G7 通过；G8 未通过目标机契约门槛。三个规则边界已由协调线程集中裁决并纳入行为回归；旧失败日志保留为迁移过程证据，最终结论以带 `-final` 的当前日志为准。

## G4/G5/G6 补充验收（2026-09-28）

协调线程要求继续补齐可在当前开发机完成的浏览器证据；本节只修改 QA 所有权内的 E2E、证据和本记录，未修改产品代码。

### 新增规格与结果

1. `frontend/e2e/acceptance/visual-layouts.spec.ts`
   - 隔离端口：后端 `18131`，前端 `15181`。
   - 结果：`1 passed (7.9s)`。
   - 新增当前运行截图：
     - `layout-desktop-1920x1080.png`
     - `layout-portrait-390x844-top.png`
     - `layout-portrait-390x844.png`
   - 与既有 1366×768、360×640、844×390 证据共同覆盖全部指定视口。
2. `frontend/e2e/acceptance/round-rematch.spec.ts`
   - 隔离端口：后端 `18132`，前端 `15182`。
   - 结果：`1 passed (7.4s)`。
   - TEST_MODE 仅建立“一张合法末牌”的临界状态；末牌出牌、胜负展示、房主点击“再来一局”、双方重新 READY、房主再次开局均通过真实 UI 完成。
   - 验证胜者/剩余牌数显示，REMATCH 后双方均为“未准备”、开局按钮禁用；双方各自准备后按钮启用，新局双方均收到 7 张牌。
3. `frontend/e2e/acceptance/mobile-operations.spec.ts`
   - 最终隔离端口：后端 `18137`，前端 `15187`。
   - 结果：`1 passed (39.9s)`。
   - 390×844 竖屏通过 UI 完成：易牌两张支付牌多选、通配牌选蓝、望牌选择真实目标、岁牌响应链。
   - 844×390 横屏通过 UI 完成：展开商店、选择真实商品、按颜色匹配支付牌、确认购买并验证商品进入手牌。
   - 年牌必选弃牌真实等待服务端 30 秒后进入暂停；暂停状态在 844×390 与 390×844 均截图并确认操作可见；房主通过 UI 点击“继续等待并重置时限”，原 `discard_card` 步骤恢复且倒计时不为 0。
   - TEST_MODE 仅用于建立难以稳定随机得到的手牌/回合，待验操作本身未通过直接 API 替代。

### 新截图

- `mobile-portrait-multiselect-390x844.png`
- `mobile-landscape-shop-844x390.png`
- `mobile-landscape-pause-844x390.png`
- `mobile-portrait-pause-390x844.png`

### 发现的产品视觉缺陷

- owner：C / `table_ui`。
- 严重程度：低（短时遮挡，不阻断点击）。
- 复现：5 人牌局中触发任一真实状态事件后立即观察 1920×1080 牌桌。
- 实际：`.event-feedback` 使用 `position:absolute; top:86px`，在 1.8 秒动效期间覆盖回合栏的当前玩家/颜色文字；证据为 `layout-desktop-1920x1080.png`。
- 预期：醒目反馈不遮挡回合关键信息，或占用独立布局区域。
- QA 未越界修改 `App.tsx` / `app.css`，已回报协调线程转交 C。

### 更新后的门槛结论

- G4：通过。指定手机横竖视口已有真实 UI 多选、选色、目标、响应、购物以及暂停恢复证据；桌面围桌与常驻商品已有 1366/1920 当前截图。
- G5：通过。入口/昵称/头像/公开邀请/二维码/5 座位/图鉴的 2 项浏览器用例，加上本轮真实胜负→REMATCH→重新 READY→再开局链，覆盖基础产品入口。
- G6：通过。C 将桌面 `.event-feedback` 从 `top:86px` 调整到 `132px`；QA 在修复后的当前集成版本重跑扩展视觉规格并目视 1920×1080、1366×768、390×844、844×390，反馈不再遮挡回合信息。
- G8：结论不变，目标机资源门槛仍未通过。

### 修复后最终合跑

命令（隔离端口后端 `18140`、前端 `15190`）：

```powershell
npx playwright test e2e/acceptance/visual-layouts.spec.ts e2e/acceptance/round-rematch.spec.ts e2e/acceptance/mobile-operations.spec.ts e2e/acceptance/card-gallery-visual.spec.ts --project=chromium --reporter=line
```

结果：`4 passed (45.6s)`。最终日志：`artifacts/acceptance/playwright-acceptance-expanded-20260928-final.log`。

新增 `card-gallery-visual.spec.ts` 对图鉴 13 个角色卡面逐项断言图片加载完成，并生成顶部/中部/底部三张当前截图。最终 G4、G5、G6 均判定通过。

## 有岁旧测试预期迁移（2026-09-29）

按已确认规则，有岁质疑只在完整回合及关联效果结束时检查，并且仅当来源玩家此时仍持有岁牌才开放窗口。本轮只迁移测试，不修改产品代码：

- `test_has_sui_failed_question_penalizes_challenger` 的夹具让来源玩家只持有普通 UNO 牌，却期待开放质疑并处罚质疑者，和已确认规则冲突。现改名为 `test_has_sui_does_not_open_when_completed_player_holds_no_sui`，断言不开放窗口、不罚摸且 helper 本身不推进回合。
- 历史报告中 `test_special_card_resolvers.py` 的五个失败逐项复核后，`纪`有后续弃牌、`岁相`和摸到`符咒`三个场景在当前版本保持原预期并通过，不应迁移。
- `余`支付四种颜色后手牌为空，以及只剩最后一张`纪`且关联响应全部结束的两个场景，没有可用于有岁判定的剩余岁牌，应直接进入正常胜负结算。旧的“轮转到下家”断言改为 `FINISHED`、`ROUND_RESULT` 和来源玩家为胜者。

隔离验证命令：

```powershell
$qaData = Join-Path ([IO.Path]::GetTempPath()) ('suicardgame-qa-sui-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qaData -Force | Out-Null
$env:SUICARDGAME_DATA_DIR = $qaData
$env:TEST_MODE = '1'
python -m pytest -q backend/tests/test_special_card_resolvers.py backend/tests/agent_rules/test_rule_windows.py --maxfail=20
```

定向验证（历史五项 resolver 加迁移后的无岁边界测试）：`6 passed in 1.32s`。

两份完整文件回归：`28 passed, 4 failed in 1.47s`。剩余四项均在 rules Agent 已改动的窗口测试中，期待无剩余岁牌时仍创建 `HAS_SUI_CHALLENGE`：

- `test_ling_reaction_allows_self_protecting_zuole_and_higher_rank_evade`
- `test_shu_omitted_unique_remainder_target_leaves_one_card_and_opens_uno_window`
- `test_shu_empty_hand_finishes_only_after_has_sui_chain_resolves`
- `test_wang_nested_wild_draw_four_resolves_and_restores_control_chain`

这些预期随后已按同一规则迁移：无岁牌来源不创建窗口，主动效果完成后继续推进或结束；被动摸牌效果不因空手伪造胜利。

## 最终复核（2026-09-29）

- `python -m pytest -q backend/tests --junitxml=artifacts/acceptance/backend-full-20260929-final.xml`：`264 passed, 1 warning`。
- `python scripts/validate-card-assets.py`：`68 manifest assets, 13 card crops and 12 avatars`。
- `npm run build`：Vite 转换 `1761 modules`，通过。
- `npm run test:e2e -- --project=chromium frontend/e2e/acceptance`：`4 passed (42.6s)`。
- 远端 G8 采样证据见 `artifacts/acceptance/g8-remote-probe-20260929.json` 与 `g8-remote-process-20260929.json`；资源结果合格，但远端现有代码第六人返回 200，故 G8 契约门槛不通过。
