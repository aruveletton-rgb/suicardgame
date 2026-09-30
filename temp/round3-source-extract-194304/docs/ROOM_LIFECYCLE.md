# 房间生命周期

Room 是持续存在的大厅和成员集合。Game 是 Room 中的一局牌。

当前实现：

- Room 可从 `LOBBY` 开始一局进入 `IN_GAME`。
- `RESET_ROOM` 中止当前 Game，清空手牌，回到 `LOBBY`。
- Reset 会记录被中止局的 `game_id`、`game_epoch` 和状态。
- 旧 `game_id/game_epoch` 命令会被拒绝。

待实现：

- `STARTING` 阶段。
- 正常结算进入 `ROUND_RESULT` 后 Rematch。
- 空房间延迟清理。
- 房主离开自动转让。
- Close 房间并失效邀请和 token。

