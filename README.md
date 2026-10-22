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

第三个坑：**规则类型大小写混用**。

官方 `sample.conf` 与全部官方文档只写小写（`final` / `geoip` / `host-suffix`），从不出现 `FINAL` / `GEOIP` / `HOST-SUFFIX`。上游两处都写成了大写：

- 主配置 `[filter_local]`：`FINAL,海外服务`、`GEOIP,CN, DIRECT`
- 分流清单：`HOST-SUFFIX` 69235 条大写，小写只 18 条

**Qx 到底区不区分大小写，我没有一手证据能定论**（官方文档不写，两种说法都有）。本仓库统一转小写的理由很单纯：小写是官方唯一写法，无论 Qx 怎么实现都必然正确，属于零风险规范化。

> 别再把它当成「所有流量走代理」的成因了——那个症状的真凶是 App 处在**「全部代理」模式**，见下一节。

第四个坑（**防御性处理，未经证实**）：兜底策略组可能有空成员。

```ini
static=海外服务, 优选节点, 香港服务, 美国服务
final, 海外服务
```

`香港服务` / `美国服务` 是 `url-latency-benchmark` + 正则，靠节点名匹配。如果订阅里没有港/美节点（比如只有新加坡和日本），这两个组就是空的。空组会不会连带让 `海外服务` 失效、进而让 `final` 指空——**没验证过**。

`harden_policy_groups()` 把兜底链上的 `static` 组收缩成单一成员 `优选节点`（正则是 `^(?!.*网易云)`，匹配所有非网易云节点，必定非空）。`香港服务` / `美国服务` 仍然保留，只是不再挂在 `final` 的必经路径上。这一步不改变任何实际能力（`优选节点` 本来就包含全部节点），只是把兜底路径上的不确定因素去掉。

第五个坑（**防御性处理**）：国内核心流量没有本地兜底。

`大陆服务` 是一份 2.99MB 的远程清单。手机端下载或解析失败时不会报错，国内流量就直接掉到 `final` 走代理，微信首当其冲。`LOCAL_SAFETY` 把 30 条最重要的国内域名（微信/QQ、阿里、腾讯云、百度、B站、字节、iCloud CN、12306、gov.cn）直接写进 `[filter_local]`，不依赖任何远程资源，等于给分流系统留了一条不会断的底线。

## 排查：所有流量都走同一个节点、国内也走线路

症状：手机上看什么都是走当前选中的那个节点，`海外服务`/`大陆服务` 两个组形同不存在。

### 第 0 步（必查）：Qx 是不是「全部代理」模式

**在动配置之前，先看 Qx 主界面的运行模式。**

Qx 有三档：`全部直连` / `规则代理` / `全部代理`。在**「全部代理」**下，**分流规则完全不参与判断**，所有流量直接丢给内置 `PROXY` 策略——配置文件写得再对也没用。

这个坑的真实案例：本人排查了三轮配置，改清单、改策略组、改规则类型大小写，全都没用；最后发现是 App 处在「全部代理」模式，切成「规则代理」立刻正常。**配置一行没改。**

「网络活动」里的表现就是每条连接第三行都显示 **`ALL, PROXY`**：

- `ALL` = 全部流量（不经规则匹配）
- `PROXY` = Qx 三大**内置策略**之一（`DIRECT` 直连 / `PROXY` 代理 / `REJECT` 阻止），不是你配置里的任何策略组

所以看到 `ALL, PROXY`，第一反应应该是**模式错了**，而不是配置错了。

对照表：

| 第三行显示 | 含义 |
|---|---|
| `ALL, PROXY` | **全部代理模式**（或规则全部失效），规则不参与判断 |
| `final, 海外服务` | 规则代理模式 + 兜底正常，只是这份请求没被具体清单匹配 |
| `host-suffix, qq.com, 大陆服务` | 规则命中且走对了 |

### 规则类型：统一成官方小写（防御性，非上述症状的成因）

官方 `sample.conf` 与全部官方文档里规则类型只出现小写：`final, …`、`geoip, cn, direct`、`host-suffix, …`。

有资料称 Qx 的类型识别不区分大小写，也有资料称区分——**这一点我没有一手证据能定论**。本仓库统一转小写的原因是：小写是官方唯一写法，无论 Qx 是否区分大小写都必然正确，属于零风险的规范化。转换范围：

- `[filter_local]`：`FINAL`→`final`、`GEOIP`→`geoip`（地区码 `CN`→`cn`）、`IP-ASN`→`ip-asn`
- 所有远程清单：`HOST-SUFFIX`→`host-suffix` 等，累计 92707 条
- Surge 专有的 `domain` / `domain-suffix` / `domain-keyword` 映射为 Qx 的 `host` / `host-suffix` / `host-keyword`；无法识别的类型注释并标记 `[qx-sync 未知规则类型]`

`normalize_main_filter_types()` 负责 `[filter_local]`，`normalize_rule_types()` 负责所有远程清单，两者都把类型统一成官方小写写法（`geoip` 的地区码也一并转小写）。

### 另外两条容易踩的 Qx 规则

**1. 本地规则永远排在远程规则前面。** 官方文档明确：本地规则总是位于远程规则之前，`final` 除外（永远最后）。所以 `[filter_local]` 里的规则优先级最高；想让某份远程清单插到本地规则前面，得给它加 `inserted-resource=true`。

**2.「分流匹配优化」会改变匹配顺序。** Qx 默认开启，此时类型优先级为
`host > host-suffix > host-wildcard > host-keyword > user-agent > ip-cidr/geoip`，
**不是**纯书写顺序。要严格按顺序匹配，去「设置 → 其他设置 → VPN → 分流匹配优化」关掉。

### 排查顺序

0. **看「网络活动」第三行**：`ALL, PROXY` → 按上面三条查；`final, 海外服务` → 兜底正常，问题在别处
1. **看条数对账**。Qx → 风车 → 分流规则 → 下滑到「远程分流」，点开每项对比 [`reports/STATUS.md`](reports/STATUS.md) 里的**客户端对账表**。`大陆服务` 应为 79978 条。
   - 显示 0 / 报错 → 链接拿不到（用 `online_check.py` 验）
   - 显示明显偏少 → 拿到的是被截断的旧缓存，见第 3 条
2. **看策略组有没有成员**。Qx → 策略 → `海外服务` 里应能看到 `优选节点`。空组 = 节点订阅没配上（`[server_remote]` 是空的，本仓库不托管节点）。
3. **强制刷新清单**。Qx 的「更新配置」只重新下载**已过期**的资源。本仓库已把所有镜像 `update-interval` 统一成 86400（1 天，官方 sample 的默认值也是 86400），但旧配置里可能是 172800（2 天），坏缓存最长要等两天。
   最快的办法：风车 → 配置文件 → 远程配置 → **删掉这条再重新添加**。
4. **确认 `final` 是最后一条**。写在 `final` 之后的本地规则全部无效（官方文档原话）。

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
