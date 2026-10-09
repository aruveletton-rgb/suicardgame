# 架构

## 技术栈

- Python 3.11+
- FastAPI
- Pydantic
- 原子 JSON 快照或 SQLite
- React + Vite + TypeScript
- pytest + Hypothesis
- 单进程、单 worker、每房间一个锁

## 当前目录

```text
backend/app/
  main.py
  domain/cards.py
  domain/room.py
  rules/uno.py
  rules/sui/catalog.py
  engine/command_handler.py
  engine/invariants.py
  repositories/json_store.py
frontend/src/
  App.tsx
  components/CardView.tsx
  data/rules.ts
scripts/
  generate-card-assets.py
  validate-card-assets.py
```

## 权威边界

后端是唯一规则执行者。前端只展示状态和提交命令，不自行结算。

## 已实现基础

- 经典牌组和特殊牌配置。
- Room/Game 分离的数据模型。
- `action_id` 幂等缓存。
- `game_id/game_epoch` 旧命令拒绝。
- Reset 中止局并回大厅。
- 卡牌唯一位置不变量。

## 待实现

- 每房间 `asyncio.Lock`。
- 完整 WebSocket 私密事件。
- 完整特殊牌效果队列。
- 持久化恢复 prompt 和超时默认动作。
- 机器人模拟、E2E 和负载测试。

