# 负载测试报告

日期：2026-06-15

## 环境

- 服务器：`139.196.13.53`
- SSH 别名：`suicardgame-server`
- 用户：`twq`
- 规格：约 2 vCPU / 2 GiB RAM
- Conda 环境：`audio`
- Python：`3.11.15`
- Node：`v20.20.2`
- 临时服务：`127.0.0.1:8011`
- 未使用 sudo、Nginx、systemd、防火墙或公网端口变更。

## 当前版本

发布包：
```text
suicardgame-rebuild-20260615-010755.zip
SHA-256: c405b175d16711852411c2f9373bf5385712c4ceb52e4ce5267c4f4bc09f3f35
```

运行目录：
```text
/home/twq/suicardgame/releases/suicardgame-rebuild-20260615-010755
```

持久化目录：
```text
/home/twq/suicardgame/runtime/data/rooms
```

## 已通过实验

HTTP 并发加入：
```json
{
  "rooms_created_for_concurrent_join": 20,
  "players_per_room": 10,
  "error_count": 0,
  "requests_measured": 377,
  "latency_ms_p95": 24.76
}
```

WebSocket 广播：
```json
{
  "error_count": 0,
  "websocket_connections": 10,
  "join_state_patch_tested": true,
  "reset_state_patch_recipients": 10,
  "private_hand_leak_checked": true,
  "state_patch_ms_median": 6.73,
  "state_patch_ms_max": 8.53
}
```

WebSocket 命令：
```json
{
  "error_count": 0,
  "websocket_connections": 4,
  "websocket_commands_tested": ["READY", "START_GAME", "RESET_ROOM"],
  "websocket_validation_error_tested": true,
  "private_hand_leak_checked": true,
  "ws_command_result_ms_p95": 1.60
}
```

重连和私密快照：
```json
{
  "error_count": 0,
  "http_requests_measured": 128,
  "http_latency_ms_p95": 26.00,
  "ws_private_snapshot_connections": 1,
  "ws_private_snapshot_ms_p95": 27.35,
  "reconnect_tested": true,
  "bad_token_tested": true,
  "authenticate_event_tested": true,
  "private_hand_leak_checked": true
}
```

服务重启恢复：
```json
{
  "room_code": "LC2JKA",
  "old_pid": 334990,
  "new_pid": 335139,
  "phase_after_restart": "IN_GAME",
  "snapshot_exists": true,
  "host_private_hand_count": 7,
  "public_hand_leak": false,
  "http_p95_ms": 5.92,
  "rss_kib": 56076,
  "error_count": 0
}
```

## 结论

服务器上的 HTTP 并发加入、基础 WebSocket、公开快照、`ping/pong`、`state_patch`、WebSocket 命令提交、HTTP reconnect、WebSocket 私密快照、Reset 清理、旧命令隔离，以及服务重启后的房间恢复实验通过。

这仍不是完整 10 人 WebSocket 自动对局压测。当前仍未覆盖：

- 随机断线重连和离线宽限默认动作。
- Rematch 连续多局。
- 全部特殊牌交互。
- 望牌控制期恢复。
- 1000 局机器人模拟。
- 完整移动端和 PC 人工 UX 检查。
