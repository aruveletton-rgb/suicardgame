# 规则追踪矩阵

| 规则 | 来源 | 后端文件 | 测试 | 前端文件 | 规则页 |
|---|---|---|---|---|---|
| 经典 108 张四色牌组 | 本提示词 4.1 | `backend/app/domain/cards.py` | `backend/tests/test_cards.py` | `frontend/src/components/CardView.tsx` | `frontend/src/data/rules.ts` |
| 每人起手 7 张 | 本提示词 4.2 | `backend/app/engine/command_handler.py` | `backend/tests/test_room_lifecycle.py` | `frontend/src/App.tsx` | 待扩展 |
| 禁止白色牌 | 本提示词 4.1 | `backend/app/domain/cards.py` | `backend/tests/test_cards.py` | 资产 manifest | 待扩展 |
| Wild Draw Four 合法性 | 本提示词 4.3/4.4 | `backend/app/rules/uno.py` | `backend/tests/test_uno_rules.py` | 待接入 | 待扩展 |
| 禁止惩罚叠加 | 本提示词 4.5 | `backend/app/rules/uno.py` | `backend/tests/test_uno_rules.py` | 待接入 | 待扩展 |
| 特殊牌数量配置 | 本提示词 7 | `backend/app/domain/cards.py` | `backend/tests/test_cards.py` | `frontend/src/data/rules.ts` | 待扩展 |
| 坎诺特为场地 NPC | 卡面 + 本提示词 6.13 | `backend/app/domain/cards.py`, `backend/app/engine/command_handler.py` | `backend/tests/test_cards.py`, `backend/tests/test_room_lifecycle.py` | `frontend/src/App.tsx` | `frontend/src/data/rules.ts` |
| Reset 回大厅并隔离旧局 | 本提示词 10.5 | `backend/app/engine/command_handler.py` | `backend/tests/test_room_lifecycle.py` | `frontend/src/App.tsx` | 待扩展 |
| 每张实体牌唯一位置 | 本提示词 8.3 | `backend/app/engine/invariants.py` | `backend/tests/test_invariants.py` | 不适用 | 架构文档 |
| 特殊牌完整结算 | 本提示词 6 | `backend/app/rules/sui/catalog.py` 规格已录入，结算待实现 | 待补 | `frontend/src/data/rules.ts` | 待扩展 |

