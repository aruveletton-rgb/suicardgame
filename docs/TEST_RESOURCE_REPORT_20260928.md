# 测试与资源报告（2026-09-28）

## 已运行

| 命令 | 结果 |
| --- | --- |
| `python -m compileall -q backend` | 通过 |
| `cd frontend; npm ci` | 通过；锁定依赖安装，npm audit 报告 2 个 high（未执行自动修复） |
| `cd frontend; npm run build` | 通过；Vite 产物生成 |
| `PYTHONPATH=. pytest -q backend/tests/test_player_limits_v12.py backend/tests/test_wild_draw_four_challenge.py backend/tests/test_special_card_exactness_matrix.py backend/tests/test_sui_xiang_seen_trigger.py` | 通过，12 passed、1 warning |
| `PYTHONPATH=. pytest -q backend/tests/test_multiplayer_flow.py backend/tests/test_wild_draw_four_challenge.py backend/tests/test_special_card_exactness_matrix.py` | 8 通过；1 个旧用例失败，因为它只准备客人却要求房主直接启动 |
| `PYTHONPATH=. pytest -q backend/tests/test_player_limits_v12.py` | 通过，2 passed；覆盖第六人拒绝和全员准备开局 |

仓库根目录直接运行 `pytest -q` 会因 Python path 不含仓库根而收集失败；正式命令应带 `PYTHONPATH=.`。根目录直接运行 `npm run build` 也不适用，前端命令必须在 `frontend/`。

## 资源边界

本轮未在用户给出的 Ubuntu 2 核/2 GiB 目标机上运行压测，也未启动线上服务。没有据硬件配置推断可支持房间数。前端资源处理均为构建机离线工作；截图使用本地开发进程。

## 仍未宣称通过

完整旧测试集结果为 83 passed、140 failed、1 skipped。失败集中在旧夹具仍按“无需准备即可启动”、10 人并发上限以及依赖旧启动前置的后续用例；不能将其结果写成全绿。需要在更新测试夹具后再运行完整后端、Playwright 多会话和 5 人房间资源测量。
