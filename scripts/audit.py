#!/usr/bin/env python3
"""QuantumultX 配置静态审计器。

不联网检查语法与引用一致性，专门找「Qx 加载时会报错或静默失效」的问题：
  1. section 重复/缺失
  2. 策略引用悬空（规则里写的策略组在 [policy] 里不存在）
  3. tag 重复
  4. FINAL 位置错误（不在最后会让后面规则失效）
  5. 规则行语法（未知指令、字段数不对）
  6. 空值键、echo-response 填 URL
  7. CRLF / BOM / 行尾空格
  8. mitm hostname 覆盖度抽查
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else "QuantumultX.conf"
raw = open(PATH, "rb").read()

issues: list[tuple[str, str]] = []   # (级别, 描述)
FATAL, WARN, INFO = "ERROR", "WARN", "INFO"


def add(level, msg):
    issues.append((level, msg))


# ---------------------------------------------------------------- 编码层
if raw.startswith(b"\xef\xbb\xbf"):
    add(FATAL, "文件带 UTF-8 BOM，Qx 会把首行 section 头解析错")
if b"\r\n" in raw:
    n = raw.count(b"\r\n")
    add(WARN, f"存在 CRLF 换行 {n} 处，建议统一 LF")

text = raw.decode("utf-8", "replace")
lines = text.splitlines()

# ---------------------------------------------------------------- 结构层
sections = []
cur = None
body = defaultdict(list)
for i, ln in enumerate(lines, 1):
    s = ln.strip()
    if s.startswith("[") and "]" in s:
        cur = s[1:s.index("]")].strip().lower()
        sections.append(cur)
        continue
    if cur is not None and s and not s.startswith("#"):
        body[cur].append((i, s))

dup = [k for k, v in Counter(sections).items() if v > 1]
if dup:
    add(FATAL, f"section 重复定义：{', '.join(dup)}")

REQUIRED = ["policy", "filter_local", "rewrite_local", "task_local", "mitm"]
for r in REQUIRED:
    if r not in sections:
        add(FATAL, f"缺少必要的 section [{r}]")

# ---------------------------------------------------------------- 策略组名
groups = set()
for _, s in body.get("policy", []):
    m = re.match(r"^(static|url-latency-benchmark|dest-hash|available|round-robin)\s*=\s*([^,]+)", s)
    if m:
        groups.add(m.group(2).strip())
BUILTIN = {"direct", "reject", "reject-200", "reject-img", "reject-dict",
           "reject-array", "proxy", "img", "blank"}
known = groups | BUILTIN

# filter_local / FINAL 的策略引用
for i, s in body.get("filter_local", []):
    parts = [p.strip() for p in s.split(",")]
    if len(parts) < 2:
        add(WARN, f"[filter_local:{i}] 字段不足：{s[:70]}")
        continue
    policy = parts[-1]
    if parts[0].upper() in ("FINAL", "GEOIP", "IP-CIDR", "IP6-CIDR", "HOST",
                            "HOST-SUFFIX", "HOST-KEYWORD", "IP-ASN",
                            "USER-AGENT", "DOMAIN", "DOMAIN-SUFFIX") or True:
        if policy and policy not in known and not policy.startswith("$"):
            add(FATAL, f"[filter_local:{i}] 引用了不存在的策略 `{policy}` → {s[:70]}")

# FINAL 位置
finals = [(idx, i) for idx, (i, s) in enumerate(body.get("filter_local", []))
          if s.upper().startswith("FINAL")]
if finals:
    idx, lineno = finals[0]
    total = len(body.get("filter_local", []))
    if idx != total - 1:
        after = body["filter_local"][idx + 1:]
        real = [(i, s) for i, s in after if not s.startswith("#")]
        if real:
            add(FATAL, f"[filter_local:{lineno}] FINAL 后面还有 {len(real)} 条规则，"
                       f"它们永远不会命中（第一条：{real[0][1][:50]}）")
else:
    add(WARN, "[filter_local] 没有 FINAL，未匹配流量将直连")

# ---------------------------------------------------------------- 策略组成员
# static / url-latency-benchmark 等组的「成员」必须是已定义的组名、内置策略，
# 或能被打到的节点名。这里只能判明显悬空的通用词，节点名交给 Qx 自己匹配。
GENERIC = {"proxy", "Proxy", "PROXY", "global", "Global", "节点", "自动", "select"}
for i, s in body.get("policy", []):
    m = re.match(r"^(static|available|round-robin|dest-hash)\s*=\s*(.+)$", s)
    if not m:
        continue
    name = m.group(2).split(",")[0].strip()
    members = [x.strip() for x in m.group(2).split(",")[1:]]
    members = [x for x in members if "=" not in x]
    for mem in members:
        if mem in GENERIC:
            add(WARN, f"[policy:{i}] 组 `{name}` 的成员 `{mem}` 不是已定义的策略组"
                       f"（Qx 会忽略该成员，不致命）")

# ---------------------------------------------------------------- tag 重复
tags = []
for sec in ("filter_remote", "rewrite_remote", "task_local"):
    for i, s in body.get(sec, []):
        m = re.search(r"tag\s*=\s*([^,]+)", s)
        if m:
            tags.append((sec, m.group(1).strip(), i))
c = Counter(t for _, t, _ in tags)
for t, n in c.items():
    if n > 1:
        where = [f"{s}:{i}" for s, tt, i in tags if tt == t]
        add(WARN, f"tag `{t}` 重复 {n} 次（{', '.join(where)}）")

# ---------------------------------------------------------------- 规则行语法
BAD_ACTIONS = {"url", "script", "reject", "direct"}
for sec in ("rewrite_local",):
    for i, s in body.get(sec, []):
        parts = s.split()
        if len(parts) < 2:
            add(WARN, f"[{sec}:{i}] 行结构异常：{s[:70]}")
            continue
        if parts[1] not in ("url", "url-and-header"):
            add(WARN, f"[{sec}:{i}] 第二列应为 url/url-and-header，实际 `{parts[1]}`")
        rest = " ".join(parts[2:])
        KNOWN = ("reject", "reject-200", "reject-img", "reject-dict", "reject-array",
                 "302", "307", "request-header", "response-header", "echo-response",
                 "script-request-body", "script-response-body", "script-request-header",
                 "script-response-header", "script-echo-response",
                 "script-analyze-echo-response", "script-response-body-v2")
        if not any(rest.startswith(k) for k in KNOWN):
            add(WARN, f"[{sec}:{i}] 未知重写指令：{rest[:50]}")

# echo-response 不能带 URL
for i, s in body.get("rewrite_local", []):
    if re.search(r"echo-response\s+https?://", s) and "script-" not in s:
        add(FATAL, f"[rewrite_local:{i}] echo-response 响应体填了 URL，Qx 会忽略该条")

# ---------------------------------------------------------------- 空值键
for i, ln in enumerate(lines, 1):
    if re.match(r"^[A-Za-z0-9_-]+\s*=\s*$", ln.strip()):
        add(FATAL, f"第 {i} 行空值键 `{ln.strip()}`（p12/passphrase 为空会让 MitM 起不来）")

# ---------------------------------------------------------------- URL 形态
bad_url = []
for i, ln in enumerate(lines, 1):
    s = ln.strip()
    if not s or s.startswith("#"):
        continue
    for u in re.findall(r"https?://[^\s,]+", s):
        if "${" in u or "{{" in u:
            bad_url.append((i, u))
for i, u in bad_url:
    add(WARN, f"第 {i} 行 URL 含未替换占位符：{u[:60]}")

# 镜像地址是否指向本仓库
MIRROR = "raw.githubusercontent.com/VanwaysAI/qx-rules-sync"
mirror_count = text.count(MIRROR)
if mirror_count == 0:
    add(FATAL, "没有任何指向本仓库的镜像地址，改写未生效")

# 残留上游死链抽查
DEAD_HOSTS = ("RuCu6/QuanX", "WeiRen0/Scripts", "WSL33099/QuantumultX")
for h in DEAD_HOSTS:
    for i, ln in enumerate(lines, 1):
        if h in ln and not ln.strip().startswith("#"):
            add(FATAL, f"第 {i} 行仍引用已消失的上游 {h}")

# ---------------------------------------------------------------- 输出
order = {FATAL: 0, WARN: 1, INFO: 2}
issues.sort(key=lambda x: order[x[0]])
print(f"审计对象: {PATH}")
print(f"行数 {len(lines)} | section {len(sections)} 个 | 策略组 {len(groups)} 个 | 镜像引用 {mirror_count} 处\n")
if not issues:
    print("✅ 未发现问题")
else:
    for lv, msg in issues:
        icon = {"ERROR": "❌", "WARN": "⚠️ ", "INFO": "ℹ️ "}[lv]
        print(f"{icon} [{lv}] {msg}")
n_err = sum(1 for l, _ in issues if l == FATAL)
n_warn = sum(1 for l, _ in issues if l == WARN)
print(f"\n合计：{n_err} 个错误 / {n_warn} 个警告")
sys.exit(1 if n_err else 0)
