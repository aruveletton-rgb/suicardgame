# Agent D · product_ui 交接（2026-09-28）

## 基线与范围

- 契约：`docs/agent-notes/contract.md` v1.1。
- 基线提交：`0559f48`（共享工作区存在 A/B/C/E 与主线程并行改动；本线程未覆盖或暂存他人文件）。
- 本线程只修改 D 的组件、数据、静态素材、卡图脚本、专属 E2E 和本文件。

## 已完成

1. `CardView`：
   - 普通 UNO 与牌背均为自包含 DOM/CSS，不依赖 SVG 内的外部 JPG。
   - 四色除颜色外还使用不同底纹；数字、禁用、反转、+2、万能、+4 保留中心与对角符号。
   - 岁牌/场地牌使用离线裁切的 360×540 WebP，保留左侧原角色卡面，不再把整张规则说明缩进手牌。
2. 结构化规则：
   - `rules.ts` 提供通用“有岁”、高辈分规避、90/30/15/10 秒规则，以及 13 张岁/场地牌的 timing、summary、steps、notes、卡面与原图路径。
   - `RulesGallery` 可逐张展开阅读并单独查看未经裁切的完整原图。
3. 首页/大厅/结算：
   - `EntryPanel`：受控 nickname/avatar/roomCode；本机昵称记忆；`?room=` 邀请预填；13 个内置头像；不持有网络连接。
   - `LobbyDashboard`：公开邀请二维码/链接（只编码 `room`）、5 个明确座位、在线/准备/等待者、完整图鉴入口。
   - `GameResult`：胜者/中止分离、每人剩余牌数、再来一局/返回大厅；`canManage=false` 时等待房主且禁用管理操作。
4. 头像与素材：
   - 生成 12 个 256×256 WebP 角色头像；默认头像由 CSS 绘制“岁”。
   - `scripts/generate-card-assets.py` 增加确定性裁切；`scripts/validate-card-assets.py` 校验尺寸与完整性。

## C / 主线程集成接口

统一入口：`frontend/src/components/product/index.ts`。

| 导出 | Props / 说明 |
|---|---|
| `EntryPanel` | `nickname`, `avatarId`, `roomCode`, `busy?`, `error?`, `onNicknameChange`, `onAvatarChange`, `onRoomCodeChange`, `onCreate`, `onJoin` |
| `RulesGallery` | `open`, `onClose` |
| `GameResult` | `players`, `winnerPlayerId`, `outcome?: 'completed' | 'aborted'`, `rematchPending?`, `canManage?`, `onRematch`, `onReturnLobby` |
| `createPublicInviteUrl` | 只保留当前公开 URL 的 path，并仅写入 `room` 查询参数；不会携带 session/reconnect token |
| `LobbyDashboard` | 保留原 Props；新增可选 `inviteUrl`, `onCopyInviteLink`, `onOpenRules` |

必须加载 `frontend/src/styles/product.css`。创建/加入房间时把 `avatarId` 传给现有 `createRoom` / `joinRoom`。

## 素材来源与裁切

- 原图：`frontend/public/assets/cards/sui/*.jpg`，与审计材料中的 cards 原图映射一致。
- 卡面统一裁切：以 1000×1000 为基准 `(10, 14, 390, 584)`，按原图尺寸同比缩放后输出 360×540 WebP。
- 角色头像：逐图单独坐标，配置在 `scripts/generate-card-assets.py::AVATAR_CROPS`；输出 256×256 WebP。
- 产物：`frontend/public/assets/cards/portraits/`、`frontend/public/assets/avatars/`。
- 坎诺特明确标为 `field` / “场地 NPC”，不伪装为可手持岁牌。

## 修改文件

- `frontend/src/components/CardView.tsx`
- `frontend/src/components/LobbyDashboard.tsx`
- `frontend/src/components/PlayerRoster.tsx`
- `frontend/src/components/product/*`
- `frontend/src/data/rules.ts`
- `frontend/src/data/avatars.ts`
- `frontend/src/styles/product.css`
- `frontend/public/assets/cards/portraits/*`
- `frontend/public/assets/avatars/*`
- `scripts/generate-card-assets.py`
- `scripts/validate-card-assets.py`
- `frontend/e2e/agent_product/product-entry-lobby-rules.spec.ts`
- `docs/agent-notes/product_ui.md`

## 验证

执行：

```powershell
python scripts/validate-card-assets.py
frontend/node_modules/.bin/tsc.cmd --noEmit -p frontend/tsconfig.json
```

结果：

- 素材校验通过：`68 manifest assets, 13 card crops and 12 avatars`。
- 本地 TypeScript `--noEmit` 通过。
- 未运行 Vite build 与浏览器多会话；按重任务令牌约束，最终 build / E2E 由 C 集成后和 E 统一执行。

命令偏差：曾从仓库根目录误执行 `npx tsc --noEmit`，`npx` 解析为废弃同名包并输出提示；没有修改项目 `package.json` / lockfile，也没有完成该次类型检查。随后改用已安装的 `frontend/node_modules/.bin/tsc.cmd` 并通过。

## 未验证 / 风险

- `EntryPanel`、`RulesGallery`、`GameResult` 的真实浏览器流程依赖 C 在 `App.tsx` 的最终集成；专属 Playwright 用例已提供但本线程未运行。
- 二维码已从代码层保证只编码公开房间号，仍需 E 在浏览器中验证复制内容与扫码入口。
- 裁切产物抽样目视检查通过（望、符咒、绩头像、岁相头像）；全量页面排版与触屏原图弹层由 E 做当前集成版本验收。
