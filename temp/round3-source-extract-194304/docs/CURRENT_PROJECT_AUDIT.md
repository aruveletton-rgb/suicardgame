# 当前旧项目只读审计

审计对象：`inputs/suicardgame-linux-server.zip` 解压到 `reference/legacy-src/suicardgame-linux-server`。旧项目仅作为证据和资源来源，不在旧状态机上继续打补丁。

## 关键结论

- 旧牌组不是经典 UNO 108 张：`backend/game/rules.py` 使用红、蓝、绿、黄、白五色，且数字范围与复制数按人数变化。
- 起手牌不是 7 张：`PLAYER_DECK_CONFIG` 对 2 到 6 人发 6 张，对 7 到 10 人发 5 张。
- 存在 `PenaltyStack` 和 `ensure_penalty_stack()`，`+2/+4` 可以累计，偏离本次要求的禁止叠加。
- Wild Draw Four 只作为可叠加惩罚牌处理，没有完整合法性检查和质疑流程。
- `backend/game/engine.py` 1192 行，`backend/game/special_cards.py` 794 行，`frontend/src/App.jsx` 414 行，`frontend/src/styles.css` 1312 行，职责明显混杂。
- `Room` 同时保存 `penalty_stack`、`pending_action`、`reaction_window`、`claim_window`、`challenge_window`，多个阻塞窗口并存且互相覆盖风险高。
- 望牌在 `apply_wang()` 中被实现成 `extra_actions: 1`，与卡面“持续控制到自己的回合开始”矛盾。
- 绩牌自动处理其他玩家同色牌，未按玩家逐个选择。
- 易牌旧实现未体现本回合多次执行。
- 余牌缺少每轮重新支付、颜色集合清理和从放弃者重启的完整模型。
- 年牌吃、碰、杠校验错误要求同色；旧代码还使用 `ming_gang` 等超出卡面要求的概念。
- 岁相翻牌到无色牌/岁牌、牌堆耗尽和 reveal 区归属没有严格建模。
- 坎诺特商店是 `DEFAULT_SHOP_ITEMS` 抽象技能商品，不是场上 8 张真实卡牌商品。
- README 声称有 `backend/tests/`，压缩包内实际没有测试目录。
- `Room` 与 `Game` 未清晰拆分，`reset_room()` 实际调用 `engine.reset_game()` 直接重新发牌开局，不是中止当前局回大厅。
- 缺少 Rematch、Reset 旧命令隔离、房间生命周期、超时默认动作和并发竞态测试。

## 可参考但不可继承的部分

- 旧项目有 FastAPI、WebSocket、JSON 快照、React/Vite 的基本方向，可以作为技术栈选择参考。
- 旧项目包含特殊牌 jpg 文件和一批原创 SVG 牌面生成思路，但白色牌和旧 manifest 不可沿用。

