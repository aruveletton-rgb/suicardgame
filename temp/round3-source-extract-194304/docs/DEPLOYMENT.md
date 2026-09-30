# 部署说明

基线日期：2026-09-25
版本：`suicardgame-v1.1`

## 当前生产拓扑

- SSH 别名：`suicardgame-server`
- 项目目录：`/home/suicardgame`
- 公网入口：`http://139.196.13.53:8000/`
- Nginx：监听 `0.0.0.0:8000`，提供静态文件并代理 `/api/`
- Uvicorn：仅监听 `127.0.0.1:8012`
- systemd 单元：`suicardgame.service`
- 持久化目录：`/home/suicardgame/runtime/data/rooms`
- 前端产物：`/home/suicardgame/frontend/dist`

WebSocket 使用无凭据 URL：

```text
ws://host/api/v1/rooms/{room_code}/ws
```

客户端收到公开快照后，通过首帧 `authenticate` 发送 `player_id` 与 `session_id`。Nginx 的 WebSocket location 会移除查询字符串，systemd 同时将 Uvicorn 日志级别设为 `warning`，避免会话凭据进入请求日志。

## 本地验证

后端：

```bash
python -m pytest backend/tests -q
python scripts/validate-card-assets.py
```

前端：

```bash
cd frontend
npx tsc --noEmit
npm run build
npx playwright test
```

## 发布前检查

```bash
ssh suicardgame-server
cd /home/suicardgame
systemctl status suicardgame --no-pager
sudo nginx -t
curl -fsS http://127.0.0.1:8012/api/v1/health
curl -fsS http://127.0.0.1:8000/api/v1/health
ss -ltnp | grep -E ':(8000|8012) '
```

必须确认：

- `8012` 仅绑定 `127.0.0.1`；
- `8000` 由 Nginx 对外监听；
- `runtime`、`data/rooms` 权限不宽于 `0700`；
- `.env`、`.git`、`runtime`、`data/rooms`、`audits` 公网访问返回 `404`；
- 工作区备份完成且不包含运行时房间数据的覆盖操作。

## 发布流程

1. 在服务器创建带时间戳的代码与配置备份。
2. 上传本次变更文件，不覆盖 `runtime/data/rooms`。
3. 在服务器运行完整后端测试、资源校验、TypeScript 检查和前端生产构建。
4. 使用模板更新 systemd 与 Nginx 配置，执行 `systemd-analyze verify` 和 `nginx -t`。
5. 原子替换前端 `dist`，重启 `suicardgame.service`，平滑重载 Nginx。
6. 检查内外健康接口、静态页面、WebSocket 首帧认证和敏感路径。
7. 执行最小压力测试并记录 CPU、内存、延迟和错误率。

## 回滚

1. 停止继续发布，不删除当前运行数据。
2. 从发布前备份恢复代码、`frontend/dist`、systemd 单元和 Nginx 配置。
3. 执行 `sudo systemctl daemon-reload`、`sudo systemctl restart suicardgame`、`sudo nginx -t` 和 `sudo systemctl reload nginx`。
4. 重新检查两个健康接口及公网首页。

禁止使用 `git reset --hard`、强制推送、删除 `runtime/data/rooms` 或未验证路径的递归删除完成回滚。
