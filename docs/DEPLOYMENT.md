# 部署说明

日期：2026-06-15

## 本地运行

后端：
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python scripts/generate-card-assets.py
python scripts/validate-card-assets.py
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

前端：
```bash
cd frontend
npm install
npm run dev
```

## 当前临时部署

服务器别名：`suicardgame-server`  
运行目录：
```text
/home/twq/suicardgame/releases/suicardgame-rebuild-20260615-010755
```

发布包：
```text
suicardgame-rebuild-20260615-010755.zip
SHA-256: c405b175d16711852411c2f9373bf5385712c4ceb52e4ce5267c4f4bc09f3f35
```

监听：
```text
127.0.0.1:8011
```

运行数据：
```text
/home/twq/suicardgame/runtime/data/rooms
```

进程与日志：
```text
/home/twq/suicardgame/runtime/uvicorn-8011.pid
/home/twq/suicardgame/runtime/uvicorn-8011.log
```

临时服务启动命令应使用 conda 环境里的真实 Python，可让 pidfile 指向实际监听进程：
```bash
SUICARDGAME_DATA_DIR=/home/twq/suicardgame/runtime/data/rooms \
/home/twq/miniconda3/envs/audio/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8011
```

不要用 `conda run -n audio python -m uvicorn ...` 作为长期后台服务命令；它会产生包装进程，pidfile 可能不指向真实监听者。

## 停止临时服务

优先按端口反查真实监听 PID：
```bash
ss -ltnp | grep '127.0.0.1:8011'
```

停止该 PID 后再启动新版本。仅杀 pidfile 中的包装进程不足以证明旧服务已停止。

## 未执行

- sudo
- Nginx
- systemd
- 开机自启
- 防火墙或安全组变更
- 公网端口开放

## 发布包要求

上传前必须完成：

- 后端测试
- 牌面资源校验
- 前端生产构建
- 唯一发布包
- SHA-256
- 排除密码、token、`.env`、`node_modules`、缓存、日志和私密房间数据

## 回滚

当前仍是临时进程方式。回滚步骤：

1. 用端口反查并停止 `127.0.0.1:8011` 的真实监听进程。
2. 切换到上一个 release 目录。
3. 使用 conda 环境真实 Python 和相同 `SUICARDGAME_DATA_DIR` 启动。
4. 检查 `/api/v1/health`。

正式生产化前仍需单独授权 Nginx、systemd、端口暴露和旧服务停用等操作。
