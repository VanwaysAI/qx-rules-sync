#!/usr/bin/env python3
"""QuantumultX 配置校验同步器。

做的事：
  1. 拉上游主配置
  2. 并发探测它引用的每一个外部资源（远程列表 / 远程 rewrite / 脚本 / 图标）
  3. 存活的 → 下载镜像到 Sources/，配置里的链接改写成本仓库地址
  4. 失效的 → 先查 config/overrides.json 找替代源，找不到就注释，全部记入报告
  5. 生成 QuantumultX.conf（可直接导入 Qx）+ reports/STATUS.md

原则：绝不静默丢功能。每一条被注释的规则都会出现在报告里。
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import hashlib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config", "upstream.json"), encoding="utf-8"))
OVR = json.load(open(os.path.join(ROOT, "config", "overrides.json"), encoding="utf-8"))

REPLACE = OVR.get("replace", {})
DROP = set(OVR.get("drop", []))

_add_path = os.path.join(ROOT, "config", "additions.json")
ADDITIONS = json.load(open(_add_path, encoding="utf-8")) if os.path.exists(_add_path) else {}

RAW_BASE = CFG["raw_base"].rstrip("/") + "/"
MIRROR_SECTIONS = set(CFG["mirror_sections"])
SCRIPT_SECTIONS = set(CFG["script_sections"])
MIRROR_SCRIPTS = CFG.get("mirror_scripts", True)
MIRROR_ICONS = CFG.get("mirror_icons", False)
STRIP_EMPTY_KEYS = {k.lower() for k in CFG.get("strip_empty_keys", [])}
PROBE = CFG.get("probe", {})
TIMEOUT = PROBE.get("timeout", 25)
RETRIES = PROBE.get("retries", 2)
WORKERS = 24

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Quantumult%20X/1.4.1 qx-sync/2.0"
URL_RE = re.compile(r"https?://[^\s,)\]\x22'|]+")
SCRIPT_KEYS = (
    "script-response-body", "script-request-body", "script-response-header",
    "script-request-header", "script-analyze-echo-response",
    "script-echo-response", "script-response-body-v2",
)

ITEMS: list[dict] = []
REPLACED: list[dict] = []
STRIPPED: list[str] = []
ECHO_FIXES: list[dict] = []
DEAD_ICONS: list[str] = []
DECISION: dict[str, dict] = {}


# ---------------------------------------------------------------- 网络

def http_get(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(2_000_000)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def looks_like_html(body: bytes) -> bool:
    """软 404：CDN 常把错误页以 200 返回。js/list/conf 不可能是 HTML 文档。"""
    head = body[:800].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def probe(url: str) -> tuple[bool, int, bytes]:
    """(可用, 状态码, 内容)。带重试抗抖动，硬错误立即放弃。"""
    last = 0
    for _ in range(RETRIES + 1):
        code, body = http_get(url)
        last = code
        if code == 200:
            if not body or looks_like_html(body):
                return False, 200, b""
            return True, 200, body
        if code in (401, 403, 404, 410, 451):
            return False, code, b""
    return False, last, b""


# ---------------------------------------------------------------- 路径

def mirror_path(url: str) -> str:
    p = urlparse(url)
    path = p.path.lstrip("/")
    host = p.netloc
    rel = path if host == "raw.githubusercontent.com" else f"{host}/{path}"
    rel = re.sub(r"[^\w\-./]", "_", rel).replace("/refs/heads/", "/")
    rel = re.sub(r"_{2,}", "_", rel).strip("/")
    if not rel or rel.endswith("/"):
        rel += "index.txt"
    if len(rel) > 170:
        stem, ext = os.path.splitext(rel)
        rel = stem[:140] + "-" + hashlib.sha1(url.encode()).hexdigest()[:8] + ext
    return "Sources/" + rel


def mirror_url(url: str) -> str:
    return RAW_BASE + mirror_path(url)


def save(path: str, body: bytes) -> None:
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if os.path.exists(full) and open(full, "rb").read() == body:
        return
    with open(full, "wb") as f:
        f.write(body)


def read_mirror(url: str) -> str:
    full = os.path.join(ROOT, mirror_path(url))
    if os.path.exists(full):
        return open(full, encoding="utf-8", errors="replace").read()
    return ""


# ---------------------------------------------------------------- 解析

def line_resource(section: str, body: str) -> tuple[str, str] | None:
    """一行里哪个 URL 是要下载的资源。返回 (kind, url)。"""
    if section in MIRROR_SECTIONS:
        urls = URL_RE.findall(body)
        return ("remote", urls[0].rstrip(".,;")) if urls else None

    low = body.lower()
    for k in SCRIPT_KEYS:
        if k in low:
            m = URL_RE.search(body.split(k, 1)[1])
            return ("script", m.group(0).rstrip(".,;")) if m else None

    urls = URL_RE.findall(body)
    if section in SCRIPT_SECTIONS and urls:
        if section == "rewrite_local":
            # 镜像 conf 内部：只有多个 URL 时最后一个才是脚本；
            # 单个 URL 是 url reject / url 302 这类纯拦截规则，无资源可下。
            if len(urls) > 1:
                return "script", urls[-1].rstrip(".,;")
            return None
        return "script", urls[0].rstrip(".,;")

    m = re.search(r"img-url=(\S+)", body)
    if m:
        return "icon", m.group(1).rstrip(".,;")
    return None


def row_ok(url: str) -> bool:
    return url in DECISION and DECISION[url]["action"] != "drop"


def addition_urls() -> dict[str, str]:
    """追加资源同样要探测、镜像、可被 overrides 修复。"""
    out = {}
    for section, items in ADDITIONS.items():
        if section.startswith("_"):
            continue
        for it in items:
            if it.get("url"):
                out[it["url"]] = "remote"
    return out


ECHO_RE = re.compile(
    r"^(.*?\burl\s+echo-response\s+)([\w/+.-]+)(\s+echo-response\s+)(https?://\S+)\s*$"
)


def fix_echo_response(lines: list[str]) -> tuple[list[str], list[dict]]:
    """修掉 `echo-response ... echo-response <URL>` 这种写法。

    Qx 的 echo-response 只接受**字面量**响应体（或 data: URI），不能给 URL。
    上游直接把 mock JSON 的地址填在响应体位置，Qx 会报
    「echo-response 需要本机 Data 目录中的正文文件，不能直接引用 URL/URI」
    然后整条规则被忽略。这里把 JSON 下载下来转成 base64 data URI 内联回去，
    功能得以保留。
    """
    out, notes = [], []
    for line in lines:
        s = line.strip()
        if not s or s[0] in "#;" or "echo-response" not in s:
            out.append(line)
            continue
        if "script-echo-response" in s or "script-analyze-echo-response" in s:
            out.append(line)
            continue
        m = ECHO_RE.match(s)
        if not m:
            out.append(line)
            continue
        ctype, url = m.group(2), m.group(4)
        ok, code, body = probe(url)
        if not ok:
            out.append("# [qx-sync echo-response 无法内联] " + s)
            notes.append({"url": url, "status": code, "action": "drop",
                          "note": "mock 正文拉不到，规则已注释"})
            continue
        b64 = base64.b64encode(body).decode("ascii")
        out.append(m.group(1) + ctype + m.group(3) + f"data:{ctype};base64," + b64)
        notes.append({"url": url, "status": 200, "action": "inlined",
                      "note": f"正文内联为 base64（{len(body)} 字节）"})
    return out, notes


def normalize_policy_case(lines: list[str]) -> tuple[list[str], int]:
    """把行尾的 DIRECT / REJECT / PROXY 统一成小写。

    上游到处混用大小写（ADBlack.list 里就有 53 条大写 REJECT）。虽然 Qx 多数
    情况下能容忍，但统一之后审计脚本才能准确判断策略引用是否悬空。
    """
    out, n = [], 0
    for ln in lines:
        head, sep, tail = ln.rpartition(",")
        if sep and tail.strip() in ("DIRECT", "REJECT", "PROXY"):
            ln = head + ", " + tail.strip().lower()
            n += 1
        out.append(ln)
    return out, n


def fix_final_order(lines: list[str]) -> tuple[list[str], bool]:
    """[filter_local] 里 FINAL 必须是最后一条。

    上游把它写在了 GEOIP,CN 前面 → 那条 GEOIP 永远不可能命中（顺序匹配、
    命中即止）。等于国内 IP 也走代理。这是上游的笔误，作者意图显然是
    「国内直连」，只是写错了位置。
    """
    out: list[str] = []
    for header, body in split_sections(lines):
        if header is None:
            out.extend(body)
            continue
        out.append(header)
        if header.strip().strip("[]").strip().lower() != "filter_local":
            out.extend(body)
            continue
        finals = [ln for ln in body if ln.strip().upper().startswith("FINAL,")]
        if not finals:
            out.extend(body)
            continue
        rest = [ln for ln in body if not ln.strip().upper().startswith("FINAL,")]
        tail: list[str] = []
        while rest and not rest[-1].strip():
            tail.append(rest.pop())
        out.extend(rest)
        out.extend(finals)
        out.extend(tail)
    return out, out != lines


def prune_dead_icons(lines: list[str]) -> tuple[list[str], set[str]]:
    """img-url 指向死链时只去掉这个属性，不注释整行。

    图标挂了不影响功能，但留着会让 Qx 反复去拉一个 404。注意别整行注释掉——
    那样会把任务/规则本身一起废掉。
    """
    icons: set[str] = set()
    for ln in lines:
        for m in re.finditer(r"img-url=(\S+?)(?=,|$)", ln):
            u = m.group(1).strip()
            if u.startswith("http") and not u.startswith(RAW_BASE):
                icons.add(u)
    if not icons:
        return lines, set()

    def chk(u: str) -> tuple[str, bool]:
        ok, _, _ = probe(u)
        return u, ok

    dead: set[str] = set()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for u, ok in ex.map(chk, sorted(icons)):
            if not ok:
                dead.add(u)
    if not dead:
        return lines, set()

    out = []
    for ln in lines:
        for u in dead:
            ln = re.sub(r",\s*img-url=" + re.escape(u), "", ln)
        out.append(ln)
    return out, dead


def strip_empty_keys(lines: list[str]) -> tuple[list[str], list[str]]:
    """删掉「键 = 空值」的行。

    为什么：上游配置留了 `p12 = ` 和 `passphrase = ` 两个占位符。Qx 看到
    p12 键存在但值为空，会去加载一个空证书，直接弹
    「MitM 错误的 p12 或 p12 passphrase，连接已断开」，MITM 整个起不来，
    所有 rewrite 全废。删掉这两行 Qx 就会用自己生成的 CA。
    """
    out, removed = [], []
    for line in lines:
        s = line.strip()
        m = re.match(r"^([A-Za-z0-9_-]+)\s*=\s*$", s)
        if m and m.group(1).lower() in STRIP_EMPTY_KEYS:
            removed.append(s.rstrip())
            continue
        out.append(line)
    return out, removed


def split_sections(lines: list[str]) -> list[tuple[str | None, list[str]]]:
    """按 [section] 切块。返回 [(原始头部行或 None, 块内行)]。"""
    chunks: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in lines:
        s = line.strip()
        if s.startswith("[") and "]" in s:
            chunks.append((line, []))
        else:
            chunks[-1][1].append(line)
    return chunks


def inject_additions(lines: list[str]) -> tuple[list[str], int]:
    """把 config/additions.json 里的额外资源插入对应 section。

    为什么需要：filter_remote 是顺序匹配、先命中先生效。direct 修正类
    如果追加在末尾，会被前面 ADBlack 的 reject 抢先吃掉，等于没加。
    """
    if not ADDITIONS:
        return lines, 0

    by_section = {s: items for s, items in ADDITIONS.items() if not s.startswith("_")}
    out: list[str] = []
    added = 0

    for header, body in split_sections(lines):
        if header is None:
            out.extend(body)
            continue

        key = header.strip().strip("[]").strip()
        out.append(header)
        items = by_section.get(key, [])

        def render(it: dict) -> str:
            d = DECISION.get(it["url"])
            if not d:
                return "# [qx-sync 未探测] " + it["line"].replace("{url}", it["url"])
            line = it["line"].replace("{url}", d["final"] or it["url"])
            if d["action"] == "drop":
                return "# [qx-sync 失效] " + line
            return line

        pre = [render(i) for i in items if i.get("position") == "prepend"]
        post = [render(i) for i in items if i.get("position") != "prepend"]

        out.extend(pre)
        added += len(pre)
        out.extend(body)

        if post:
            # 插到本块最后一个有效行之后，避免被尾部空行/注释隔开
            start = len(out) - len(body)
            idx = len(out)
            for k in range(len(out) - 1, start - 1, -1):
                t = out[k].strip()
                if t and not t.startswith("#") and not t.startswith(";"):
                    idx = k + 1
                    break
            out[idx:idx] = post
            added += len(post)

    return out, added


def probe_batch(urls: dict[str, str]) -> None:
    """urls: {url: kind}。并发探测并写入 DECISION。"""
    todo = {}
    for url, kind in urls.items():
        if url in DECISION or url.startswith(RAW_BASE):
            continue
        todo[url] = kind
    if not todo:
        return

    def work(pair):
        url, kind = pair
        if url in DROP:
            return {"url": url, "kind": kind, "status": None, "action": "drop",
                    "final": None, "note": "在 drop 名单（上游仓库已删除/封禁）"}
        target = REPLACE.get(url)
        if target:
            ok, code, body = probe(target)
            if ok:
                save(mirror_path(target), body)
                return {"url": url, "kind": kind, "status": code, "action": "replaced",
                        "final": mirror_url(target), "src": target,
                        "note": f"已替换 → {urlparse(target).path}"}
            return {"url": url, "kind": kind, "status": code, "action": "drop",
                    "final": None, "note": f"替代源不可用 ({code})"}
        ok, code, body = probe(url)
        if ok:
            if kind == "icon" and not MIRROR_ICONS:
                return {"url": url, "kind": kind, "status": code, "action": "keep",
                        "final": url, "note": "图标，不镜像"}
            if kind == "script" and not MIRROR_SCRIPTS:
                return {"url": url, "kind": kind, "status": code, "action": "keep",
                        "final": url, "note": "脚本，不镜像"}
            save(mirror_path(url), body)
            return {"url": url, "kind": kind, "status": code, "action": "mirrored",
                    "final": mirror_url(url), "src": url, "note": ""}
        note = {0: "连接失败/超时", 200: "返回 HTML 而非资源", 401: "401 未授权",
                403: "403 被拒", 404: "404 不存在", 405: "405",
                410: "410 已删除", 429: "429 限流",
                451: "451 被 DMCA 封禁"}.get(code, f"HTTP {code}")
        # 硬死亡：确定资源不存在，可以安全注释掉
        if code in (404, 410, 451) or code == 200:
            return {"url": url, "kind": kind, "status": code, "action": "drop",
                    "final": None, "note": note}
        # 软失败：可能是扫描器自身网络/限流问题，不能误杀，保留原链
        return {"url": url, "kind": kind, "status": code or 0, "action": "keep",
                "final": url, "note": f"{note}（已保留原链，待下轮复验）"}

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for d in ex.map(work, todo.items()):
            DECISION[d["url"]] = d
            ITEMS.append(d)
            if d["action"] == "replaced":
                REPLACED.append({"from": d["url"], "to": d["src"], "mirror": d["final"]})


def collect(lines: list[str], hint: str | None = None) -> dict[str, str]:
    """从一组行里提取 {url: kind}，只取生效行。hint 用于无 [section] 头的镜像 conf。"""
    section = hint or "preface"
    out = {}
    for line in lines:
        s = line.strip()
        if s.startswith("[") and "]" in s and hint is None:
            section = s[1:s.index("]")].strip()
            continue
        if not s or s[0] in "#;":
            continue
        if section not in MIRROR_SECTIONS and section not in SCRIPT_SECTIONS:
            continue
        f = line_resource(section, s)
        if f:
            out[f[1]] = f[0]
    return out


def rewrite_lines(lines: list[str], section_hint: str | None = None) -> tuple[list[str], int]:
    """按 DECISION 改写行。返回 (新行列表, 被注释数)。"""
    section = section_hint or "preface"
    out, dropped = [], 0
    for line in lines:
        s = line.strip()
        if s.startswith("[") and "]" in s and section_hint is None:
            section = s[1:s.index("]")].strip()
            out.append(line)
            continue
        if not s or s[0] in "#;":
            out.append(line)
            continue
        if section not in MIRROR_SECTIONS and section not in SCRIPT_SECTIONS:
            out.append(line)
            continue
        f = line_resource(section, s)
        if not f:
            out.append(line)
            continue
        kind, url = f
        d = DECISION.get(url)
        if not d:
            out.append(line)
            continue
        if d["action"] == "drop":
            out.append("# [qx-sync 失效] " + line)
            dropped += 1
        elif d["final"] and d["final"] != url:
            out.append(line.replace(url, d["final"]))
        else:
            out.append(line)
    return out, dropped


# ---------------------------------------------------------------- 报告

def write_report(prev: dict | None) -> dict:
    dead = [i for i in ITEMS if i["action"] == "drop"]
    live = [i for i in ITEMS if i["action"] != "drop"]

    prev_dead = set()
    if prev:
        prev_dead = {i["url"] for i in prev.get("items", []) if i.get("action") == "drop"}
    newly = [i for i in dead if i["url"] not in prev_dead]

    now = datetime.now(timezone(timedelta(hours=8)))
    report = {
        "generated_at": now.isoformat(),
        "upstream": CFG["profile_url"],
        "summary": {"total": len(ITEMS), "alive": len(live), "dead": len(dead),
                    "replaced": len(REPLACED), "newly_dead": len(newly)},
        "items": sorted(ITEMS, key=lambda x: (x["action"] != "drop", x["url"])),
        "replaced": REPLACED,
        "dropped": [{"url": i["url"], "kind": i["kind"], "status": i["status"],
                     "note": i["note"]} for i in dead],
    }
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "status.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    L = ["# QuantumultX 配置体检报告", "",
         f"- 上次同步：`{now:%Y-%m-%d %H:%M:%S %z}`（北京时间）",
         f"- 上游配置：{CFG['profile_url']}",
         f"- 资源总数 **{len(ITEMS)}** ｜ 可用 **{len(live)}** ｜ 失效 **{len(dead)}**"]
    if newly:
        L.append(f"- ⚠️ **本次新增失效 {len(newly)} 条**")
    L.append("")

    if ECHO_FIXES:
        L += ["## echo-response 响应体已内联", "",
              "Qx 的 `echo-response` 只认字面量响应体，不能填 URL。上游把 mock 地址"
              "直接写在响应体位置，会被 Qx 忽略。已把正文下载下来转成 base64 内联：", ""]
        for e in ECHO_FIXES:
            mark = "✅ 已内联" if e["action"] == "inlined" else "❌ 已注释"
            L.append(f"- {mark} · `{e['url']}` · {e['note']}")
        L.append("")

    if STRIPPED:
        L += ["## 已移除的空值配置项", "",
              "上游留了值为空的占位符，Qx 会把它当成「我要用自定义证书」从而报 "
              "`MitM 错误的 p12 或 p12 passphrase`。以下行已从生成配置中删除：", ""]
        for s in STRIPPED:
            L.append(f"- `{s}`")
        L.append("")

    if REPLACED:
        L += ["## 死链已自动修复", "", "| 原地址（已死） | 替换为 |", "|---|---|"]
        for r in REPLACED:
            L.append(f"| `{r['from']}` | `{r['to']}` |")
        L.append("")

    if ADDITIONS:
        L += ["## 额外追加的规则源（上游配置原本没有）", ""]
        for sec, items in ADDITIONS.items():
            if sec.startswith("_"):
                continue
            for it in items:
                d = DECISION.get(it["url"], {})
                where = "插在最前 · 最高优先级" if it.get("position") == "prepend" else "追加到末尾 · 最低优先级"
                state = "✅" if d.get("action") not in (None, "drop") else "❌ 未生效"
                L.append(f"- {state} **{sec}** · {where} · `{it['url']}`")
                if it.get("why"):
                    L.append(f"  - {it['why']}")
        L.append("")

    if dead:
        L += ["## 失效清单（配置中已注释，不再拖慢 Qx）", "",
              "| 状态 | 类型 | 地址 | 说明 |", "|---|---|---|---|"]
        for i in dead:
            st = "超时" if not i["status"] else str(i["status"])
            mark = " 🆕" if i in newly else ""
            L.append(f"| {st}{mark} | {i['kind']} | `{i['url'][:120]}` | {i['note']} |")
        L.append("")

    L += ["## 全部资源", "", "<details><summary>展开明细</summary>", "",
          "| 状态 | 动作 | 地址 |", "|---|---|---|"]
    for i in report["items"]:
        st = "OK" if i["action"] != "drop" else "DEAD"
        L.append(f"| {st} | {i['action']} | `{i['url'][:120]}` |")
    L += ["", "</details>", "",
          "## 怎么用", "",
          "Quantumult X → 风车 → 配置文件 → 远程配置 → 添加：", "",
          "```",
          RAW_BASE + "QuantumultX.conf",
          "```", "",
          "然后把节点订阅填进 `[server_remote]`（本仓库不托管任何节点）。"]

    with open(os.path.join(ROOT, "reports", "STATUS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    print(f"资源 {len(ITEMS)} | 可用 {len(live)} | 失效 {len(dead)} | "
          f"修复 {len(REPLACED)} | 新增失效 {len(newly)}")
    return report


# ---------------------------------------------------------------- main

def main() -> int:
    print(f"上游: {CFG['profile_url']}")
    ok, code, body = probe(CFG["profile_url"])
    if not ok:
        print(f"上游配置拉取失败 (code={code})，中止并保留上一次产物。", file=sys.stderr)
        return 1
    text = body.decode("utf-8", "replace")

    prev = None
    p = os.path.join(ROOT, "reports", "status.json")
    if os.path.exists(p):
        try:
            prev = json.load(open(p, encoding="utf-8"))
        except Exception:
            prev = None

    lines = text.splitlines()

    # Phase 1：主配置里的直接资源 + 追加资源
    batch1 = collect(lines)
    extra = addition_urls()
    batch1.update(extra)
    print(f"直接引用 {len(batch1)} 个（含追加 {len(extra)}）")
    probe_batch(batch1)

    # Phase 2：镜像下来的 conf 内部嵌套的脚本（递归一层）
    batch2: dict[str, str] = {}
    for d in ITEMS:
        src = d.get("src")
        if d["action"] not in ("mirrored", "replaced") or not src:
            continue
        if not src.endswith((".conf", ".snippet", ".sgmodule", ".list", ".txt")):
            continue
        nested = collect(read_mirror(src).splitlines(), "rewrite_local")
        for u, k in nested.items():
            if k == "script":
                batch2[u] = k
    if batch2:
        print(f"嵌套脚本 {len(batch2)} 个")
        probe_batch(batch2)

    # Phase 3：改写镜像 conf 内部的嵌套脚本地址
    patched = 0
    for d in ITEMS:
        src = d.get("src")
        if d["action"] not in ("mirrored", "replaced") or not src:
            continue
        if not src.endswith((".conf", ".snippet", ".sgmodule")):
            continue
        content = read_mirror(src).splitlines()
        if not batch2:
            break
        new, n = rewrite_lines(content, "rewrite_local")
        new, echo_notes = fix_echo_response(new)
        if echo_notes:
            ECHO_FIXES.extend(echo_notes)
        if n or echo_notes or new != content:
            patched += 1
            with open(os.path.join(ROOT, mirror_path(src)), "w", encoding="utf-8") as f:
                f.write("\n".join(new) + "\n")

    # Phase 4：生成主配置
    out, dropped = rewrite_lines(lines)
    out, added = inject_additions(out)
    out, echo_main = fix_echo_response(out)
    ECHO_FIXES.extend(echo_main)
    out, stripped = strip_empty_keys(out)
    if stripped:
        print(f"移除空值键 {len(stripped)} 个：{', '.join(stripped)}")
        STRIPPED[:] = stripped
    out, ncase = normalize_policy_case(out)
    if ncase:
        print(f"统一策略名大小写 {ncase} 处")
    out, moved = fix_final_order(out)
    if moved:
        print("FINAL 已移到 [filter_local] 末尾（原位置导致其后规则永不命中）")
    out, dead_icons = prune_dead_icons(out)
    if dead_icons:
        print(f"清理失效图标 {len(dead_icons)} 个（保留任务本身）")
        DEAD_ICONS[:] = sorted(dead_icons)

    now = datetime.now(timezone(timedelta(hours=8)))
    header = [
        "# ============================================================",
        "# QuantumultX 配置 · 自动校验版",
        f"# 构建时间: {now:%Y-%m-%d %H:%M:%S} +08:00（GitHub Actions 每日本地 08:00 重建）",
        f"# 上游来源: {CFG['profile_url']}",
        f"# 体检报告: {RAW_BASE}reports/STATUS.md",
        "# 所有外部资源已镜像并通过可用性校验；失效项已注释并标记 [qx-sync 失效]。",
        "# 请勿手工修改本文件 —— 下次同步会被覆盖。要改就改 config/overrides.json。",
        "# ============================================================",
        "",
    ]
    with open(os.path.join(ROOT, "QuantumultX.conf"), "w", encoding="utf-8") as f:
        f.write("\n".join(header + out) + "\n")
    print(f"主配置已生成，注释掉 {dropped} 行失效引用，注入 {added} 条追加规则")

    write_report(prev)

    # 清理孤立镜像
    used = {mirror_path(i["src"]) for i in ITEMS
            if i["action"] in ("mirrored", "replaced") and i.get("src")}
    removed = 0
    for root, _, files in os.walk(os.path.join(ROOT, "Sources")):
        for fn in files:
            fp = os.path.join(root, fn)
            if os.path.relpath(fp, ROOT) not in used:
                os.remove(fp)
                removed += 1
    if removed:
        print(f"清理孤立镜像 {removed} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
