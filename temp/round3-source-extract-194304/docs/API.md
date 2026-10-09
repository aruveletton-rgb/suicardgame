# HTTP API

更新日期：2026-09-28。

后端是房间、身份、牌局、窗口与计时的权威来源。客户端按钮禁用和倒计时仅用于展示，不能替代服务端校验。

## 接口

```text
GET  /api/v1/health
POST /api/v1/rooms
POST /api/v1/rooms/{room_code}/join
POST /api/v1/rooms/{room_code}/reconnect
GET  /api/v1/rooms/{room_code}/state
POST /api/v1/rooms/{room_code}/commands
WS   /api/v1/rooms/{room_code}/ws
```

创建和加入请求可以提交稳定的内置头像 ID：

```json
{
  "nickname": "玩家",
  "avatar_id": "wang"
}
```

允许的头像 ID：`default`、`wang`、`ji`、`yu`、`yi`、`zuole`、`xi`、`nian`、`sui_xiang`、`shu`、`chongyue`、`ling`、`fuzhou`。

## 权威命令

HTTP 与已认证 WebSocket 使用同一命令模型：

```json
{
  "action_id": "client-generated-uuid",
  "room_id": "ABC123",
  "player_id": "player-id",
  "command_type": "PLAY_CARD",
  "payload": {},
  "game_id": "active-game-id",
  "game_epoch": 1,
  "expected_state_version": 12
}
```

支持的正式命令：

- 房间：`READY`、`START_GAME`、`RESET_ROOM`、`REMATCH`、`CLOSE_ROOM`。
- 回合：`PLAY_CARD`、`DRAW_CARD`、`DECLARE_UNO`、`CATCH_UNO`。
- 岁牌/窗口：`ACTIVATE_SPECIAL`、`RESPOND_TO_PROMPT`。
- 商店：`BUY_SHOP_GOOD`、`REFRESH_SHOP`。
- 暂停：`CONTINUE_WAITING`、`ABORT_GAME`（仅房主）。

`TEST_SET_STATE` 和 `TEST_OPEN_RESPONSE_WINDOW` 仅在 `TEST_MODE=1` 且数据目录位于系统临时目录下、使用受限测试前缀时可用；不得在生产环境启用。

`action_id` 在同一房间内幂等。服务端还使用 `game_id`、`game_epoch`、`state_version` 和 `prompt_id` 拒绝过期命令或旧计时回调。

## 房间与结果

- 房间容量为 2–5 人，第六人返回 `409 ROOM_FULL`。
- 所有在座玩家必须在线且 READY；房主才可 `START_GAME`。
- `REMATCH` 回到大厅并清除所有 READY，下一局必须重新准备。
- `ABORT_GAME` 进入结果阶段但不产生胜者；不能按剩余手牌数伪造胜者。

## 暂停与时限

- 普通回合：90 秒。
- 必选颜色、目标、多选、交付：30 秒。
- 可选左乐、规避、吃碰杠：15 秒。
- 质疑：10 秒。

普通回合或必选步骤到期后，服务端保留原步骤并进入暂停。房主可 `CONTINUE_WAITING`，为同一步骤生成新的时限/窗口代次；或 `ABORT_GAME` 中止本局。可选窗口到期视为放弃并由服务端推进。

## 快照边界

公开快照包含玩家座次、头像、在线/准备状态、牌数、公开牌面、当前行动人、`turn_deadline_at`、`pause_state`、过滤后的 `pending_action`、商店和结算信息。

私有快照额外包含本人手牌和本人可执行的窗口选项。服务端不会向全房广播其他玩家的手牌或合法牌 ID，也不会在快照中返回 reconnect token。

WebSocket 认证与事件格式见 `docs/WEBSOCKET_PROTOCOL.md`。
