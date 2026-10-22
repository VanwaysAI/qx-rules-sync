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

## 已修掉的上游坑

除了死链，上游配置还有一处会直接把 MITM 打死：

```
[mitm]
passphrase =        ← 值为空
p12 =               ← 值为空
```

Qx 见到 `p12` 键存在但没值，会以为"用户要用自定义证书"，然后去加载一个空证书，直接弹 **`MitM 错误的 p12 或 p12 passphrase，连接已断开`**。MITM 起不来，所有 rewrite 全部失效（但分流和代理还能用，所以很容易误判成"重写规则没生效"）。

生成时会自动删掉这类空值键（`config/upstream.json` 的 `strip_empty_keys`），Qx 随即改用自己生成的 CA。

**如果你在 Qx 里手填过自定义证书**，注意本仓库的配置是每天覆盖重建的，别把证书写进配置文件——用 App 内的证书设置。

第二个坑在 `echo-response`：

```ini
^https?:\/\/wrapper\.cyapi\.cn\/v1\/activity\? url echo-response application/json echo-response https://....../caiyun.json
```

Qx 的 `echo-response` 要么写字面量、要么填 `data:` URI —— 但**只要有 URI 特征就会被拒**（`https://` 和 `data:` 都算），它只认 Qx 沙盒 `Data` 目录里的本地文件。远程配置没有任何办法往用户手机里放文件，所以这类规则**远程无解**。

`fix_echo_response()` 的处理是**把整条规则注释掉**（不是改写，是停用）。代价是该 App 的 mock 去广告失效，收益是那个红字报错彻底消失。教训：早先一版把它改成 `data:application/json;base64,...` 试过，一样报错——`data:` 本身就是 URI。

第三个坑，也是最致命的一个：**规则类型大小写**。

分流清单里 `HOST-SUFFIX`（大写）写了 69235 条，`host-suffix`（小写）只写了 18 条，同一份文件混着来。Qx 原生的规则类型是**小写**，大小写混用在不同版本上容错度不一致；解析器一旦整体拒收，这张 7.9 万条的国内直连表就等于**一条都没加载**——而 Qx 界面上不会报错。

`normalize_rule_types()` 会把所有清单的规则类型统一成小写，并把 Surge 专有的 `domain` / `domain-suffix` / `domain-keyword` 映射成 Qx 的 `host` / `host-suffix` / `host-keyword`；真正无法识别的类型会注释掉并标记 `[qx-sync 未知规则类型]`。首轮跑出 **92707 条**需要转换。

第四个坑：**兜底策略组可能整个失效**。

```ini
static=海外服务, 优选节点, 香港服务, 美国服务
FINAL,海外服务
```

`香港服务` / `美国服务` 是 `url-latency-benchmark` + 正则，靠节点名匹配。如果订阅里没有港/美节点（比如只有新加坡和日本），这两个组就是空的；兜底组一旦因此失效，`FINAL` 就指向了不存在的东西，Qx 会退回它自己的默认策略——在「网络活动」里显示成 **`ALL, PROXY`**——于是**所有流量，包括国内，全都走当前选中的那个节点**。

`harden_policy_groups()` 把兜底链上的 `static` 组收缩成单一成员 `优选节点`（正则是 `^(?!.*网易云)`，匹配所有非网易云节点，必定非空）。`香港服务` / `美国服务` 仍然保留，只是不再挂在 `FINAL` 的必经路径上。

第五个坑：**国内核心流量没有本地兜底**。

`大陆服务` 是一份 2.99MB 的远程清单。手机端下载或解析失败时不会报错，国内流量就直接掉到 `FINAL` 走代理，微信首当其冲。`LOCAL_SAFETY` 把 30 条最重要的国内域名（微信/QQ、阿里、腾讯云、百度、B站、字节、iCloud CN、12306、gov.cn）直接写进 `[filter_local]`，不依赖任何远程资源，等于给分流系统留了一条不会断的底线。

## 排查：国内站点也走代理、策略组不切换

症状：手机上看什么都是走当前选中的那个节点，`海外服务`/`大陆服务` 两个组形同不存在。

