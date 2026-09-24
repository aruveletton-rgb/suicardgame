# WEBSOCKET_PROTOCOL

Endpoint:

```text
/api/v1/rooms/{room_code}/ws?player_id={player_id}&session_id={session_id}
```

The backend first sends a public `snapshot`. If `player_id` and `session_id` authenticate, it also sends a player-scoped `private_snapshot`.

## Client To Server

### ping

```json
{ "event": "ping" }
```

Response:

```json
{ "event": "pong", "state_version": 12 }
```

### get_state

```json
{ "event": "get_state" }
```

Response: public `snapshot`.

### authenticate

```json
{
  "event": "authenticate",
  "player_id": "player-id",
  "session_id": "current-session-id"
}
```

Response: `private_snapshot` on success, `error` on failure.

### command

```json
{
  "event": "command",
  "action_id": "client-generated-id",
  "player_id": "player-id",
  "command_type": "PLAY_CARD",
  "payload": {},
  "game_id": "active-game-id",
  "game_epoch": 1,
  "expected_state_version": 12
}
```

Supported gameplay command types:

- `READY`
- `START_GAME`
- `RESET_ROOM`
- `REMATCH`
- `PLAY_CARD`
- `DRAW_CARD`
- `RESPOND_TO_PROMPT`
- `DECLARE_UNO`
- `CATCH_UNO`
- `ACTIVATE_SPECIAL`
- `BUY_SHOP_GOOD`
- `REFRESH_SHOP`
- `TEST_SET_STATE` only when `TEST_MODE=1`

## Server To Client

### snapshot / state_patch

Public state only. It includes room phase, player public metadata, hand counts, active game metadata, top discard, shop goods, field card, reveal area, UNO public state, special state, and pending action summary.

It must not include any player's private hand.

### private_snapshot

Player-scoped state. It includes:

- the same public room state;
- `you.hand`;
- `you.uno.must_declare`;
- `you.uno.can_catch_player_id`.

It must not include reconnect token.

Authenticated WebSocket connections receive a fresh `private_snapshot` after each broadcast so hand changes are visible after draw, play, gift, shop, and penalty actions.

### command_result

```json
{
  "event": "command_result",
  "action_id": "client-generated-id",
  "result": {
    "ok": true,
    "state_version": 13
  }
}
```

### error

```json
{
  "event": "error",
  "error": "ILLEGAL_PLAY",
  "message": "optional user-facing message",
  "action_id": "client-generated-id"
}
```

## Pending Action Shape

Public pending action:

```json
{
  "prompt_id": "prompt-id",
  "kind": "WILD_DRAW_FOUR_CHALLENGE",
  "source_player_id": "source-player-id",
  "responder_ids": ["target-player-id"],
  "legal_responses": ["challenge", "decline_challenge"],
  "default_action": "decline_challenge",
  "effect": {
    "type": "wild_draw_four_challenge"
  }
}
```

The public `effect` field is deliberately filtered. It must not include private card ids from hidden hands.

## Special Card Interactions

Special cards use `ACTIVATE_SPECIAL` and `RESPOND_TO_PROMPT`.

Common payload fields:

- `card_id`
- `chosen_color`
- `target_player_id`
- `pair_card_ids`
- `payment_card_ids`
- `card_ids`
- `response`

Response values include:

- `challenge`
- `decline_challenge`
- `submit_cards`
- `pass`
- `decline`
- `restart`
- `stop`
- `use_xi`
- `give_card`
- `control_play`
- `control_pass`
- `discard_card`
- `chi`
- `peng`
- `gang`

Current prompt kinds:

- `WILD_DRAW_FOUR_CHALLENGE`: `challenge` or `decline_challenge`.
- `SUI_PLAYER_RESPONSE`: shared prompt kind for Ji/Yu/Sui Xiang/Wang/Fuzhou card effects.
- `CHONGYUE_CHALLENGE`: `challenge` or `decline_challenge`; public effect fields include `displayed_colors` and `drawn_until_four`.
- `NIAN_TURN_END_DISCARD`: `discard_card` with `card_id`; opened after a Nian-enabled player completes a turn action.
- `NIAN_CLAIM_WINDOW`: `chi`, `peng`, `gang`, or `pass`; claim responses include `card_ids`.

Public effect fields may include `type`, `source_card_kind`, `source_player_id`, `target_player_id`, `controlled_player_id`, `chosen_color`, `required_color`, `phase`, `responder_index`, `total_discarded`, `used_colors`, `displayed_colors`, `drawn_until_four`, `last_played`, `advance_steps`, `seen_event_id`, `seen_source`, and `immune_player_ids`.

The server must not expose hidden hand contents through public prompt effects. Card ids for selected hand cards are sent only by the acting private client in command payloads.

## Reconnect

Reconnect is HTTP:

```text
POST /api/v1/rooms/{room_code}/reconnect
```

The backend validates `player_id` and `reconnect_token`, rotates `session_id`, and returns a `private_snapshot`. Reconnect tokens are never broadcast.

## Security Notes

- Do not log reconnect tokens.
- Do not log session tokens.
- Do not expose `runtime/data/rooms` JSON bodies.
- Do not include private hand card ids in public `snapshot` or `state_patch`.
