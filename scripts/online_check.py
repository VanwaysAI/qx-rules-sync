#!/usr/bin/env python3
"""线上可达性检查：把生成配置里引用的每一个镜像地址都实际请求一遍。

与 sync.py 的区别：sync 检查的是**上游**，这里检查的是**我们推到 GitHub 上之后**
是否真的拿得到——覆盖 push 失败、文件没提交、路径算错这类问题。
"""
from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, sys.argv[1] if len(sys.argv) > 1 else "QuantumultX.conf")
text = open(CONF, encoding="utf-8").read()

URLS = sorted({u.rstrip(".,;")
               for u in re.findall(r"https?://[^\s,)\x22']+", text)
               if "qx-rules-sync" in u})
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Quantumult%20X/1.4.1"


def check(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(300_000)
            head = body[:400].lstrip().lower()
            soft = head.startswith(b"<!doctype html") or head.startswith(b"<html")
            return url, r.status, len(body), soft
    except urllib.error.HTTPError as e:
        return url, e.code, 0, False
    except Exception as e:
        return url, 0, 0, type(e).__name__


print(f"检查 {len(URLS)} 个镜像地址（线上）...\n")
bad = []
with ThreadPoolExecutor(max_workers=16) as ex:
    for url, code, size, flag in ex.map(check, URLS):
        ok = code == 200 and size > 0 and not flag
        if not ok:
            bad.append((url, code, flag))
        short = url.split("qx-rules-sync/main/")[-1]
        print(f"{'✅' if ok else '❌'} {code:>3}  {size:>8}  {short[:88]}")

print()
if bad:
    print(f"❌ {len(bad)} 个地址不可用：")
    for u, c, f in bad:
        print(f"   [{c}] {u}")
    sys.exit(1)
print(f"✅ 全部 {len(URLS)} 个镜像地址在线可用")
