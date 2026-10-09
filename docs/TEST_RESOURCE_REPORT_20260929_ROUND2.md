# 第二轮测试、浏览器与资源报告

日期：2026-09-29
工作区：`E:/suicardgame`
分支：`codex/suicardgame-v1.2`
测试对象：`0c61d81` + 当前工作区修复补丁（最终提交前）。

## 环境与隔离

- Windows 开发机；后端使用 `C:/ProgramData/anaconda3/python.exe`，依赖通过 `PYTHONPATH=C:/Users/tangweiqing/AppData/Local/Temp/suicardgame-qa-py313;E:/suicardgame` 提供。
- Node/npm 使用仓库已有安装；生产构建 Vite 8.0.16。
- 每次后端/E2E 使用独立 `SUICARDGAME_DATA_DIR` 和独立端口；未读写项目 `data/rooms`、附件原有房间或真实 token。
- 当前 HEAD：`0c61d811d7cfe632466b3fe8965b1a503069384f`；工作区源码补丁 SHA-256 清单见 `artifacts/acceptance/source-files-20260929-round2.sha256.json`。

## 后端

命令：

`C:/ProgramData/anaconda3/python.exe -m pytest -q backend/tests --junitxml=artifacts/acceptance/backend-full-20260929-round2-final.xml`

环境变量：隔离 `PYTHONPATH` 和 `SUICARDGAME_DATA_DIR`。
结果：**266 passed, 1 warning, 17.55s**；退出码 0。Warning 是 anyio/Starlette BlockingPortal 弃用提示，不影响测试。基线审计记录的 264 项不是本轮目标数量；本轮增加/迁移了有岁真实失败与隐私行为断言，最终 JUnit 的 tests 属性为 266。

## 素材与构建

- `C:/ProgramData/anaconda3/python.exe scripts/validate-card-assets.py`：退出码 0，`validated 68 manifest assets, 13 card crops and 12 avatars`。
- `cmd /d /c npm --prefix frontend run build`：退出码 0，1761 modules；CSS 51.89 kB / gzip 10.51 kB，JS 270.59 kB / gzip 87.82 kB。产物：`frontend/dist/assets/index-C6wZ6mwv.css`、`index-Y4Hl-EOj.js`。

## 生产样式验证

使用本地 Vite preview（端口 5180）和系统 Chrome headless，向生产页面插入红/黄/绿/蓝/wild 卡面探针并读取 computed style。结果保存在 `production-card-computed-style-20260929-round2.log`：四色分别为 rgb(187,57,60)、rgb(208,165,36)、rgb(37,128,96)、rgb(45,104,157)，wild 为四色 conic-gradient；普通卡保留底纹，非灰色覆盖。

## 浏览器验收

使用本机现有 Chrome/Playwright Chromium，均为真实 UI 操作；TEST_MODE 只建立难以稳定随机得到的初始场景，待验操作不通过直接 API 替代。

- `playwright-acceptance-round2-final.log`：视觉布局、卡图库、手机操作/暂停恢复、胜负重开，4 passed（51.0s）。覆盖 1366×768、1920×1080、360×640、390×844、844×390。
- `playwright-product-table-round2-final.log`：入口/大厅/图鉴与桌面/移动布局可达，3 passed（13.5s）。
- `playwright-multiplayer-round2-final.log`：实时多人、响应窗口、重连/隐私，2 passed（31.8s）。
- 首次浏览器尝试因 webServer 误用系统 Python 失败，原始日志 `e2e-card-gallery-20260929-round2.log` 保留；切换到已存在隔离依赖和独立端口后通过，不将首次环境错误计入产品失败。

## Linux 入口

使用 Git Bash（`C:/Program Files/Git/bin/bash.exe`）：

- 11 个 `scripts/*.sh` 文件逐一 `bash -n` 通过；逐文件字节扫描 CRLF=0。
- `bash scripts/run_tests.sh --help` 退出码 0。
- 证据：`bash-portability-20260929-round2-final.log`。

## 资源与远端边界

本轮没有目标机授权/候选部署，因此 G8 **未验证**。不把历史远端采样、旧 /home/suicardgame 代码或本机开发机浏览器运行当作 Ubuntu 22.04、2 vCPU / 2 GiB 证据；没有执行 SSH、systemd、Nginx、防火墙或真实房间数据操作。

## 运行身份与证据规则

最终机器摘要绑定 `run_id=round2-20260929-1357`，并列出当前 HEAD、工作区补丁 hash、命令、退出码、证据路径和 G8 阻塞原因。日志不含真实 token、session/reconnect token 或私有房间数据。
