# 卡面资源清单

资产来源：

- 经典 UNO 牌和卡背：`scripts/generate-card-assets.py` 生成原创 SVG。
- 特殊牌和基础规则图：`cards.zip` 原图，路径为 `frontend/public/assets/cards/sui/`。
- 统一映射入口：`backend/app/domain/cards.py::asset_manifest()` 和生成的 `frontend/src/data/cardManifest.json`。

特殊牌映射：

| asset_key | 名称 | 文件 |
|---|---|---|
| `sui_wang` | 望牌 | `15aefb709c02084fbf08600c51e42d85.jpg` |
| `sui_yu` | 余牌 | `23db64326534b6478c57bae78d1c1590.jpg` |
| `sui_yi` | 易牌 | `23f1f0c5d35242bc5a52bba759946770.jpg` |
| `sui_zuole` | 左乐牌 | `2f42240353fbe94ad44e1ee11070299b.jpg` |
| `sui_xi` | 夕牌 | `3e25cb360344c2f96a7120b0bdc36335.jpg` |
| `sui_shu` | 黍牌 | `941e81d9c480f062462aed1364e55ad1.jpg` |
| `sui_chongyue` | 重岳牌 | `9bf6f1118300add4e001671f90641b5d.jpg` |
| `sui_ling` | 令牌 | `a096ad301444ccefec6871995adafdef.jpg` |
| `field_cannot` | 坎诺特牌 | `ddc008e08c2dc031c8a7f115a3832c43.jpg` |

校验结果：`python scripts/validate-card-assets.py` 已验证 64 个资产。

