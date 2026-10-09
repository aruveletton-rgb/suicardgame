# 测试报告

日期：2026-06-15

## 本地测试

命令：
```text
python -m pytest -q backend/tests
python scripts/validate-card-assets.py
npm.cmd run build
```

结果：
- 后端测试：`22 passed, 1 warning`
- 牌面资源校验：`validated 68 assets`
- 前端生产构建：通过

新增覆盖：
- 原子 JSON 房间快照生成。
- 清空内存后从快照恢复已开局房间。
- 恢复后公共状态仍只暴露 `hand_count`。
- 恢复后 HTTP reconnect 可返回本人 7 张私有手牌。
- WebSocket 命令结算后的状态会被持久化。
- `pytest.ini` 将临时目录固定为 `.pytest_tmp`，绕过本机默认临时目录权限问题。

仍覆盖：
- 经典 108 张四色 UNO 基础牌组。
- 无白色普通牌。
- 特殊牌数量配置。
- 坎诺特为场地牌，商店展示 8 张真实商品牌。
- 每人起手 7 张。
- Reset 回到大厅并清空手牌、准备状态和活动 Game。
- Reset 后旧 `game_id/game_epoch` 命令返回 `STALE_GAME_COMMAND`。
- `action_id` 幂等。
- 普通 UNO 出牌匹配与 Wild Draw Four 基础合法性判断。
- 卡牌唯一位置不变量。
- HTTP `/join` 并发加入不会分配重复座位。
- WebSocket `snapshot`、`ping/pong`、`state_patch`、命令提交和结构化错误。
- HTTP reconnect 与 WebSocket `private_snapshot` 不泄露其他玩家手牌。

## 服务器测试

目标：`suicardgame-server`，即 `twq@139.196.13.53`

当前运行版本：
```text
/home/twq/suicardgame/releases/suicardgame-rebuild-20260615-010755
```

发布包：
```text
suicardgame-rebuild-20260615-010755.zip
SHA-256: c405b175d16711852411c2f9373bf5385712c4ceb52e4ce5267c4f4bc09f3f35
```

服务器构建和测试：
- SHA-256 校验：通过。
- 后端测试：`22 passed in 1.16s`。
- 前端依赖安装与生产构建：通过。
- 健康检查：`{"status":"ok"}`。
- 临时服务：`127.0.0.1:8011`。

重启恢复实验：
```json
{
  "room_code": "LC2JKA",
  "old_pid": 334990,
  "new_pid": 335139,
  "phase_after_restart": "IN_GAME",
  "game_epoch": 1,
  "snapshot_exists": true,
  "host_private_hand_count": 7,
  "public_hand_leak": false,
  "http_p95_ms": 5.92,
  "rss_kib": 56076,
  "error_count": 0
}
```

发现并修复的部署问题：
- 首次重启恢复实验发现 `conda run` 包装进程被写入 pidfile，真实监听 8011 的旧 Python 进程仍在运行。
- 因旧服务未带 `SUICARDGAME_DATA_DIR`，快照写入旧 release 内的默认 `data/rooms`。
- 修正为按端口反查真实监听 PID，并用 `/home/twq/miniconda3/envs/audio/bin/python` 直接启动新 release。

## 未完成 / 未覆盖

- 完整特殊牌效果仍是规则骨架级覆盖，尚未逐牌完整实现。
- 一次性换设备恢复码未完成。
- 同一玩家多连接的更细粒度连接计数未完成。
- 前端自动保存和使用 `reconnect_token/session_id` 未完成。
- 断线倒计时和离线宽限默认动作未完成。
- Hypothesis 属性测试未完成。
- 1000 局机器人模拟未完成。
- Playwright E2E 与完整移动端/PC UX 复测未完成。
