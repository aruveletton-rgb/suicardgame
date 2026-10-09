# 审计证据

先读主报告。submitted_screenshots 来自用户上传源码包，不是本次新浏览器截图。

原始测试和定向测试均未修改产品源码。legacy-ready-diagnostic 是诊断运行：临时将 start_game 调用前的 room.players[*].ready 置 True，排除 test_player_limits_v12.py 后复跑，仅证明旧失败受准备条件影响，不构成验收通过。

resource_smoke.py 中路径请自行替换为隔离项目/虚拟环境目录。CPU/RSS 采样 PID 无法可靠归属，已从结果剔除；脚本中原始采样逻辑仅供审计，不可作为有效性能测量。

不含真实房间数据。日志已脱敏。
