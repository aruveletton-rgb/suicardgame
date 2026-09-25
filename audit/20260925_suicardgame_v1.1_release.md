# suicardgame-v1.1 发布审计

- 审计日期：2026-09-25
- 目标主机：`suicardgame-server`
- 部署目录：`/home/suicardgame`
- 公网入口：`http://139.196.13.53:8000/`
- 版本标识：`suicardgame-v1.1`
- 结论：通过

## 问题与修正

1. 原大厅直接展示空牌桌，缺少房间状态、行动指引和规则信息。重构为入口页、大厅仪表盘、牌局页三层架构，大厅新增房间号、在线/准备人数、开局步骤、玩家状态和岁牌规则预览。
2. WebSocket 凭据原位于查询字符串，可能进入代理或应用日志。改为连接后的首帧认证，并在 Nginx WebSocket 路由中丢弃遗留查询字符串。
3. Playwright 默认数据目录与后端 Step8 隔离规则不一致。默认改为进程唯一的 `/tmp/suicardgame-step8-*` 目录。
4. 部署文档与现有 systemd、Nginx 和端口拓扑不一致。文档和部署模板已同步更新。

## 验证证据

- TypeScript：`npx tsc --noEmit` 通过。
- 前端生产构建：Vite 构建通过，JS 225.26 kB，CSS 14.12 kB。
- 后端：`221 passed in 6.58s`。
- 浏览器回归：`10 passed in 34.0s`。
- 本机 Edge 公网检查：页面标题、创建房间、加入房间和中文内容均可读取；截图位于 `artifacts/v1.1-ui/public-postdeploy-entry.png`。
- 公网大厅检查：房间号长度 6、玩家列表 1 行、规则卡 4 张、实时连接正常、单人开局禁用、控制台错误 0。
- WebSocket 安全烟测：公开快照后首帧认证成功并收到私有快照；遗留查询参数被 Nginx 丢弃；journald 未出现测试标记。
- 敏感路径：`/.env`、`/.git/config`、`/runtime/data/rooms`、`/data/rooms`、`/audits`、`/deploy_templates` 均返回 404。

## 最小压力测试

- 场景：5 个并发房间、19 名玩家、每房 2-5 人、最多 15 轮命令。
- 总耗时：1.62 秒；命令错误：0；手牌泄露：0；座位冲突：0。
- HTTP P95：创建 24.14ms，加入 43.78ms，命令 19.15ms。
- WebSocket P95：连接 16.16ms，认证后私有快照 22.58ms。
- 资源：服务内存约 68.9MB；采样期间最低 CPU idle 63%，无 swap。

## 部署与回滚

- systemd 后端：`127.0.0.1:8012`；Nginx：`0.0.0.0:8000`，同时保留现有 80 监听。
- 部署后两层健康检查均返回 `{"status":"ok"}`。
- 回滚包：`/home/suicardgame/audits/releases/suicardgame-v1.1-20260925`。
- 运行数据目录未移动、未覆盖、未删除。

## 限制

- 当前公网入口仍为 HTTP IP 直连，传输层不具备 TLS；本次通过首帧认证与查询字符串剥离消除了凭据出现在 URL/日志中的风险，但正式公开运营仍建议配置域名和 HTTPS。
