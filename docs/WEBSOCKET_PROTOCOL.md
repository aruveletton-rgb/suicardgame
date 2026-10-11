# WebSocket 协议

更新日期：2026-09-28。

端点：

```text
/api/v1/rooms/{room_code}/ws
```

凭据不得放在 URL。连接后服务器先发送公开 `snapshot`；客户端随后发送认证消息：

```json
{
  "event": "authenticate",
  "player_id": "player-id",
  "session_id": "current-session-id"
}
```

认证成功后服务器发送该玩家的 `private_snapshot`。认证失败关闭连接或返回 `AUTH_FAILED`，未认证连接不能提交玩法命令。

## 客户端事件

心跳：

```json
{ "event": "ping" }
```

拉取最新公开状态：

```json
{ "event": "get_state" }
```

提交命令：

```json
{
  "event": "command",
  "action_id": "client-generated-uuid",
  "player_id": "player-id",
  "command_type": "RESPOND_TO_PROMPT",
  "payload": {
    "prompt_id": "prompt-id",
    "response": "pass"
  },
  "game_id": "active-game-id",
  "game_epoch": 1,
  "expected_state_version": 12
}
```

命令列表及 HTTP 等价入口见 `docs/API.md`。

## 服务端事件

- `pong`：心跳响应。
- `snapshot` / `state_patch`：当前完整公开状态，不是 JSON Patch。
- `private_snapshot`：公开状态加本人私有手牌/选项。
- `command_result`：命令的幂等结果。
- `error`：错误码、可选提示与对应 `action_id`。

已认证连接在状态变化后会收到新的私有快照，因此摸牌、出牌、交付、商店交换和罚摸能更新本人手牌。

## `pending_action`

```json
{
  "prompt_id": "prompt-id",
  "kind": "CHONGYUE_CHALLENGE",
  "source_player_id": "source-player-id",
  "status": "open",
  "resolution_policy": "sequential",
  "display_title": "重岳牌质疑",
  "display_message": "...",
  "created_at": 0,
  "deadline_at": 0,
  "required": false,
  "paused": false,
  "responder_count": 3,
  "responded_count": 0,
  "can_respond": true,
  "legal_responses": ["challenge", "pass"],
  "default_action": "pass",
  "resolution_reason": null,
  "effect": {}
}
```

- `can_respond`、`legal_responses` 和 `default_action` 按查看者过滤。
- `effect` 只包含公开字段；私有候选牌 ID 不会发送给其他玩家。
- `required=true` 的窗口超时后进入 `pause_state`，不会执行默认代选。
- 客户端倒计时归零后应等待服务端状态转换，不能自行推进牌局。

常见窗口：`SUI_REACTION`、`SUI_PLAYER_RESPONSE`、`CHONGYUE_CHALLENGE`、`GENERIC_RESPONSE_WINDOW`。Wild Draw Four 出牌后直接罚摸四张，不创建质疑窗口。

## 重岳逐人阶段

`effect.type=chongyue` 的新流程包含 `reveal`、`draw`、`challenge`、`source_check`、`source_draw` 阶段。`acting_player_id` 指向当前操作者，`reveal_order` 从使用者下一位起按出牌方向排列，使用者最后处理。尚未轮到的玩家不会提前补牌。

- 展示阶段提交 `RESPOND_TO_PROMPT`，`response=submit_cards`，`card_ids` 每种当前可提供的缺失颜色选一张。`required_color_count` 是本次所需数量。牌仍留在原手牌中。
- 补牌阶段提交同一命令，`response=draw_one`，一次只摸一张；重复颜色或无色牌也公开展示。当前已有缺失颜色的手牌时，必须先展示，不能绕过展示额外摸牌。
- 质疑阶段使用 `challenge` 或 `decline_challenge`；使用者是否合格在其补牌前判定。合格后展示并罚摸质疑者，失败后使用者补齐并停止剩余阶段。
- `displayed_cards`、`displayed_colors`、`drawn_until_four` 按玩家 ID 汇总实际已公开的卡面、颜色和补牌数量；`missing_colors` 描述当前阶段缺失颜色。未展示手牌和内部质疑判定字段不广播。
- 必选展示/补牌窗口限时 180 秒，超时暂停并保留步骤；可选质疑限时 10 秒，到期视为不质疑。
- 结算摘要保存在公开的 `special_state.chongyue_result`，仅含已展示牌、计数、质疑结果等公开信息；下一次发动会清除旧摘要。

旧快照中不含 `phase` 的重岳质疑窗口继续按其原有质疑状态完成，不补跑新展示阶段或重复摸牌。

## 隐私与恢复

- reconnect token 仅用于 HTTP reconnect，不通过 WebSocket 广播。
- 公共状态只含其他玩家 `hand_count`，不含完整手牌。
- 望控制链只向获授权玩家提供所需私有信息；场地牌不视为手牌。
- 重连、重启和旧命令通过 `game_id/game_epoch/state_version/prompt_id` 与窗口代次隔离，避免重复结算。
