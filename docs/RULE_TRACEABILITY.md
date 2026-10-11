# 规则追踪矩阵

当前规则来源为 `docs/PLAYER_MANUAL.md` 与 `backend/rules/special_cards.yaml`。旧提示词和已移除牌种不作为当前验收依据。

| 规则 | 来源 | 后端文件 | 测试 | 前端文件 | 规则页 |
|---|---|---|---|---|---|
| 经典 108 张四色牌组 | 本提示词 4.1 | `backend/app/domain/cards.py` | `backend/tests/test_cards.py` | `frontend/src/components/CardView.tsx` | `frontend/src/data/rules.ts` |
| 每人起手 7 张 | 玩家手册 2 | `backend/app/engine/command_handler.py` | `backend/tests/test_room_lifecycle.py` | `frontend/src/App.tsx` | `frontend/src/data/rules.ts` |
| 禁止白色牌 | 四色牌组 | `backend/app/domain/cards.py` | `backend/tests/test_cards.py` | 资产 manifest | `frontend/src/data/rules.ts` |
| Wild Draw Four 普通出牌限制、同类接力和选色 | 玩家手册 2/3 | `backend/app/rules/uno.py`, `backend/app/engine/command_handler.py` | `backend/tests/test_uno_rules.py`, `backend/tests/test_action_stacks.py` | `frontend/src/App.tsx`, `frontend/src/game/playable.ts` | `frontend/src/data/rules.ts` |
| 加牌、禁牌同类接力；接受加牌后继续回合 | 玩家手册 2/3 | `backend/app/engine/action_stack.py`, `backend/app/engine/command_handler.py`, `backend/app/engine/special_effects.py` | `backend/tests/test_action_stacks.py`, `backend/tests/test_player_action_updates.py` | `frontend/src/App.tsx` | `frontend/src/data/rules.ts` |
| 当前特殊牌配置及旧牌种移除 | 当前 YAML | `backend/app/domain/cards.py` | `backend/tests/test_cards.py`, `backend/tests/test_current_rule_removals.py` | `frontend/src/data/rules.ts` | `frontend/src/data/rules.ts` |
| 坎诺特为场地 NPC | 卡面 + 本提示词 6.13 | `backend/app/domain/cards.py`, `backend/app/engine/command_handler.py` | `backend/tests/test_cards.py`, `backend/tests/test_room_lifecycle.py` | `frontend/src/App.tsx` | `frontend/src/data/rules.ts` |
| Reset 回大厅并隔离旧局 | 玩家手册 8 | `backend/app/engine/command_handler.py` | `backend/tests/test_room_lifecycle.py` | `frontend/src/App.tsx` | `docs/PLAYER_MANUAL.md` |
| 每张实体牌唯一位置 | 本提示词 8.3 | `backend/app/engine/invariants.py` | `backend/tests/test_invariants.py` | 不适用 | 架构文档 |
| 当前八种岁牌结算、规避和响应 | 玩家手册 4/5、当前 YAML | `backend/app/engine/special_effects.py`, `backend/app/rules/sui/catalog.py` | `backend/tests/test_special_card_exactness_matrix.py`, `backend/tests/agent_rules/test_rule_windows.py` | `frontend/src/App.tsx` | `frontend/src/data/rules.ts` |
| 重岳按方向逐人展示、逐张补牌、质疑与提前停止 | 玩家手册 5、当前 YAML 重岳 | `backend/app/engine/special_effects.py`, `backend/app/main.py`, `backend/app/engine/bot.py` | `backend/tests/test_chongyue_flow.py`, `backend/tests/test_chongyue_integration.py`, `frontend/e2e/acceptance/chongyue-flow.spec.ts` | `frontend/src/App.tsx`, `frontend/src/components/table/ChongyuePanel.tsx` | `frontend/src/data/rules.ts` |
| 开局继续翻至有色牌，万能牌保留在弃牌堆 | 玩家手册 2 | `backend/app/engine/command_handler.py` | `backend/tests/test_player_action_updates.py` | `frontend/src/App.tsx` | `frontend/src/data/rules.ts` |
| 无合法动作时每次点击只摸一张，直到可以出牌 | 玩家手册 3 | `backend/app/engine/command_handler.py` | `backend/tests/test_player_action_updates.py`, `backend/tests/test_uno_deck_and_game_end.py` | `frontend/src/App.tsx` | `frontend/src/data/rules.ts` |
| 普通回合与多牌响应 180 秒；新回合重置时限 | 玩家手册 7 | `backend/app/engine/runtime/deadlines.py`, `backend/app/engine/command_handler.py`, `backend/app/engine/special_effects.py` | `backend/tests/agent_runtime/test_extended_deadlines.py`, `backend/tests/test_audit_runtime_regressions.py` | `frontend/src/App.tsx` | `docs/PLAYER_MANUAL.md` |
| 多牌步骤自动切换模式与高亮候选牌 | 玩家手册 3 | `backend/app/engine/special_effects.py` | `frontend/e2e/acceptance/multi-card-guidance.spec.ts` | `frontend/src/App.tsx`, `frontend/src/hooks/game/useGameSelection.ts` | `docs/PLAYER_MANUAL.md` |
| 机器人每步延迟约 1.5 秒，状态变化取消旧动作 | 玩家手册 1 | `backend/app/main.py` | `backend/tests/test_bot_response_delay.py` | `frontend/src/App.tsx` | `docs/PLAYER_MANUAL.md` |

矩阵列出当前实现和现有测试入口，不表示所有规则组合已穷举。

