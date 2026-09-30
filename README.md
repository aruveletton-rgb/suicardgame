# suicardgame

本文档使用 UTF-8 编码保存。

`suicardgame` 是一个多人联机卡牌项目：以经典 UNO 为基础规则，并加入 `cards.zip` 中整理出的岁牌特殊牌/场地牌规则。后端负责权威状态结算，前端通过 HTTP API 与 WebSocket 进行多人房间同步。

## 当前状态

- 本仓库包含 FastAPI 单 worker 权威后端与 React/TypeScript/Vite 客户端。
- 支持 2–5 人房间；所有在座玩家在线并 READY 后才能开局，第六人由服务端拒绝。
- 当前修复版本包含 90/30/15/10 秒服务端时限、必选超时暂停、岁牌规则窗口、三种牌桌布局、头像/邀请/图鉴与基础结算。
- 本轮只在隔离本地工作区实现和验证，没有部署、重启或修改任何线上 systemd/Nginx/防火墙。
- README 中不再把历史公网地址或服务器路径描述为当前已验证状态；部署模板位于 `deploy_templates/`，应用前必须单独审核。

## 项目结构

```text
suicardgame/
├── backend/
│   ├── app/main.py                 # FastAPI HTTP 与 WebSocket 入口
│   ├── app/domain/                 # 卡牌、房间、玩家、牌局状态模型
│   ├── app/engine/                 # 命令处理、UNO 与特殊牌结算
│   ├── app/rules/uno.py            # UNO 出牌合法性辅助逻辑
│   └── tests/                      # 后端自动化测试
├── backend/rules/special_cards.yaml # cards.zip 结构化特殊牌规则
├── frontend/
│   ├── src/App.tsx                 # 真实 API/WebSocket 多人客户端
│   ├── e2e/                        # Playwright 多人流程测试
│   └── dist/                       # 前端生产构建产物
├── scripts/
│   ├── start_backend.sh            # 本机后端启动脚本
│   ├── start_frontend_dev.sh       # Vite 开发启动脚本
│   ├── build_frontend.sh           # 前端生产构建脚本
│   ├── run_tests.sh                # 回归验证脚本
│   └── smoke_backend.sh            # 临时后端 health smoke
├── docs/
│   ├── SPECIAL_CARD_RULES_FROM_CARDS_ZIP.md
│   ├── WEBSOCKET_PROTOCOL.md
│   └── PRODUCTION_DEPLOYMENT_PLAN.md
├── deploy_templates/               # systemd / Nginx 模板，仅作参考
├── audit/                          # 审计与部署记录，不应对公网暴露
├── artifacts/acceptance/           # 本轮脱敏验收证据
└── runtime/data/rooms              # 运行房间数据，禁止打印或公开
```

## 本地启动

本轮验证环境为 Python 3.13.5、Node.js 25.9.0。先安装仓库声明的 Python 与前端依赖，然后使用独立数据目录启动后端；不要指向真实 `runtime/data/rooms` 做测试。

PowerShell（必须使用两个独立终端；环境变量不会跨终端继承）：

后端终端：

```powershell
Set-Location E:\suicardgame
$env:SUICARDGAME_DATA_DIR = Join-Path $env:TEMP "suicardgame-dev-rooms"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8122
```

前端终端：

```powershell
Set-Location E:\suicardgame
$env:VITE_BACKEND_TARGET = "http://127.0.0.1:8122"
npm --prefix frontend run dev -- --port 5174
```

Bash（两个终端分别执行后端和前端命令）：

```bash
export SUICARDGAME_DATA_DIR="$(mktemp -d)"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8122
VITE_BACKEND_TARGET=http://127.0.0.1:8122 npm --prefix frontend run dev -- --port 5174
```

生产构建：

```bash
npm --prefix frontend run build
```

构建产物位于 `frontend/dist/`。公网部署应保持后端只监听回环地址，并通过受审核的反向代理暴露；本仓库的部署模板不代表当前机器已部署。

## 验证命令

```bash
python -m pytest -q backend/tests
python scripts/validate-card-assets.py
npm --prefix frontend run build
npm --prefix frontend exec playwright test -- --list
```

如需执行 Playwright E2E：

```bash
RUN_PLAYWRIGHT_E2E=1 ./scripts/run_tests.sh
```

## 多人测试建议

1. 启动隔离的本地后端和前端开发服务器，访问本地前端地址。
2. 再用无痕窗口或另一浏览器上下文打开同一地址。
3. 玩家 A 创建房间。
4. 玩家 B 加入房间。
5. 所有人 READY 后开始游戏，测试出牌、摸牌、选颜色/目标/多选、商店交换、暂停恢复、UNO、+4/岁牌响应、断线重连与结算再准备。

## 安全注意

- 不要打印 `.env`。
- 不要打印 token、session token、reconnect token。
- 不要打印 `runtime/data/rooms` 或 `data/rooms` 中的房间 JSON 正文。
- 不要把 `runtime`、`data/rooms`、`audit`、`artifacts`、`.git`、`node_modules` 暴露到公网。
- 不要在公网启用 `TEST_MODE=1`。
- 后端保持 `127.0.0.1:8012` 内部监听，由 Nginx 提供公网入口。
