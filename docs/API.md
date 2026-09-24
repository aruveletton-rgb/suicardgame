# API

日期：2026-06-15

## 已实现接口

```text
GET  /api/v1/health
POST /api/v1/rooms
POST /api/v1/rooms/{room_code}/join
POST /api/v1/rooms/{room_code}/reconnect
GET  /api/v1/rooms/{room_code}/state
POST /api/v1/rooms/{room_code}/commands
WS   /api/v1/rooms/{room_code}/ws
```

## HTTP 写命令模型

```json
{
  "action_id": "uuid",
  "room_id": "ABC123",
  "game_id": "...",
  "game_epoch": 1,
  "player_id": "...",
  "expected_state_version": 12,
  "command_type": "PLAY_CARD",
  "payload": {}
}
```

当前命令入口支持：

- `READY`
- `START_GAME`
- `RESET_ROOM`
- `REMATCH`
- `PLAY_CARD`

`action_id` 在同一房间内幂等。Reset 后旧 `game_id/game_epoch` 命令返回：

```json
{
  "detail": {
    "error": "STALE_GAME_COMMAND",
    "message": "该操作属于已经结束或重置的牌局"
  }
}
```

## WebSocket

连接：

```text
ws://host/api/v1/rooms/{room_code}/ws?player_id={player_id}
```

连接成功后服务器立即发送公开快照：

```json
{
  "event": "snapshot",
  "room_code": "ABC123",
  "state_version": 1,
  "state": {}
}
```

如果客户端已有当前 `session_id`，可连接：

```text
ws://host/api/v1/rooms/{room_code}/ws?player_id={player_id}&session_id={session_id}
```

服务器会先发送公开 `snapshot`，再只向该连接发送本人 `private_snapshot`。私密快照包含本人手牌：

```json
{
  "event": "private_snapshot",
  "room_code": "ABC123",
  "state_version": 1,
  "state": {},
  "you": {
    "player_id": "...",
    "session_id": "...",
    "hand": []
  }
}
```

客户端心跳：

```json
{"event": "ping"}
```

服务器返回：

```json
{"event": "pong", "state_version": 1}
```

客户端主动拉取状态：

```json
{"event": "get_state"}
```

服务器返回新的 `snapshot`。

客户端也可以在已连接 WebSocket 后认证私密视图：

```json
{
  "event": "authenticate",
  "player_id": "...",
  "session_id": "..."
}
```

认证成功返回 `private_snapshot`，失败返回：

```json
{"event": "error", "error": "AUTH_FAILED"}
```

客户端可通过 WebSocket 提交服务器权威命令：

```json
{
  "event": "command",
  "action_id": "uuid",
  "command_type": "READY",
  "payload": {"ready": true}
}
```

如果连接 URL 已包含 `player_id`，命令消息可以省略 `player_id`；否则必须在消息中提供。服务器先向发起连接返回：

```json
{
  "event": "command_result",
  "action_id": "uuid",
  "result": {}
}
```

如果命令修改了房间状态，服务器随后向同房间全部 WebSocket 连接广播：

```json
{
  "event": "state_patch",
  "room_code": "ABC123",
  "state_version": 2,
  "state": {}
}
```

`snapshot` 和 `state_patch` 当前都是完整公开快照形式，不是 JSON Patch 增量差异；它们不包含任何玩家完整手牌，只暴露 `hand_count`。

命令错误返回：

```json
{
  "event": "error",
  "error": "COMMAND_TYPE_REQUIRED",
  "message": "command_type is required",
  "action_id": "uuid"
}
```

## 目标但未实现接口

```text
GET  /api/v1/server-info
GET  /api/v1/rooms/{room_code}/summary
POST /api/v1/rooms/{room_code}/recover
GET  /api/v1/rooms/{room_code}/history
```

## 仍未完成

- 服务重启后的房间恢复。
- 一次性恢复码。
- 完整历史查询。
