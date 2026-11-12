#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bounty-scam-detector
====================

GitHub 上标着 "bounty" 的 issue，很大一部分不是悬赏，而是：
  · 诱捕自动化 Agent 的测试夹具（trap / fixture / benchmark）
  · 用积分兑换当幌子的免费劳动力农场

这个脚本用 6 条可验证的信号给仓库打分，帮你在一头扎进去之前判断：
这个"悬赏"到底有没有人真的准备付钱。

用法
----
    # 1. 直接查几个仓库
    python detector.py owner/repo owner2/repo2

    # 2. 搜出当前所有 open 的 bounty issue，按仓库聚合后打分
    python detector.py --search "label:bounty"

    # 3. 从文件读仓库列表（每行一个）
    python detector.py --file repos.txt

    # 4. 输出 JSON，方便接别的工具
    python detector.py --search "label:bounty" --json

设置 GITHUB_TOKEN 环境变量可以把 API 配额从 60 次/小时提到 5000 次/小时。

没有第三方依赖，Python 3.8+ 即可运行。
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
USER_AGENT = "bounty-scam-detector/1.0"

# 这些词出现在仓库名或简介里，基本可以直接判定为测试夹具
FLAG_WORDS = (
    "benchmark",
    "fixture",
    "sandbox",
    "telemetry",
    "bounty solver",
    "bounty-solver",
    "testing an automated",
    "trap",
)


def _headers():
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def api_get(path, params=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"HTTP {e.code}: {body}") from None


def days_since(iso):
    if not iso:
        return None
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except ValueError:
        return None


# --------------------------------------------------------------------------
# 打分
# --------------------------------------------------------------------------

def score_repo(repo):
    """返回 (分数, 风险等级, [(分值, 原因), ...])"""
    stars = repo.get("stargazers_count") or 0
    forks = repo.get("forks_count") or 0
    issues = repo.get("open_issues_count") or 0
    size_kb = repo.get("size") or 0
    age = days_since(repo.get("created_at"))
    desc = repo.get("description") or ""
    name = repo.get("name") or ""
    text = f"{name} {desc}".lower()

    hits = []

    # 1. fork 数超过 star 数 —— 正常项目一定反过来
    if forks > stars and stars < 100:
        hits.append((30, f"fork({forks}) 超过 star({stars})"))

    # 2. issue 数量相对代码量异常
    if issues > 100 and size_kb < 2000:
        hits.append((30, f"{issues} 个 open issue，代码只有 {size_kb} KB"))

    # 3. 新建不久就挂满 issue
    if age is not None and age <= 60 and issues > 50:
        hits.append((25, f"建库 {age} 天就有 {issues} 个 issue"))

    # 4. 自述里出现夹具类关键词
    for word in FLAG_WORDS:
        if word in text:
            hits.append((40, f"自述含「{word}」"))
            break

    # 5. 是别人的 fork，却挂着大量 issue
    if repo.get("fork") and issues > 50:
        hits.append((35, "是别人的 fork，却挂着大量 issue"))

    # 6. 0 star 却有大量 fork
    if stars == 0 and forks >= 20:
        hits.append((25, f"0 star 却有 {forks} 个 fork"))

    total = min(100, sum(p for p, _ in hits))
    if total >= 60:
        level = "HIGH"
    elif total >= 30:
        level = "MEDIUM"
    else:
        level = "LOW"
    return total, level, hits


# --------------------------------------------------------------------------
# 采集
# --------------------------------------------------------------------------

def collect_from_search(query, per_page=50):
    """搜 open 的 bounty issue，返回去重后的仓库名列表"""
    data = api_get("/search/issues", {
        "q": f"{query} is:issue state:open",
        "per_page": per_page,
        "sort": "updated",
        "order": "desc",
    })
    repos = []
    seen = set()
    for item in data.get("items", []):
        full = item.get("repository_url", "").replace(f"{API}/repos/", "")
        if full and full not in seen:
            seen.add(full)
            repos.append(full)
    return repos


def fetch_repo(full_name):
    return api_get(f"/repos/{full_name}")


def wait_for_quota():
    """撞到限流时等一会儿再继续"""
    time.sleep(2)


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
DIM = "\033[2m"
RESET = "\033[0m"

# 只在真终端里上色；重定向到文件或设了 NO_COLOR 时全部退化成纯文本。
# 否则转义码会以 [2m 这种形式混进输出，管道下游全被污染。
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def color(level):
    if not USE_COLOR:
        return "", ""
    return {"HIGH": (RED, RESET),
            "MEDIUM": (YELLOW, RESET),
            "LOW": (GREEN, RESET)}[level]


def render(results):
    print()
    print(f"{'仓库':<44} {'分':>4}  {'风险':<6} 主要理由")
    print("-" * 104)
    for r in results:
        c0, c1 = color(r["level"])
        reason = r["reasons"][0] if r["reasons"] else "无明显异常"
        print(f"{r['repo'][:44]:<44} {r['score']:>4}  "
              f"{c0}{r['level']:<6}{c1} {reason}")
    print("-" * 104)

    high = sum(1 for r in results if r["level"] == "HIGH")
    print(f"共 {len(results)} 个仓库，其中 {high} 个高风险。")
    if high:
        note = "分数 ≥ 60 建议直接放弃：真悬赏不会空置几个月还等你来领。"
        print(f"\n{DIM}{note}{RESET}" if USE_COLOR else f"\n{note}")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="给 GitHub 上的『悬赏仓库』打分，识别陷阱和积分农场")
    p.add_argument("repos", nargs="*", help="owner/repo，可多个")
    p.add_argument("--search", metavar="QUERY",
                   help='搜索 open 的 bounty issue，如 "label:bounty"')
    p.add_argument("--file", metavar="PATH", help="从文件读仓库列表，每行一个")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument("--details", action="store_true", help="打印每个仓库的全部命中理由")
    args = p.parse_args(argv)

    names = list(args.repos)

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            names += [line.strip() for line in f
                      if line.strip() and not line.startswith("#")]

    if args.search:
        try:
            names += collect_from_search(args.search)
        except RuntimeError as e:
            print(f"搜索失败: {e}", file=sys.stderr)
            return 1

    # 去重保序
    seen, unique = set(), []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            unique.append(n)

    if not unique:
        p.print_help()
        return 1

    results = []
    for i, name in enumerate(unique, 1):
        print(f"[{i}/{len(unique)}] {name}", file=sys.stderr)
        try:
            repo = fetch_repo(name)
        except RuntimeError as e:
            print(f"  跳过: {e}", file=sys.stderr)
            wait_for_quota()
            continue
        score, level, hits = score_repo(repo)
        results.append({
            "repo": name,
            "score": score,
            "level": level,
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "open_issues": repo.get("open_issues_count"),
            "size_kb": repo.get("size"),
            "created_at": repo.get("created_at"),
            "reasons": [reason for _, reason in hits],
        })
        wait_for_quota()

    results.sort(key=lambda r: -r["score"])

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        render(results)
        if args.details:
            print()
            for r in results:
                if r["reasons"]:
                    print(f"{r['repo']}  ({r['score']} 分)")
                    for reason in r["reasons"]:
                        print(f"   · {reason}")
                    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
