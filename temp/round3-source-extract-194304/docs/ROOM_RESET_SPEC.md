# Reset 规格

Reset 用于中止当前局并恢复干净大厅，不等于 Rematch，也不等于 Close。

已实现：

- 只有房主可 Reset。
- 若有活动 Game，标记为 `ABORTED_BY_ROOM_RESET` 并写入历史。
- 清空所有玩家手牌。
- 清空准备状态。
- 清空 `active_game`，Room 回到 `LOBBY`。
- 增加 `room_version` 和 `state_version`。
- 旧局命令返回 `STALE_GAME_COMMAND`。

待实现：

- 取消真实后台计时任务。
- 通知客户端关闭旧弹窗。
- Reset 与出牌、重连、关闭房间的锁内事务裁决。

