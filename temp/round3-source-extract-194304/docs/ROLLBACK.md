# 回滚方案

当前尚未部署到服务器。

目标部署时每次发布使用独立版本目录：

```text
/home/twq/suicardgame/releases/suicardgame-rebuild-YYYYMMDD-HHMMSS/
```

回滚原则：

- 保留上一版本目录。
- 不覆盖生产数据快照。
- 启动前记录端口、日志路径、数据目录和进程方式。
- 未经单独授权不修改 systemd、Nginx、防火墙或旧服务。

