# 项目执行基线（2026-09-28，本轮修复）

## 目标与范围

当前项目是 React/TypeScript/Vite 前端与 FastAPI 单进程权威结算的多人联机 UNO＋岁牌游戏。本轮目标为修复 UI、特殊牌与 90/30/15/10 秒时限/暂停链路，并以真实测试和浏览器证据验收。允许修改本仓库源码、测试及文档；不修改已运行的远端服务、真实房间数据、系统配置或部署模板，不增加数据库/队列/AI 对手等范围外功能。

## 工作区与版本

- 本地工作区：`E:\suicardgame`；基线分支 `codex/suicardgame-v1.2`，基线提交 `0559f48`。
- `origin`：`git@github.com:aruveletton-rgb/suicardgame.git`。本轮开始时已有两个未跟踪的 `audit/20260928_suicardgame_v1.2_jingxichangunit_8080.*` 及 `temp/`；视作用户已有内容，不纳入本轮提交。
- README 中 `/home/suicardgame`、8012 和公网地址是旧环境说明，不能作为当前本地运行状态证据。先前在 `jingxichangunit` 的 8080 服务亦不在本轮改动范围。

## 验收与兼容

- 2–5 人、全部在座玩家在线并 READY 才能开局；不能为旧测试恢复免准备开局。
- 后端负责规则、窗口超时、暂停、恢复、幂等与持久化；HTTP/WS 现有身份/命令链继续有效。老房间快照兼容加载且不静默删除或踢人。
- 三种主要布局（桌面、手机竖屏、手机横屏）必须支持实际操作；普通牌与角色卡面需真实渲染。八项审计失败语义必须改为行为回归。
- 目标服务器为 2 vCPU/2 GiB，但可用份额未知；资源目标需实测，不凭硬件参数宣称容量。本轮默认只做开发机/隔离环境验证。

## 本地验证入口

- 后端：从仓库根目录运行 `python -m pytest -q backend/tests`，使用隔离 `SUICARDGAME_DATA_DIR`，绝不指向真实 `runtime/data/rooms`。
- 卡图：`python scripts/validate-card-assets.py`。
- 前端：`cd frontend && npm run build`；浏览器：`cd frontend && npx playwright test`（配置必须使用独立数据目录与端口）。
- `scripts/run_tests.sh` 当前基线包含旧绝对路径与 Conda 环境假设，由 QA 线程迁移后才作为可移植验证入口。

## 证据边界

审计报告/证据包仅证明旧状态缺陷，不是规则来源；历史截图不能冒充本轮实测。结果报告按 G1–G8 分开记录，通过只依据本轮集成版本的命令/断言/截图/采样。真正未决规则仅在现行权威资料无依据时提出具体选项。
