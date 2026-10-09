# suicardgame v1.5

`suicardgame` 是一个基于 UNO 规则、加入岁牌特殊规则的多人卡牌游戏。后端负责房间、牌局和规则结算，前端通过 HTTP 与 WebSocket 同步游戏状态。

## 功能

- 2--5 人房间，支持真人与机器人混合对战。
- 房主可以在大厅增减机器人；机器人会自动准备并完成回合。
- 普通 UNO 出牌、摸牌、UNO 声明、+4 质疑、岁牌响应和商店操作。
- 机器人支持普通出牌、岁牌响应、特殊牌目标选择和超时默认响应。
- 断线重连、房间准备、暂停恢复、回合倒计时和结算再来一局。
- 中文规则提示、手牌合法性高亮以及移动端布局。

## 目录

```text
backend/                 FastAPI 后端、领域模型、规则引擎和测试
frontend/src/            React/TypeScript 客户端
frontend/e2e/            Playwright 端到端流程
backend/rules/           特殊牌规则数据
docs/                    协议、规则和玩家手册
scripts/                 本地构建与验证脚本
```

## 本地开发

需要 Python、Node.js 和 npm。先安装依赖，再分别启动后端和前端：

```powershell
$env:SUICARDGAME_DATA_DIR = Join-Path $env:TEMP "suicardgame-dev-rooms"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8012
```

```powershell
$env:VITE_BACKEND_TARGET = "http://127.0.0.1:8012"
npm --prefix frontend run dev -- --port 5174
```

也可以先构建客户端，再用 Vite preview 查看构建结果：

```powershell
npm --prefix frontend run build
npm --prefix frontend run preview -- --port 8080
```

测试数据应使用独立的 `SUICARDGAME_DATA_DIR`，不要把真实运行数据目录用于测试。不要提交 `.env`、令牌、运行房间 JSON 或本地证据文件。

## 游戏操作

完整的玩家操作和岁牌规则见 [docs/PLAYER_MANUAL.md](docs/PLAYER_MANUAL.md)。机器人对战的基本流程：

1. 创建房间后，房主在大厅增加机器人数量。
2. 等待机器人自动准备，真人玩家点击“准备”。
3. 房主开始游戏；机器人会在自己的回合自动行动。
4. 需要响应岁牌或 +4 时，按界面提示选择高亮手牌；响应超时会按规则处理。

## 验证

```powershell
python -m pytest -q backend/tests
python scripts/validate-card-assets.py
npm --prefix frontend run build
```

Playwright 测试：

```powershell
cd frontend
npx playwright test --config=playwright.config.ts
```

端到端脚本只通过可见 UI 操作，不读取玩家令牌或后端私有状态。需要多人本地流程时，先启动后端和前端，再打开多个浏览器上下文加入同一房间。

## 相关文档

- [玩家手册](docs/PLAYER_MANUAL.md)
- [岁牌规则](docs/SPECIAL_CARD_RULES_FROM_CARDS_ZIP.md)
- [WebSocket 协议](docs/WEBSOCKET_PROTOCOL.md)

## 版本

当前版本：`suicardgame-v1.5`。
