# QuantumultX 配置体检报告

- 上次同步：`2026-10-25 10:33:29 +0800`（北京时间）
- 上游配置：https://raw.githubusercontent.com/Moli-X/Resources/main/Rewrite/QuantumultX.conf
- 资源总数 **90** ｜ 可用 **83** ｜ 失效 **7**

## 已清理的「未知策略」规则

远程清单里有规则指向了配置中并不存在的策略组。Qx 遇到这种行最坏会让**整份清单加载失败**——而这份清单如果是大陆直连表，后果就是全部流量掉到 FINAL 兜底组走代理。已注释掉这些行：

- 涉及策略名：`proxy`

## 已停用的 echo-response 规则

Qx 的 `echo-response` 正文只要是 URI 就拒绝（`https://` 和 `data:` 都算），只认 Qx 沙盒里的本地文件 —— 远程配置没法往用户手机里分发文件，所以这类规则无解，已整条注释：

- ❌ 已停用 · `https://raw.githubusercontent.com/Keywos/rule/main/mocks/caiyun.json`
  - Qx 不接受 URL / data URI 作响应体，远程配置无法提供本地文件，整条注释（损失：该 App 的 mock 去广告）

## 已移除的空值配置项

上游留了值为空的占位符，Qx 会把它当成「我要用自定义证书」从而报 `MitM 错误的 p12 或 p12 passphrase`。以下行已从生成配置中删除：

- `passphrase =`
- `p12 =`

## 死链已自动修复

| 原地址（已死） | 替换为 |
|---|---|
| `https://github.com/ddgksf2013/Rewrite/raw/master/AdBlock/Cainiao.conf` | `https://raw.githubusercontent.com/ddgksf2013/Rewrite/master/AdBlock/CainiaoAds.conf` |
| `https://raw.githubusercontent.com/Maasea/sgmodule/master/YoutubeAds.sgmodule` | `https://raw.githubusercontent.com/Maasea/sgmodule/master/YouTube.Enhance.sgmodule` |
| `https://raw.githubusercontent.com/Peng-YM/Sub-Store/master/backend/dist/cron-sync-artifacts.min.js` | `https://raw.githubusercontent.com/sub-store-org/Sub-Store/release/cron-sync-artifacts.min.js` |
| `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/cnftp.js` | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/cnftp.js` |
| `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/fenbi.js` | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/fenbi.js` |
| `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/ithome.js` | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/ithome/ithome.js` |
| `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/myBlockAds.js` | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/myBlockAds.js` |
| `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/break/kuwo.js` | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/kuwo/kuwo.js` |
| `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/weibo.js` | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/weibo/weibo_ads.js` |
| `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/xmly_json.js` | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/xmly/xmly_json.js` |

## 额外追加的规则源（上游配置原本没有）

- ✅ **filter_remote** · 插在最前 · 最高优先级 · `https://raw.githubusercontent.com/fmz200/wool_scripts/main/QuantumultX/filter/filterFix.list`
  - 63 条 direct 修正，把被误分到外区的国内站点拉回直连。必须最高优先级，否则被 ADBlack 的 reject 抢先命中。
- ✅ **filter_remote** · 追加到末尾 · 最低优先级 · `https://raw.githubusercontent.com/fmz200/wool_scripts/main/QuantumultX/filter/filter.list`
  - 2787 条 reject 广告拦截，作为 ADBlack 的补充。放最后，不干扰已有分流。

## 客户端对账表（排查「国内也走代理」用）

Qx → 风车 → 分流规则 → 下滑到「远程分流」，点开每项看条数。**和下表对不上就说明那份清单没加载成功**，对应分流会整体掉到 `FINAL,海外服务` 走代理，表现就是「全都走节点、不切组」。

| 远程分流 | 应有条数 |
|---|---|
| 分流修正 | **62** |
| 广告名单 | **9518** |
| 微信转圈 | **341** |
| 海外服务 | **2869** |
| 大陆服务 | **79978** |
| 油管分流 | **180** |
| 广告增强 | **2761** |

> 特别注意 `大陆服务`：它要是显示 0 或远小于上表数字，国内站点就会全部走代理。

> 另外看「网络活动」第三行的匹配标识：显示 `ALL, PROXY` 多半是 **Qx 处在「全部代理」模式**（`ALL` = 全部流量不经规则，`PROXY` = Qx 内置代理策略），此时分流规则完全不参与判断，先切回「规则代理」再说；显示 `final, 海外服务` 才是规则生效且兜底正常。

