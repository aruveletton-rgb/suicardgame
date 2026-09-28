# 修复协作契约 v1（2026-09-28）

本契约以 `0559f48` 的现有模型为基线。主线程负责变更控制；执行线程不得跨越本轮约定的文件所有权。`docs/agent-notes/` 下各线程仅修改自己的记录。

| 边界 | 冻结约定 |
|---|---|
| 房间/暂停 | 继续使用 `RoomPhase`、`GameStatus`、`GameState.current_prompt`。暂停是当前对局的独立持久字段 `pause_state`，不是新的房间阶段；其中至少有暂停原因、原 `prompt_id`、步骤类别、触发时间。暂停时 `current_prompt` 及效果上下文保持不变，不推进回合。中止使用 `ABORTED_BY_ROOM_RESET`，公开快照不得伪造胜者。 |
| 操作身份 | `source_player_id` 是效果来源；`target_player_id` 是受影响者；望控制时另外记录控制者、被控制人及手牌所有者。控制者只接收被授权范围内的私有手牌，不能扩大为全房公开。父子效果使用 `effect_queue` 中的显式上下文/恢复点，禁止覆盖父窗口后丢失。 |
| 窗口 | 沿用 `Prompt` 的 `prompt_id`、`kind`、`responder_ids`、`resolution_policy`、`deadline_at`、`default_action`、`response_records`、`game_id/game_epoch`。必选与可选的区别必须可从窗口持久数据确定；可选到期视为放弃，必选到期进入暂停。关闭/续期需改变可验证的窗口代次，拒绝旧提交。私有候选仅放入 `private_options_by_responder`。 |
| 计时 | 普通回合 90 秒使用独立持久 `turn_deadline_at`/代次，并在快照呈现虚拟 `TURN_MAIN` 步骤，避免占用特殊规则的 `current_prompt`；必选选色、目标、多选、交付等 30 秒；可选左乐/规避/吃碰杠 15 秒；质疑 10 秒。只有 runtime 统一调度有效 deadline；窗口消费、暂停、重置、后继窗口生成时取消/失效旧任务并调度新任务。恢复等待重置当前步骤时限。客户端倒计时只显示。 |
| 规则调用 | rules 模块只改变当前 `Room/GameState` 并返回明确的“等待窗口/继续效果/完成”结果或抛规则错误，不直接创建异步计时器、不自行持久化或广播；runtime 的单房间锁内调用规则，再原子保存、调度、广播。若现有同步函数已执行推进，入口不得再次推进。 |
| 命令 | 保留 `READY`、`START_GAME`、`PLAY_CARD`、`DRAW_CARD`、`ACTIVATE_SPECIAL`、`RESPOND_TO_PROMPT`、`BUY_SHOP_GOOD`、`REFRESH_SHOP`、`REMATCH`、`RESET_ROOM` 与 UNO 命令。新增 `CONTINUE_WAITING`（仅房主，恢复暂停步骤）和 `ABORT_GAME`（仅房主，标记中止并进结果阶段）；二者需 `action_id` 幂等和已有 game/version 校验。`REMATCH` 返回大厅并清除准备。 |
| 快照 | 公开状态含座次、在线/准备、牌数、公开牌、当前行动人、公开窗口、暂停状态、胜者及结算牌数；私有状态含本人手牌、本人合法响应/候选、受控授权手牌。不能在公开 `special_state` 或日志中泄露私有卡牌集合。TypeScript `types.ts` 与服务端字段一一对应。 |
| UI 交接 | product_ui 提供由 props/callback 驱动的 Entry、Lobby、Card、Rules、Result，不持有 WebSocket。table_ui 在 `App.tsx` 中统一持有网络/选牌状态；主牌、支付牌集合、颜色、目标和响应窗口分别记录；横竖屏切换不得重置。D 的样式只用 `product.css` 作用域，C 维护全局设计变量。 |
| 兼容 | JSON 快照新增字段有缺省值；旧房间原样加载，不因超过新上限而驱逐已有玩家。进程重启时，过期必选窗口恢复为暂停，不能执行默认罚摸；旧命令与旧 timer 依 game/prompt/代次校验作废。隔离测试数据目录，不读写现有真实房间。 |

## 变更记录

- v1：冻结上述字段语义、命令名与所有权。
- v1.1：普通回合时钟与特殊 `current_prompt` 分离，以 `turn_deadline_at`/代次持久化；特殊窗口新增持久 `required` 标志。此调整不改变 90 秒暂停规则。规则模块提供 `open_has_sui_challenge(room, player_id)` 等同步入口，runtime 在回合及关联效果结束时接线。接口需要再调整时由提出方先通知主线程。

## 尚待用户裁决（不阻塞其他工作）

多人同时“有岁”质疑的竞争顺序、最后一张牌连锁后的胜负顺序、同时“看到”事件排序；先核对现行权威规则是否已有依据。90/30/15/10 秒与必选暂停不是待决项。
