# qx-rules-sync

QuantumultX 配置自动校验镜像。**每天北京时间 08:00** 扫描上游配置引用的每一个外部资源，活着的镜像到本仓库，死了的注释掉，然后重建一份干净的 `QuantumultX.conf`。

目的是解决一个具体问题：Quantumult X 拉取配置时，如果上游引用的脚本/规则已经被作者删除，会一次性弹出一屏 `Status code 404`，而且重试永远无效——那些文件真的不在了。

## 怎么用

Quantumult X → 右下角风车 → 配置文件 → 远程配置 → 添加：

```
https://raw.githubusercontent.com/VanwaysAI/qx-rules-sync/main/QuantumultX.conf
```

节点订阅自己填进 `[server_remote]`，本仓库**不托管任何节点**。

## 在上游之外额外追加的规则

上游配置本身缺两块，`config/additions.json` 补上了，位置经过优先级计算：

| 规则源 | 位置 | 内容 |
|---|---|---|
| `fmz200/.../filter/filterFix.list` | **`[filter_remote]` 最前** | 63 条 `direct` 修正，把被误分到外区的国内站点拉回直连 |
| `fmz200/.../filter/filter.list` | **`[filter_remote]` 末尾** | 2787 条 `reject` 广告拦截，作为 `ADBlack.list` 的补充 |

**顺序不能反。** `[filter_remote]` 是顺序匹配、先命中先生效。`filterFix` 的 `direct` 如果排在 `ADBlack.list` 后面，会被前面那条 `reject` 抢先吃掉，等于白加。

要加自己的规则源，往 `config/additions.json` 的数组里塞一条就行，`line` 里的 `{url}` 会被替换成镜像后的地址。

## 它做了什么

| 步骤 | 说明 |
|---|---|
| 扫描 | 递归解析主配置 + 它引用的每个 conf/list 内部的脚本，共约 90 个外链 |
| 探测 | 24 并发请求，重试 3 次；识别软 404（CDN 返回 200 的 HTML 错误页） |
| 修复 | 先查 `config/overrides.json` 的映射表，能找到新地址的自动替换 |
| 镜像 | 存活资源全量下载到 `Sources/`，配置里的链接改写成本仓库地址 |
| 注释 | 确凿失效（404 / 410 / 451 / HTML 错误页）的行前加 `# [qx-sync 失效]` |
| 报告 | 生成 `reports/STATUS.md`，列出每条资源的状态 |

**关键设计：不误杀。** 只有 404 / 410 / 451 这类"确实不存在"才注释。超时、429 限流、5xx 这类可能是扫描器自己网络问题，一律保留原链、下轮复验——宁可留个可能坏的，也不砍掉能用的。

## 当前上游的真实状况

上游 `Moli-X/Resources` 的主配置本身没问题，但它**大量引用已死亡的上游**：

| 上游仓库 | 状态 |
|---|---|
| `RuCu6/QuanX` | 整个仓库消失，账号只剩 8 个无关仓库 |
| `WeiRen0/Scripts` | 已删除 |
| `WSL33099/QuantumultX` | 451 DMCA 封禁 |
| `blackmatrix7` 的 smzdm 脚本 | 已移除，只剩 list 规则 |

`RuCu6` 那批（cnftp / fenbi / ithome / kuwo / myBlockAds / weibo）在 `fmz200/wool_scripts` 里有等价副本，已通过映射表自动接回。知乎脚本没有等价替代，只能放弃。

## 目录

```
QuantumultX.conf          生成的主配置（别手改，下次同步会覆盖）
Sources/                  镜像的外部资源（按原始仓库路径存放）
config/upstream.json      上游地址、镜像范围
config/overrides.json     死链修复映射表 / 放弃名单
scripts/sync.py           同步器
reports/STATUS.md         体检报告
reports/status.json       机器可读结果（用于和上一轮做 diff）
```

## 想加修复

发现某条链接还有救，编辑 `config/overrides.json`：

```json
{
  "replace": {
    "https://raw.githubusercontent.com/死了的仓库/xxx.js":
      "https://raw.githubusercontent.com/活着的仓库/xxx.js"
  }
}
```

提交后 Actions 会自动重跑。映射表里的替代源也会被实测，实测失败会回落成注释。

确认某条彻底没救、不想每轮都探测它，加进 `drop` 数组。

## 注意事项

- **定时任务会被 GitHub 自动暂停**：仓库连续 60 天无提交活动，schedule 会被禁用。每周手动触发一次，或者给仓库随便提个 commit 就行。
- **定时不完全准点**：GitHub Actions 的 schedule 在高峰期会延迟几分钟到半小时，08:00 的任务可能 08:20 才跑完。
- **Qx 主配置不自动更新**：子规则和重写会按 `update-interval` 自动拉，但 Qx 的主 profile 需要在 App 里手动点一次「更新」。所以建议你现在配置里启用、之后每周手动更新一次即可。
- **镜像内容版权归原作者**，本仓库只是可用性中继，不做任何修改（除了改写链接和注释死链）。
