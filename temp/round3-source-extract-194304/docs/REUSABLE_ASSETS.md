# 可复用资源清单

## 直接复用

- `cards.zip` 中 14 张 jpg 原图，已复制到 `frontend/public/assets/cards/sui/`。
- 图片尺寸均非零且可解码：13 张为 `1000x1000` 或近似尺寸，额外基础规则图为 `1200x1200`。
- 旧项目 FastAPI + React + Vite 的轻量部署方向可复用为技术判断。

## 仅可参考

- 旧 `frontend/scripts/generate-card-assets.mjs` 的“生成经典牌面”思路可参考，但输出含白色牌，不能直接迁移。
- 旧 WebSocket 快照广播思路可参考，但必须改成 Room/Game 分离、私密事件隔离和命令幂等。
- 旧 JSON 快照持久化可参考，但必须改成原子写入、game_epoch 隔离和 prompt 恢复。

## 不复用

- 旧 `card-manifest.json` 包含白色普通牌和白色动作牌。
- 旧坎诺特商店技能商品不复用。
- 旧状态窗口和 penalty stack 不复用。

