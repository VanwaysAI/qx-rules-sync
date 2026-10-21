#!/usr/bin/env python3
"""检查 Sources/ 下镜像的规则清单：策略列引用的策略是否真实存在。

主配置审计（audit.py）看不到 list 文件内部，而策略名写错会让整批规则静默失效。
用法: python audit_sources.py QuantumultX.conf
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, sys.argv[1] if len(sys.argv) > 1 else "QuantumultX.conf")

text = open(CONF, encoding="utf-8").read()

# 已定义的策略组
groups = set()
for m in re.finditer(r"^(?:static|url-latency-benchmark|available|round-robin|dest-hash)\s*=\s*([^,\n]+)",
                     text, re.M):
    groups.add(m.group(1).strip())
BUILTIN = {"direct", "reject", "reject-200", "reject-img", "reject-dict",
           "reject-array", "proxy", "no-resolve", "img"}
known = groups | BUILTIN

# 被引用的镜像清单：只取 [filter_remote] 段（rewrite_remote 里是规则不是策略）
refs = []
section = ""
for ln in text.splitlines():
    s = ln.strip()
    if s.startswith("[") and "]" in s:
        section = s[1:s.index("]")].strip().lower()
        continue
    if section != "filter_remote" or not s or s[0] in "#;":
        continue
    m = re.match(r"^(https?://\S+?),\s*tag=([^,]+)(.*)$", s)
    if not m:
        continue
    fp = re.search(r"force-policy=([^,\s]+)", m.group(3))
    refs.append((m.group(1), m.group(2).strip(), fp.group(1) if fp else None))

print(f"策略组：{', '.join(sorted(groups))}")
print(f"清单引用：{len(refs)} 条\n")

problems = 0
for url, tag, force in refs:
    rel = url.split("qx-rules-sync/main/", 1)[-1]
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        print(f"⚠️  {tag}: 镜像文件缺失 {rel}")
        problems += 1
        continue
    policies = Counter()
    for ln in open(path, encoding="utf-8", errors="replace"):
        s = ln.strip()
        if not s or s[0] in "#;" or s.startswith("["):
            continue
        if s.startswith("hostname") or s.startswith("//"):
            continue
        parts = [p.strip() for p in s.split(",")]
        if len(parts) < 2:
            continue
        last = parts[-1]
        # 两列格式（依赖 force-policy）不算策略名
        if force:
            continue
        if last.lower() == "no-resolve" and len(parts) >= 3:
            last = parts[-2]
        if re.match(r"^[\d.:]+/\d+$", last) or last.replace(".", "").isdigit():
            continue
        if last in ("", "no-resolve"):
            continue
        policies[last] += 1

    unknown = {p: n for p, n in policies.items() if p not in known}
    status = "✅" if not unknown else "❌"
    detail = "、".join(f"{p}×{n}" for p, n in sorted(unknown.items(), key=lambda x: -x[1])[:4])
    print(f"{status} {tag:<12} 策略 {dict(policies) if len(policies) <= 3 else str(len(policies)) + ' 种'}"
          + (f"  ← 未知：{detail}" if unknown else ""))
    if unknown:
        problems += 1

print(f"\n{'全部策略名有效' if problems == 0 else f'{problems} 个清单存在未知策略名'}")
sys.exit(1 if problems else 0)