## 失效清单（配置中已注释，不再拖慢 Qx）

| 状态 | 类型 | 地址 | 说明 |
|---|---|---|---|
| 超时 | remote | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Rewrites/Cube/amap.snippet` | 在 drop 名单（上游仓库已删除/封禁） |
| 超时 | remote | `https://raw.githubusercontent.com/WeiRen0/Scripts/main/ZHVIP.js` | 在 drop 名单（上游仓库已删除/封禁） |
| 超时 | remote | `https://raw.githubusercontent.com/WeiRen0/Scripts/main/wxds.js` | 在 drop 名单（上游仓库已删除/封禁） |
| 超时 | script | `https://raw.githubusercontent.com/chouchoui/QuanX/master/Scripts/testflight/Auto_join_TF.js` | 在 drop 名单（上游仓库已删除/封禁） |
| 超时 | script | `https://raw.githubusercontent.com/WSL33099/QuantumultX/main/Script/JD/ClCart.js` | 在 drop 名单（上游仓库已删除/封禁） |
| 404 | script | `https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/script/smzdm/smzdm_remove_ads.js` | 404 不存在 |
| 超时 | script | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/zhihu.js` | 在 drop 名单（上游仓库已删除/封禁） |

## 全部资源

<details><summary>展开明细</summary>

| 状态 | 动作 | 地址 |
|---|---|---|
| DEAD | drop | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Rewrites/Cube/amap.snippet` |
| DEAD | drop | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/zhihu.js` |
| DEAD | drop | `https://raw.githubusercontent.com/WSL33099/QuantumultX/main/Script/JD/ClCart.js` |
| DEAD | drop | `https://raw.githubusercontent.com/WeiRen0/Scripts/main/ZHVIP.js` |
| DEAD | drop | `https://raw.githubusercontent.com/WeiRen0/Scripts/main/wxds.js` |
| DEAD | drop | `https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/script/smzdm/smzdm_remove_ads.js` |
| DEAD | drop | `https://raw.githubusercontent.com/chouchoui/QuanX/master/Scripts/testflight/Auto_join_TF.js` |
| OK | mirrored | `https://github.com/Moli-X/Resources/raw/main/Script/Nicegram.js` |
| OK | mirrored | `https://github.com/Moli-X/Resources/raw/main/Script/Xiaohongshu.js` |
| OK | mirrored | `https://github.com/NobyDa/Script/raw/master/Surge/WeChat.list` |
| OK | replaced | `https://github.com/ddgksf2013/Rewrite/raw/master/AdBlock/Cainiao.conf` |
| OK | mirrored | `https://github.com/ddgksf2013/Scripts/raw/master/douban.js` |
| OK | mirrored | `https://github.com/ddgksf2013/Scripts/raw/master/pornhub.js` |
| OK | mirrored | `https://github.com/sub-store-org/Sub-Store/releases/latest/download/sub-store-0.min.js` |
| OK | mirrored | `https://github.com/sub-store-org/Sub-Store/releases/latest/download/sub-store-1.min.js` |
| OK | mirrored | `https://raw.githubusercontent.com/ChuheGit/1/main/Script/jd_scripts/jd_bean_change.js` |
| OK | mirrored | `https://raw.githubusercontent.com/ChuheGit/1/main/Script/jd_scripts/jd_unsubscribe.js` |
| OK | mirrored | `https://raw.githubusercontent.com/I-am-R-E/Functional-Store-Hub/Master/NodeLinkCheck/Script/NodeLinkCheck.js` |
| OK | mirrored | `https://raw.githubusercontent.com/I-am-R-E/QuantumultX/main/JavaScript/DouBan.js` |
| OK | mirrored | `https://raw.githubusercontent.com/I-am-R-E/QuantumultX/main/TaskLocal/NeteaseMusicUnlockCheck.js` |
| OK | mirrored | `https://raw.githubusercontent.com/KOP-XIAO/QuantumultX/master/Scripts/nf-ui-check.js` |
| OK | mirrored | `https://raw.githubusercontent.com/KOP-XIAO/QuantumultX/master/Scripts/ytb-ui-check.js` |
| OK | replaced | `https://raw.githubusercontent.com/Maasea/sgmodule/master/YoutubeAds.sgmodule` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Filter/ADBlack.list` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Filter/Mainland.list` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Filter/Overseas.list` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Filter/YouTube.list` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Rewrite/ADBlock.conf` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Rewrite/Collections.conf` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Rewrite/Cookie.conf` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Rewrite/Search.conf` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Rewrite/TikTok/TikTok-US.conf` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Rewrite/XHS.conf` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Script/Bilibili/AD_Bilibili.conf` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Script/Bilibili/TPBilibili.js` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Script/Bilibili/ZLBilibili.js` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Script/Bilibili/ZMBilibili.js` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Script/Bilibili/bilibili_json.js` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Script/MTxiuxiu/MTxiuxiu.js` |
| OK | mirrored | `https://raw.githubusercontent.com/Moli-X/Resources/main/Script/MTxiuxiu/MeiTu.js` |
| OK | mirrored | `https://raw.githubusercontent.com/Neurogram-R/Quantumult-X/main/Dualsub.js` |
| OK | mirrored | `https://raw.githubusercontent.com/NobyDa/Script/master/Bahamut/BahamutAnimeAds.js` |
| OK | mirrored | `https://raw.githubusercontent.com/NobyDa/Script/master/JD-DailyBonus/JD_DailyBonus.js` |
| OK | mirrored | `https://raw.githubusercontent.com/NobyDa/Script/master/QuantumultX/File/xjsp.js` |
| OK | mirrored | `https://raw.githubusercontent.com/NobyDa/Script/master/TestFlight/TestFlightAccount.js` |
| OK | replaced | `https://raw.githubusercontent.com/Peng-YM/Sub-Store/master/backend/dist/cron-sync-artifacts.min.js` |
| OK | replaced | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/break/kuwo.js` |
| OK | replaced | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/cnftp.js` |
| OK | replaced | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/fenbi.js` |
| OK | replaced | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/ithome.js` |
| OK | replaced | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/myBlockAds.js` |
| OK | replaced | `https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/weibo.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/js/adsense.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/js/qidian.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/js/qq-news.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/js/spotify-json.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/js/spotify-proto.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/js/tieba-json.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/js/tieba-proto.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/js/vgtime.js` |
| OK | mirrored | `https://raw.githubusercontent.com/app2smile/rules/master/module/youtube.sgmodule` |
| OK | mirrored | `https://raw.githubusercontent.com/chavyleung/scripts/master/box/chavy.boxjs.js` |
| OK | mirrored | `https://raw.githubusercontent.com/chavyleung/scripts/master/box/scripts/boxjs.revert.usercfgs.httpbackend.js` |
| OK | mirrored | `https://raw.githubusercontent.com/ddgksf2013/Scripts/refs/heads/master/amdc.js` |
| OK | mirrored | `https://raw.githubusercontent.com/ddgksf2013/Scripts/refs/heads/master/cainiao_json.js` |
| OK | mirrored | `https://raw.githubusercontent.com/dompling/Script/master/jd/jd_cookie_search.js` |
| OK | mirrored | `https://raw.githubusercontent.com/evilbutcher/Quantumult_X/master/check_in/appstore/AppMonitor.js` |
| OK | mirrored | `https://raw.githubusercontent.com/evilbutcher/Quantumult_X/master/check_in/hzh/hzh.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/QuantumultX/filter/filter.list` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/QuantumultX/filter/filterFix.list` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/QuantumultX/scripts/Flightradar24.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/51card.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/555Ad.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/amdc.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/coolapk.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/fly.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/jingxiAd.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/quark.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/reddit.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/rrtv_json.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/soda.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/soul/soul_ads.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/stay.js` |
| OK | mirrored | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/xiaotucc.js` |
| OK | replaced | `https://raw.githubusercontent.com/fmz200/wool_scripts/main/Scripts/xmly_json.js` |
| OK | mirrored | `https://raw.githubusercontent.com/id77/QuantumultX/master/task/jdWuLiu.js` |
| OK | mirrored | `https://raw.githubusercontent.com/kokoryh/Script/master/js/12306.js` |
| OK | mirrored | `https://raw.githubusercontent.com/sub-store-org/Sub-Store/master/scripts/revert.js` |
| OK | mirrored | `https://raw.githubusercontent.com/unknowntokyo/surge-list/master/X/dns-clear-cache.js` |
| OK | mirrored | `https://raw.githubusercontent.com/zZPiglet/Task/master/asset/UnblockURLinWeChat.js` |

</details>

## 怎么用

Quantumult X → 风车 → 配置文件 → 远程配置 → 添加：

```
https://raw.githubusercontent.com/VanwaysAI/qx-rules-sync/main/QuantumultX.conf
```

然后把节点订阅填进 `[server_remote]`（本仓库不托管任何节点）。
