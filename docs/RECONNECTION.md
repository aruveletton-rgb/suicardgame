# 断线重连

日期：2026-06-15

## 当前已实现

玩家加入时服务器生成：
- `player_id`
- `reconnect_token`
- `session_id`
- 座位、昵称和房间归属

公共状态只包含：
- `player_id`
- `nickname`
- `seat_index`
- `online`
- `is_host`
- `ready`
- `hand_count`

公共状态不包含：
- `reconnect_token`
- `session_id`
- 完整手牌

## 持久化

后端使用原子 JSON 快照保存 `Room`、当前 `Game`、玩家会话、手牌、牌堆、弃牌堆、商店、prompt、`state_version` 和已处理 `action_id`。

数据目录由环境变量控制：
```text
SUICARDGAME_DATA_DIR
```

服务器当前目录：
```text
/home/twq/suicardgame/runtime/data/rooms
```

服务重启后会从该目录加载房间快照。已验证：开局后的双人房在真实进程重启后仍保持 `IN_GAME`，玩家可用原 `reconnect_token` 恢复并拿到本人 7 张手牌。

## HTTP 重连

接口：
```text
POST /api/v1/rooms/{room_code}/reconnect
```

请求：
```json
{
  "player_id": "...",
  "reconnect_token": "..."
}
```

成功后：

- 校验 `player_id + reconnect_token`。
- 将玩家标记为在线。
- 轮换新的 `session_id`。
- 增加房间 `state_version`。
- 保存房间快照。
- 返回本人 `private_snapshot`。
- 向同房间 WebSocket 广播公开 `state_patch`。

响应不会返回 `reconnect_token`。

失败返回：
```json
{
  "detail": {
    "error": "RECONNECT_FAILED",
    "message": "reconnect failed"
  }
}
```

## WebSocket 私密快照

连接 WebSocket 时不在 URL 携带凭据：
```text
WS /api/v1/rooms/{room_code}/ws
```

服务器发送：

1. 公开 `snapshot`
2. 客户端发送 `authenticate`
3. 仅发给认证连接的 `private_snapshot`

连接后认证：
```json
{
  "event": "authenticate",
  "player_id": "...",
  "session_id": "..."
}
```

认证成功返回 `private_snapshot`，失败时连接以 `1008` 关闭。认证前发送游戏命令会返回 `AUTH_REQUIRED`。

`private_snapshot.you.hand` 包含本人完整手牌，每张牌包含：
- `card_id`
- `category`
- `kind`
- `color`
- `value`
- `asset_key`

## 断开处理

已认证的 WebSocket 断开时，如果该连接仍对应玩家当前 `session_id`：
- 玩家被标记为离线。
- 房间 `state_version` 增加。
- 保存房间快照。
- 同房间收到公开 `state_patch`。

如果玩家已经通过 reconnect 获得新 `session_id`，旧连接断开不会覆盖新会话状态。

## 仍未完成

- 一次性换设备恢复码。
- 同一玩家多连接的更细粒度连接计数。
- 前端自动保存和使用 `reconnect_token/session_id`。
- 断线倒计时和离线宽限默认动作。
