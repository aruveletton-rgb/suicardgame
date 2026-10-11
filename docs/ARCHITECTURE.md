# 架构

## 技术栈

- Python 3.11+
- FastAPI
- Pydantic
- 原子 JSON 快照
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
  engine/special_effects.py
  engine/bot.py
  engine/reshuffle.py
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

## 当前运行能力

- 房间命令使用每房间 `threading.RLock` 串行处理；连接管理使用 `asyncio.Lock`。部署保持单进程、单 worker。
- WebSocket 会话校验、公共快照和按玩家过滤的私密快照；HTTP 命令同样校验会话。
- 当前八种岁牌和坎诺特场地商店的结算、响应队列与隐私过滤。当前规则以 `PLAYER_MANUAL.md` 为准，已移除的牌种不在牌组中。
- JSON 快照恢复手牌、prompt、暂停、回合时限和幂等缓存。可选响应超时默认放弃；普通回合和必选步骤超时暂停。
- 机器人通过权威命令路径行动；模拟报告记录原始命令拒绝、兜底成功和兜底拒绝。指定 seed 时初始洗牌和后续重洗牌可复现。
- pytest 规则、鉴权、隐私、恢复与并发测试；Playwright 桌面、手机和生产构建验收。

## 验证边界

现有测试不代表所有岁牌组合或生产负载已覆盖。多 worker 部署和生产负载容量尚未验证。

