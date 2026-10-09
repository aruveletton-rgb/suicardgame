# SPECIAL_CARD_RULES_FROM_CARDS_ZIP

> 历史卡面资料，仅用于追溯来源。当前发行版本不再使用绩牌、年牌、岁相牌、符咒牌或有岁质疑；坎诺特商店仍保留。

- Source: `cards.zip` (local source archive)
- Extracted local review directory: not part of the repository
- Review note: rules below were transcribed from the 14 jpg images in `cards.zip`. One image is a global/base-rule card, and 13 images are playable special/field cards.
- UNCERTAIN policy: no rule below is intentionally inferred from backend implementation; when timing or conflict resolution is not explicitly present on the card, the field is marked as `UNCERTAIN` or `not specified by card image`.

## Global Extra Rules Image

Source asset: `8528700881491428f2e83d277561869d.jpg`

1. When another player uses a “岁牌”, you may discard a “岁牌” with higher rank on your own turn to avoid being selected/affected by that Sui card.
2. After a player ends their turn, other players may shout “有岁!” to question whether that player has unused Sui cards in hand. If the questioned player has unused Sui cards, that player draws 4 cards and hands the Sui card to the challenger. If not, the challenger draws 4 cards.

## Special / Field Cards

### 望牌

- id: `wang`
- source_asset: `15aefb709c02084fbf08600c51e42d85.jpg`
- timing: immediately when another player cannot play a legal/reasonable card.
- effect: inspect that player's hand and control that player to play the game. Your own hand is also considered available as that player's hand. Then continue controlling the next player(s) until your own turn begins.
- card clarifications: “cannot play legal card” means no card matching current color or number in normal play. Most other Sui effects count as display/discard, not play. While controlling another player, the game is treated as that player playing; category-use restrictions do not apply, and the controller may choose not to play.

### 绩牌

- id: `ji`
- source_asset: `1da5cef571c0302eb77b09e1fe9bbe96.jpg`
- timing: on your own turn.
- effect: declare one color. Other players, in play order, may discard any number of cards of that color. Then you may discard no more than the total number of discarded cards of that color.

### 余牌

- id: `yu`
- source_asset: `23db64326534b6478c57bae78d1c1590.jpg`
- timing: on your own turn.
- effect: discard four cards with all different colors. Then other players in order each discard one card whose color has not appeared earlier in this effect round, excluding the user. If a player chooses not to discard, the user may choose to restart this card effect from that player by paying another four different-color cards. This can repeat until the user chooses not to restart or all players have discarded successfully.

### 易牌

- id: `yi`
- source_asset: `23f1f0c5d35242bc5a52bba759946770.jpg`
- timing: on your own turn.
- effect: discard two number cards whose values sum to 8 at the same time. Other players, in order, each draw one card. This action may be repeated multiple times in the same turn.

### 左乐牌

- id: `zuole`
- source_asset: `2f42240353fbe94ad44e1ee11070299b.jpg`
- timing: when anyone uses a Sui card.
- effect: choose one player, including yourself. During this turn, that Sui card effect is ineffective against the chosen player.

### 夕牌

- id: `xi`
- source_asset: `3e25cb360344c2f96a7120b0bdc36335.jpg`
- timing: when you are passively required to provide/use a card.
- effect: this card may be treated as any one card being required by the passive demand. After it is used, immediately discard this card.
- clarification: “use” here means any card-game action including discard, play, use, and reveal, not only active card play.

### 年牌

- id: `nian`
- source_asset: `3f72b366c71fa69b00332f2787dc2079.jpg`
- timing: when a chance satisfying Chi/Peng/Gang rules appears on the table.
- effect: immediately shout “吃”, “碰”, or “杠” and enable the corresponding rules for this game.
- long-running rules added to the game:
  - 摸: every player whose turn does not begin via Chi/Peng/Gang draws one card at turn start and discards one card of any color at turn end.
  - 吃: after the previous player’s turn ends, you may discard two cards that form a numeric sequence with the previous player’s played card.
  - 碰: if two cards in your hand match the number of another player’s played card, you may discard those two cards and immediately enter your turn. The draw phase should be skipped.
  - 杠: if three cards in your hand match the number of another player’s played card, you may discard those three cards and immediately enter your turn.

### 岁相牌

