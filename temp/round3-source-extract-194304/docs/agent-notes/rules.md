# Rules Agent 交接（2026-09-28）

基线：`0559f48800aa589df32440a7d8e7c270da1cc64d`。共享工作区内续接既有未提交 rules 改动；未覆盖其他 Agent 文件。

## 已实现

- 有岁：`open_has_sui_challenge(room, completed_player_id, *, advance_steps=1) -> bool` 冻结窗口开启时被质疑者手中的岁牌 ID；10 秒逐人质疑，成功后转为被质疑者 30 秒必选交付窗口。成功时自选交付一张冻结集合内且仍在手中的岁牌并摸四张；失败时质疑者摸四张。罚摸牌不倒算本次判定。
- 高辈分规避：受影响玩家可在对应 `current_prompt` 以 `evade` + `card_id` 弃置更高辈分岁牌；只写入当前效果的 `immune_player_ids`，不发动弃牌本身能力，不产生永久免疫。合法候选只放在当前响应者的 `private_options_by_responder`。
- 左乐：可在岁牌响应窗口以 `use_zuole` + `card_id` + `target_player_id` 保护任意在座玩家（包括自己），免疫只属于当前效果。
- 即时岁牌生效前响应：新增持久效果类型 `sui_activation_reaction`，用于易、黍、重岳、望；令使用原有 `ling_reaction`。所有响应完成或 15 秒逐人放弃后才应用效果；规则层不创建 timer。
- 年：收集所有有效吃/碰/杠申报后按 `杠 > 碰 > 吃`、同级方向距离裁决；仅下家可吃；落选申报不扣牌。必选回合末弃牌 `required=True`，规则过期入口保留窗口不推进。
- 望：允许控制普通牌、+4 与岁牌；子效果通过 `parent_wang_source_card_id` 恢复父控制链。+4 质疑、令等嵌套窗口完成后继续望控制，场地牌仍拒绝。
- 其余既有行为保持：夕仅在被动需求窗口替代；绩/余按逐人选择；易保留本回合可重复；令冻结发动时最大手牌数；黍按当前最少手牌者处理余数；岁相/符咒保留事件去重与牌区移动；商店保持牌张移动。

## Runtime / API 接口

- Runtime 在完整回合与关联效果结束、尚未推进时调用 `open_has_sui_challenge`；返回 `True` 时不得重复推进。rules 内多步效果的 `_finish_effect_and_advance` 已自行接线，入口不要二次推进。
- `respond_special_prompt` 新增/使用响应：`challenge`、`decline_challenge`、`give_card`、`evade`、`use_zuole`、`pass`。即时响应窗口是普通持久 `Prompt`，runtime 按 prompt ID/代次调度即可。
- `expire_special_prompt` 仅消费可选窗口；`HAS_SUI_CHALLENGE(required=True)` 与 `NIAN_TURN_END_DISCARD(required=True)` 返回 `False`，由 runtime 暂停并保留原窗口。到期产生后继 prompt 时 runtime 必须重新调度。
- 新效果不持久化/广播/创建异步任务；继续依赖 A 的单房间原子保存、广播与统一 deadline 调度。

## 验证

- `python -m py_compile backend/app/engine/special_effects.py backend/app/rules/sui/catalog.py`：通过。
- `python -m pytest backend/tests/agent_rules -q`：`10 passed in 1.42s`。
- `git diff --check -- <rules owned paths>`：通过（Git 仅提示现有 LF/CRLF 转换警告）。

专属测试覆盖：有岁成功/失败与私有交付选项、年竞争、令左乐与高辈分规避、易的生效前左乐、黍的高辈分规避、望目标规避、望嵌套 +4/令及父链恢复、可选即时响应连续到期。

## 未决与未验证

- 多名玩家同时“有岁！”质疑仍无权威顺序。当前逐座次收集；第二名也选择质疑时返回 `RULE_DECISION_REQUIRED`，不扣牌、不静默裁决。候选解释：首个有效质疑者获得权利；或全部声明后按方向距离裁决。影响交付归属和后续罚摸对象。
- 最后一张牌触发嵌套效果后的胜负顺序、同时“看到”事件排序仍待用户裁决，未在 rules 层擅自扩展。
- 未运行全量后端测试；旧测试仍含“特殊效果结束后立即无 prompt”和“年申报先到先得”等已被新规则取代的预期，应由 QA 按真实 READY 和新窗口流程迁移后复验。
- 未做 HTTP/WS 集成、重启恢复或浏览器验收；由 runtime/QA 在集成版本验证。
