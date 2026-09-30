# Agent A runtime 交接（2026-09-28 更新）

## 基线与范围

- 基线提交：`0559f48 feat(release): prepare suicardgame v1.2`
- 工作分支：`codex/suicardgame-v1.2`
- 续接工作区中已有的 runtime 未提交改动；未覆盖或暂存其他 Agent/用户改动。
- 本 Agent 未创建提交；交付形态为当前工作区中下列文件的未提交 patch。

## 已完成

- 普通回合独立持久时钟：`turn_deadline_at` + `turn_sequence`，90 秒到期原地暂停，不摸牌、不换人。
- 特殊窗口统一调度：质疑 10 秒、可选响应 15 秒、必选操作 30 秒；窗口消费后自动取消旧任务并调度后继窗口。
- 修正必选 `HAS_SUI_CHALLENGE/give_card` 恢复后误用 10 秒的问题，恢复时获得完整 30 秒。
- 必选窗口到期保留 `current_prompt`、`effect_queue` 和私有候选；`CONTINUE_WAITING` 轮换 `prompt_id` 并重置当前步骤时限，旧响应失效。
- `ABORT_GAME` 仅允许房主在暂停状态中使用；结果阶段无伪胜者。`REMATCH` 返回大厅并清空准备状态。
- 调度指纹包含 `game_id`、`game_epoch`、deadline 和窗口/回合代次；重置、恢复、后继窗口会取消/隔离旧回调。
- 启动恢复：旧活动房间缺少普通回合时钟时补 90 秒；过期必选步骤恢复为暂停；可选过期窗口留给默认动作消费。
- 快照加载时所有旧传输会话标记为离线，必须重连后才满足“全员在线且 READY”开局条件。
- 2–5 人、第五人可加入、第六人服务端拒绝；头像 ID 经过固定 allowlist 校验并进入公开/私有快照和持久化。
- 已接入 rules 同步入口 `open_has_sui_challenge(room, completed_player_id, advance_steps=...)`；runtime 只负责原子命令后的持久化、调度和广播，不在规则层创建 timer。
- 修复 `TEST_OPEN_RESPONSE_WINDOW` 在 Windows 上硬编码 `/tmp` 的问题：改用 `tempfile.gettempdir()` 的解析路径，同时保留 `TEST_MODE=1`、系统临时目录内、首级目录名以 `suicardgame-step8-` 开头三重安全边界。
- 修复特殊响应私有快照把 card ID 误当作合法响应名的问题：`legal_responses` 只返回当前玩家实际可执行的动作；仅当前有权响应且确有本人候选时才附带 `private_option_card_ids`。公开快照、无候选响应者、等待玩家和已响应玩家完全省略该私有 key，不泄露字段形态或他人 card ID。

## 新增/变化接口

| 接口 | 说明 |
|---|---|
| `GameState.turn_deadline_at` / `turn_sequence` | 普通回合时钟及代次隔离 |
| `GameState.pause_state` | 持久暂停原因、原 prompt、步骤类别、时间 |
| `Prompt.required` | 持久必选/可选分类 |
| `CONTINUE_WAITING` | 仅房主；恢复暂停步骤并重置该步骤时限 |
| `ABORT_GAME` | 仅房主且仅暂停时；中止本局、无胜者 |
| `recover_runtime_state(room)` | 加载快照后的时钟/暂停/窗口身份恢复 |
| `backend.app.engine.runtime` | 90/30/15/10 时限及 prompt 分类/身份规范化 |
| `avatar_id` | create/join/session/player snapshot 的稳定头像字段 |
| `pending_action.private_option_card_ids?` | 可选字段；仅当前响应者确有本人候选牌时出现，与 `legal_responses` 动作名分离 |

## 修改文件

- `backend/app/domain/room.py`
- `backend/app/engine/command_handler.py`
- `backend/app/engine/runtime/__init__.py`（新增）
- `backend/app/engine/runtime/deadlines.py`（新增）
- `backend/app/main.py`
- `backend/app/repositories/json_store.py`
- `backend/tests/agent_runtime/test_deadlines.py`
- `docs/agent-notes/runtime.md`

## 验证

1. `PYTHONPATH=. python -m pytest backend/tests/agent_runtime -q`
   - 结果：`17 passed, 1 warning in 1.89s`
   - 警告：FastAPI TestClient 的 `httpx2` 弃用提示，不影响断言。
   - 新增覆盖：系统临时目录下唯一 Step8 数据目录允许；系统临时目录外即使名称匹配也拒绝。
   - 隐私覆盖：Yi/Ling/Shu 的 `SUI_REACTION` 无牌者仍可 pass；左乐/高辈分牌仅向持有者暴露相应动作和本人 card ID。
2. `python -m compileall -q backend/app/domain/room.py backend/app/engine/command_handler.py backend/app/engine/runtime backend/app/main.py backend/app/repositories/json_store.py`
   - 结果：通过，无输出。
3. `git diff --check -- <runtime owned paths>`
   - 结果：通过；仅 Git 提示部分工作树文件未来可能由 LF 转 CRLF。
4. 相关回归合跑：`backend/tests/agent_runtime backend/tests/test_player_limits_v12.py backend/tests/test_persistence.py backend/tests/test_wild_draw_four_challenge.py`
   - 结果：`21 passed, 1 failed, 1 warning in 2.63s`。
   - 唯一失败：`test_challenge_window_is_single_use` 仍断言 +4 结算后 `current_prompt is None`；当前 rules 会按新需求打开 `HAS_SUI_CHALLENGE`，该旧预期应由 QA 迁移，未通过篡改产品行为规避。
5. 快照隐私相关回归：`backend/tests/test_response_window_privacy.py backend/tests/test_response_window_security.py backend/tests/test_response_window_reconnect.py backend/tests/test_special_snapshot_privacy.py`
   - 结果：`16 passed, 1 warning in 2.42s`。
6. 公开私有字段修复定向合跑：崇岳公开摘要指名失败、全部 `agent_runtime`、窗口/特殊快照隐私测试。
   - 结果：`34 passed, 1 warning in 3.91s`。

## 未验证/集成注意

- 未运行全量后端测试、浏览器 E2E、资源采样或长期真实 90/30/15/10 秒等待；按协调线程要求仅运行轻量和相关回归。
- 当前全局工作区同时存在 rules、旧测试和前端的未提交改动；未执行 commit、checkout、reset 或全量暂存。
- 仓库根 `.gitignore` 的 `runtime/` 规则会忽略新增的 `backend/app/engine/runtime/`；集成提交时必须显式使用 `git add -f backend/app/engine/runtime/__init__.py backend/app/engine/runtime/deadlines.py`，否则这两个已验证文件不会进入提交。
- `special_effects.py` 的窗口创建/后继推进由 rules Agent 所有；其最终变更若新增 prompt kind/default action，应继续使用持久 `required`，并由 `backend.app.engine.runtime` 补充对应时限分类。
