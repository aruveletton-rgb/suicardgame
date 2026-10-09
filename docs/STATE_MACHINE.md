# 状态机

Room 生命周期：

```text
LOBBY -> STARTING -> IN_GAME -> ROUND_RESULT -> LOBBY
                         \-> RESETTING -> LOBBY
任意允许阶段 -> CLOSED
```

当前代码已实现 `LOBBY`、`IN_GAME`、`ROUND_RESULT` 的基础入口，以及 `RESET_ROOM` 回到 `LOBBY`。

Game 阶段计划：

```text
TURN_START
TURN_MAIN
DRAWN_CARD_DECISION
UNO_WINDOW
SUI_REACTION
SUI_PLAYER_RESPONSE
CHONGYUE_CHALLENGE
TURN_END
```

所有等待输入必须收敛为一个 `Prompt`，包含 `prompt_id`、来源、响应者、合法响应、创建时间、截止时间、默认动作和 `state_version`。