- id: `sui_xiang`
- source_asset: `55c25e3116be272c57ed9a955bafcd73.jpg`
- timing: when seen by any player.
- effect: the first player who observed it flips the top card of the deck. Then players in order discard one card with the same color as the flipped card, otherwise draw four cards. If the flipped card is not colored, flip again until a colored card appears.

### 黍牌

- id: `shu`
- source_asset: `941e81d9c480f062462aed1364e55ad1.jpg`
- timing: on your own turn, when one color count in your hand is greater than or equal to the number of other players.
- effect: distribute cards of that color evenly to the other players. Any remainder cards are given to one of the players who currently has the fewest cards.

### 重岳牌

- id: `chongyue`
- source_asset: `9bf6f1118300add4e001671f90641b5d.jpg`
- timing: on your own turn.
- effect: in current play order, every player displays four hand cards of different colors. If a player lacks enough colors, they draw cards and display drawn cards until all colors are complete. Other players may question you after their own display phase. If you pass the challenge, the challenger draws 4 cards. If you fail, you also draw until colors are complete, and this Sui effect immediately stops resolving.

### 令牌

- id: `ling`
- source_asset: `a096ad301444ccefec6871995adafdef.jpg`
- timing: on your own turn.
- effect: determine the current maximum hand count among all players. All players draw until their hand count reaches that maximum. The user also draws if below the maximum. If the user already has the maximum, the user does not draw.

### 坎诺特牌

- id: `cannot`
- source_asset: `ddc008e08c2dc031c8a7f115a3832c43.jpg`
- timing: field NPC, placed before the game starts.
- effect: before the game starts, place this card on the field and place 8 cards around it as “goods”. Each turn, a player may discard one colored card and take one good with the same color or same number. A player may discard any card to take a non-colored good. A player may refresh the shop once at any time during their own turn, replacing the 8 goods.

### 符咒牌

- id: `fuzhou`
- source_asset: `df61e38b7181b20ff352318a5f70a267.jpg`
- timing: immediately when drawn by a player.
- effect: all players, in order, may give you one hand card. Then discard the Fuzhou card.

## Project Rule Acceptance Notes

The following notes are the project's explicit rule choices for source-image timing that is ambiguous or would otherwise create nested unresolved prompts in the current realtime engine.

### `wang` - CONSERVATIVE_ACCEPTED

- Source rule: the controller may inspect/control a blocked player and continue controlling following players until the controller's own turn begins.
- Project rule: Wang can control normal number/action/wild plays and pass decisions. It intentionally rejects Sui, field cards, and Wild Draw Four during controlled play because those cards create nested target/challenge prompt chains inside an already active control prompt.
- Impact: control timing, Reverse, Skip, Draw Two, and pass progression continue to work; nested special-card chains are blocked instead of deadlocking.
- Test coverage: `backend/tests/test_wang_exact_control.py`.

### `zuole` - CONSERVATIVE_ACCEPTED

- Source rule: choose one player to be unaffected by the current Sui card for this turn.
- Project rule: Zuole applies to prompt-based Sui effects that track `immune_player_ids`.
- Impact: immunity is serializable and scoped to the current Sui prompt; it does not create a second global interrupt queue.
- Test coverage: `backend/tests/test_special_card_resolvers.py` and `backend/tests/test_special_card_exactness_matrix.py`.

### `xi` - CONSERVATIVE_ACCEPTED

- Source rule: Xi can be treated as a required card when passively asked to provide/use a card.
- Project rule: Xi is exposed only in passive prompts whose `legal_responses` include `use_xi`, such as Ji, Yu, and Sui Xiang response windows.
- Impact: Xi cannot be used as a universal replacement for optional shop payment or Fuzhou gift choices.
- Test coverage: `backend/tests/test_special_card_resolvers.py` and `backend/tests/test_special_card_exactness_matrix.py`.

### `fuzhou` - CONSERVATIVE_ACCEPTED

- Source rule: Fuzhou triggers immediately when drawn.
- Project rule: the normal path is still on-draw. Hand activation is also accepted as a test/admin equivalent that opens the same gift window and then discards Fuzhou.
- Impact: draw-trigger behavior is preserved while deterministic tests and frontend manual validation can exercise the same resolver.
- Test coverage: `backend/tests/test_special_card_resolvers.py` and `backend/tests/test_special_card_exactness_matrix.py`.
