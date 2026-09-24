# suicardgame

本文档使用 UTF-8 编码保存。

`suicardgame` 是一个多人联机卡牌项目：以经典 UNO 为基础规则，并加入 `cards.zip` 中整理出的岁牌特殊牌/场地牌规则。后端负责权威状态结算，前端通过 HTTP API 与 WebSocket 进行多人房间同步。

## 当前状态

- 项目路径：`/home/suicardgame`
- 后端：FastAPI / Uvicorn，内部监听 `127.0.0.1:8012`
- 前端：Vite 构建产物，由 Nginx 提供静态访问
- 公网测试入口：`http://139.196.13.53:8000/`
- API 健康检查：`http://139.196.13.53:8000/api/v1/health`
- 运行数据目录：`/home/suicardgame/runtime/data/rooms`
- 敏感目录权限要求：`runtime`、`runtime/data/rooms`、`data/rooms` 保持 `700`

## 项目结构

```text
/home/suicardgame
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
├── audits/                         # 审计与部署报告，不应对公网暴露
└── runtime/data/rooms              # 运行房间数据，禁止打印或公开
```

## 如何启动

### 生产/公网测试方式

当前正式运行方式是：

1. systemd 启动后端服务 `suicardgame.service`；
2. 后端仅绑定 `127.0.0.1:8012`；
3. Nginx 监听公网测试端口 `8000`，提供前端静态文件，并反向代理 `/api/` 与 WebSocket 到后端。

常用检查命令：

```bash
sudo systemctl status suicardgame --no-pager
sudo systemctl status nginx --no-pager
curl -fsS http://127.0.0.1:8012/api/v1/health
curl -fsS http://127.0.0.1:8000/api/v1/health
```

用户手动测试地址：

```text
http://139.196.13.53:8000/
```

### 手动启动后端

如果不使用 systemd，只在服务器内手动启动后端：

```bash
cd /home/suicardgame
./scripts/start_backend.sh
```

等价命令：

```bash
cd /home/suicardgame
source /home/miniconda3/etc/profile.d/conda.sh
conda activate audio
export SUICARDGAME_DATA_DIR=/home/suicardgame/runtime/data/rooms
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8012
```

不要把后端直接绑定到 `0.0.0.0`，公网入口应由 Nginx 控制。

### 前端开发启动

```bash
cd /home/suicardgame
./scripts/start_frontend_dev.sh
```

开发服务器只用于调试，不作为生产部署入口。

### 构建前端

```bash
cd /home/suicardgame
./scripts/build_frontend.sh
```

构建产物位于：

```text
/home/suicardgame/frontend/dist
```

## 验证命令

```bash
cd /home/suicardgame
./scripts/run_tests.sh
./scripts/smoke_backend.sh
```

如需执行 Playwright E2E：

```bash
cd /home/suicardgame
RUN_PLAYWRIGHT_E2E=1 ./scripts/run_tests.sh
```

## 多人测试建议

1. 打开普通浏览器访问 `http://139.196.13.53:8000/`。
2. 再用无痕窗口或另一台设备打开同一地址。
3. 玩家 A 创建房间。
4. 玩家 B 加入房间。
5. 开始游戏，测试出牌、摸牌、选颜色、UNO 宣告/抓取、Wild Draw Four 质疑、特殊牌提示与刷新重连。

## 安全注意

- 不要打印 `.env`。
- 不要打印 token、session token、reconnect token。
- 不要打印 `runtime/data/rooms` 或 `data/rooms` 中的房间 JSON 正文。
- 不要把 `runtime`、`data/rooms`、`audits`、`.git`、`node_modules` 暴露到公网。
- 不要在公网启用 `TEST_MODE=1`。
- 后端保持 `127.0.0.1:8012` 内部监听，由 Nginx 提供公网入口。
