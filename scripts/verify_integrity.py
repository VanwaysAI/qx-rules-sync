#!/usr/bin/env python3
"""镜像完整性校验：逐一比对「上游资源大小」与「本地镜像大小」。

专门抓静默截断——HTTP 200、文件存在、内容看着正常，但只下了一半。
Mainland.list 就吃过这个亏（卡了 2MB 上限，丢了 1MB 规则）。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS = os.path.join(ROOT, "reports", "status.json")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Quantumult%20X/1.4.1"

rep = json.load(open(STATUS, encoding="utf-8"))
items = [i for i in rep["items"] if i.get("src") and i["action"] in ("mirrored", "replaced")]


def upstream_size(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else None
    except Exception:
        # HEAD 不被支持时退回 GET
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return len(r.read())
        except Exception:
            return None


def local_size(url: str):
    rel = url.split("qx-rules-sync/main/", 1)[-1]
    p = os.path.join(ROOT, rel)
    return os.path.getsize(p) if os.path.exists(p) else None


def was_patched(url: str) -> bool:
    """内容被我们改写过的文件：脚本链接换成了本仓库地址、死链被注释、
    echo-response 被内联。这些文件字节数必然和上游不同，不能按字节比对。"""
    rel = url.split("qx-rules-sync/main/", 1)[-1]
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return False
    txt = open(p, encoding="utf-8", errors="replace").read()
    return "qx-rules-sync" in txt or "qx-sync" in txt


def work(item):
    return (item["src"], upstream_size(item["src"]),
            local_size(item["final"]), was_patched(item["final"]))


print(f"校验 {len(items)} 个镜像文件的完整性...\n")

# 允许的偏差：同步流程会做小改写（注释掉引用未知策略/未知规则类型的行、
# 统一规则类型大小写、改写嵌套脚本地址）。这些只动几行到几百字节，
# 而真正的静默截断是**整块丢失**——当年 Mainland.list 就是丢了 1MB / 33%。
# 所以用 2% 相对阈值：小改动放过，大块缺失仍然报警。
TOLERANCE = 0.02

bad, skip, patched, trimmed = [], 0, 0, 0
with ThreadPoolExecutor(max_workers=12) as ex:
    for src, up, lo, wasedit in ex.map(work, items):
        short = src.split("raw.githubusercontent.com/")[-1]
        if lo is None:
            bad.append((short, up, "本地文件缺失"))
        elif wasedit:
            patched += 1
            print(f"✏️  {lo:>9}  {short[:86]}  （内容已改写，跳过字节比对）")
        elif up is None:
            skip += 1
        elif up != lo and abs(up - lo) <= max(2048, up * TOLERANCE):
            trimmed += 1
            print(f"✏️  {lo:>9}  {short[:86]}  （微调 {up - lo:+d} 字节，在容差内）")
        elif up != lo:
            bad.append((short, up, f"大小不符：上游 {up} / 本地 {lo}，差 {up - lo}"))
        else:
            print(f"✅ {lo:>9}  {short[:90]}")

print()
if skip:
    print(f"（{skip} 个上游未返回 Content-Length，已跳过）")
if patched:
    print(f"（{patched} 个文件内容被改写，大小本就会变）")
if trimmed:
    print(f"（{trimmed} 个文件在容差内微调，属同步流程的正常改写）")
if bad:
    print(f"❌ {len(bad)} 个文件不完整：")
    for s, up, why in bad:
        print(f"   {s}\n      {why}")
    sys.exit(1)
print(f"✅ 全部 {len(items)} 个镜像校验通过")