Qx 是**顺序匹配、命中即止**：国内域名先由 `大陆服务` 清单命中 → `static=大陆服务, direct` → 直连。所以只要那份清单没加载成功，国内流量就没有任何规则接住，一路掉到 `[filter_local]` 最后一条 `FINAL,海外服务`，全部走代理。

按这个顺序查：

0. **看「网络活动」里那条匹配标识**。这是最直接的证据：
   - `ALL, PROXY` → **一条规则都没命中**，Qx 掉到自己的默认策略了。不是「分流没切」，是整条规则链没接上。优先查第 3、4 条
   - `FINAL, 海外服务` → 兜底正常工作，问题只是某份分流清单没匹配到
   - `大陆服务` / `host-suffix, qq.com, 大陆服务` → 规则命中了，走的是对的
1. **看条数对账**。Qx → 风车 → 分流规则 → 下滑到「远程分流」，点开每项对比 [`reports/STATUS.md`](reports/STATUS.md) 里的**客户端对账表**。`大陆服务` 应为 79978 条。
   - 显示 0 / 报错 → 链接拿不到（用 `online_check.py` 验）
   - 显示明显偏少 → 拿到的是被截断的旧缓存，见第 3 条
2. **看策略组有没有成员**。Qx → 策略 → `海外服务` 里面应该能看到 `优选节点`/`香港服务`/`美国服务`，`优选节点` 里应该有一堆节点。空组 = 节点订阅没配上（`[server_remote]` 是空的，本仓库不托管节点）。
3. **强制刷新清单**。Qx 的「更新配置」只重新下载**已过期**的资源。本仓库已把所有镜像的 `update-interval` 统一成 86400（1 天），但如果你手上那份旧配置还是 172800（2 天），坏缓存最长要等两天才会被换掉。
   最快的办法：风车 → 配置文件 → 远程配置 → **删掉这条再重新添加**，资源会全部重下。
4. **确认 `FINAL` 在最后**。上游原配置把 `FINAL,海外服务` 写在了 `GEOIP,CN, DIRECT` 前面，导致 `GEOIP` 永远不可达。本仓库已把 `FINAL` 移到 `[filter_local]` 末条（`audit.py` 会检查这一点）。

## 自检脚本

改完配置想确认没搞坏，跑这三条：

```bash
python3 scripts/audit.py QuantumultX.conf           # 结构/语法/策略引用
python3 scripts/audit_sources.py QuantumultX.conf   # 镜像清单里的策略名是否真实存在
python3 scripts/verify_integrity.py                 # 镜像文件是否被截断（对比上游大小）
python3 scripts/online_check.py QuantumultX.conf    # 推到 GitHub 后是否真的拿得到
```

`verify_integrity.py` 是为了防一类特别隐蔽的故障：`Mainland.list` 有 2.99MB，早期版本读取时卡了 2MB 上限，结果**只下到 2MB、丢了 26,228 条国内直连规则**——HTTP 200、文件存在、Qx 也不报错，只是国内网站开始走代理。现在读取用 `r.read()` 不限长度，并校验 `Content-Length` 与实际字节数是否一致，不一致宁可判失败也不落盘残文件。

## 注意事项

- ⚠️ **更新配置会清空节点订阅**。本仓库的 `[server_remote]` 是空的（不托管任何节点），而 Qx 更新远程配置时是**整段覆盖**。更新后节点若消失，去 `[server_remote]` 把订阅重新加一次就行。`[server_local]` 里的手写单节点同理。
- **定时任务会被 GitHub 自动暂停**：仓库连续 60 天无提交活动，schedule 会被禁用。每周手动触发一次，或者给仓库随便提个 commit 就行。
- **定时不完全准点**：GitHub Actions 的 schedule 在高峰期会延迟几分钟到半小时，08:00 的任务可能 08:20 才跑完。
- **Qx 主配置不自动更新**：子规则和重写会按 `update-interval` 自动拉，但 Qx 的主 profile 需要在 App 里手动点一次「更新」。所以建议你现在配置里启用、之后每周手动更新一次即可。
- **镜像内容版权归原作者**，本仓库只是可用性中继，不做任何修改（除了改写链接和注释死链）。
