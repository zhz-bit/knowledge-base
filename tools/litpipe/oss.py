#!/usr/bin/env python3
"""litpipe ⑤ oss · 开源检测(四级合一,可无人值守)

四级按成本从低到高,前面命中就不跑后面:
  ① 摘要 / extra / url 里的仓库链接   —— 零成本,读 Zotero 本地数据
  ② arXiv API 的 comment 字段        —— 批量,几秒
  ③ PDF 正文挖掘                     —— 本地,零 API(链接常只在脚注/"Code available at")
  ④ gh 搜索 + 官方性验证             —— 最贵,且是"猜候选",验证最严

**可信度不同,验证强度也不同**:
  · PDF 正文与摘要里的链接是**作者自己写的**,仓库存在即采信
  · gh 搜索是我猜的候选,必须仓库 README/描述提到该论文(arXiv 号/主标题/≥60% 实词)

三条防误报护栏(都是实际踩出来的):
  · 综述论文正文里印的是**别人的**仓库(它在罗列相关工作)→ 标题含 survey/review 的不走"正文即采信"
  · 泛标题匹配一切 → 主标题是 "Autonomous Driving" 这类纯泛词时不用"含主标题"规则
  · 一仓库被多篇认领 → 按仓库名与模型名贴合度裁决(同团队续作如 VAD/VADv2 例外)

**增量**:已标过 `开源`/`未见开源` 且 extra 有 Code: 行的跳过,只查新论文。
加 --force 全部重查。

用法:
  python oss.py                    # 增量,全库,干运行
  python oss.py --apply            # 写回 Zotero
  python oss.py --scope e2e        # 只跑端到端
  python oss.py --force --apply    # 全部重查
"""
import json, re, subprocess, sys, time
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, load_state, save_state
from lib_corpus import _api_get as api
from detect_oss import find_repo, arxiv_meta
from detect_oss_gh import gh, verify, model_name, words, norm
from detect_oss_pdf import local_pdfs, scan_pdf

APPLY = "--apply" in sys.argv
FORCE = "--force" in sys.argv
SCOPE = "all"
for i, a in enumerate(sys.argv):
    if a == "--scope":
        SCOPE = sys.argv[i + 1]

LIST_RE = re.compile(r"awesome|paper[-_]?list|reading[-_]?list|survey|collection|"
                     r"resources|roadmap", re.I)
SURVEY_RE = re.compile(r"survey|review|benchmark(?:ing)?\s+of|challenges\s+and", re.I)
GENERIC = {"autonomous driving", "end to end autonomous driving",
           "end-to-end autonomous driving", "deep learning", "computer vision"}


def is_generic(title):
    return norm(title.split(":")[0]) in GENERIC


def dedupe(rows):
    """一个仓库被多篇论文认领时,只留最贴合的。同团队续作(VAD/VADv2)保留。"""
    by = {}
    for r in rows:
        by.setdefault(r["repo"], []).append(r)
    drop = set()
    for repo, xs in by.items():
        if len(xs) < 2:
            continue
        rn = norm(repo.split("/")[-1]).replace(" ", "")

        def score(x):
            head = norm(x["title"].split(":")[0]).replace(" ", "")
            if rn == head:
                return 3
            if rn and (rn in head or head.startswith(rn)):
                return 2
            return 0
        xs.sort(key=lambda x: -score(x))
        for x in xs[1:]:
            # 分数相同 = 同一系列的续作,都算这个仓库
            if score(x) < score(xs[0]):
                drop.add(id(x))
    return [r for r in rows if id(r) not in drop]


def main():
    z = Zot()
    C = load_state("lib_corpus.json", {})
    if SCOPE == "e2e":
        pool = {k: v for k, v in C.items()
                if v["band"] == "5 自动驾驶综述"
                and ("端到端" in v["sub"] or v["sub"] in ("VLM-VLA", "模块化E2E", "RL后训练"))}
    else:
        pool = dict(C)

    # 批量取条目(逐条会被偶发 SSL 打断,且 except:continue 会静默丢数据)
    data = {}
    keys = list(pool)
    for i in range(0, len(keys), 50):
        for x in api(z, f"{z.base}/items?itemKey={','.join(keys[i:i+50])}&limit=50"):
            data[x["key"]] = x["data"]
        time.sleep(0.25)
    print(f"范围 {SCOPE}:{len(pool)} 篇,取回 {len(data)}")

    if not FORCE:                                   # 增量:查过的跳过
        skip = {k for k, d in data.items()
                if re.search(r"^Code:", d.get("extra", "") or "", re.M)
                or any(t.get("tag") == "未见开源" for t in d.get("tags", []))}
        pool = {k: v for k, v in pool.items() if k not in skip}
        print(f"增量模式:已查过 {len(skip)} 篇,本次查 {len(pool)} 篇")
    if not pool:
        print("没有待查的论文"); return

    found = {}

    # ── ① 摘要 / extra / url ──
    need_ax = []
    for k in pool:
        d = data.get(k) or {}
        r = find_repo(d.get("abstractNote", ""), d.get("extra", ""), d.get("url", ""))
        if r:
            found[k] = {"repo": r, "how": "摘要/元数据"}
        elif pool[k].get("arxiv"):
            need_ax.append((k, pool[k]["arxiv"]))
    print(f"① 摘要/元数据:{len(found)}")

    # ── ② arXiv comment ──
    if need_ax:
        meta = arxiv_meta([a for _, a in need_ax])
        n = 0
        for k, ax in need_ax:
            m = meta.get(ax)
            if m:
                r = find_repo(m["comment"], m["summary"])
                if r:
                    found[k] = {"repo": r, "how": "arXiv comment"}; n += 1
        print(f"② arXiv comment:{n}")

    # ── ③ PDF 正文 ──
    rest = [k for k in pool if k not in found]
    pdfs = local_pdfs(rest) if rest else {}
    n = 0
    for k, f in pdfs.items():
        repo, site = scan_pdf(f)
        cand = repo or (f"https://github.com/{site}" if site else "")
        if not cand:
            continue
        found[k] = {"repo": cand, "how": "PDF正文", "from_pdf": bool(repo),
                    "survey": bool(SURVEY_RE.search(pool[k]["title"]))}
        n += 1
    print(f"③ PDF 正文:{n}(有本地 PDF 的 {len(pdfs)} 篇)")

    # ── ④ gh 搜索(只对前三级都没命中、且库内被引 ≥1 的,控制成本)──
    rest = [k for k in pool if k not in found and pool[k]["indeg"] >= 1]
    rest.sort(key=lambda k: -pool[k]["indeg"])
    print(f"④ gh 搜索:待查 {len(rest)} 篇 ...", flush=True)
    n = 0
    for k in rest:
        v = pool[k]
        nm = model_name(v["title"])
        q = f"{nm} autonomous driving" if len(nm.split()) <= 3 else nm
        res = gh(["-X", "GET", "search/repositories", "-f", f"q={q}", "-f", "per_page=5"])
        best = None
        for it in ((res or {}).get("items") or [])[:5]:
            if LIST_RE.search(it["full_name"]):
                continue
            ok, why = verify(it, v["title"], v.get("arxiv", ""))
            if ok and "含论文主标题" in why and is_generic(v["title"]):
                continue                              # 泛标题不能靠"含主标题"
            if ok and "实词命中" in why and it["stargazers_count"] < 20:
                continue                              # 证据太弱
            if ok and (best is None or it["stargazers_count"] > best[0]["stargazers_count"]):
                best = (it, why)
            time.sleep(0.35)
        if best:
            found[k] = {"repo": f"https://github.com/{best[0]['full_name']}",
                        "how": f"gh搜索·{best[1]}",
                        "stars": best[0]["stargazers_count"]}
            n += 1
        time.sleep(0.8)
    print(f"   命中 {n}")

    # ── 验证 + 补 star ──
    print("\n验证仓库并取 star ...", flush=True)
    rows = []
    for k, info in found.items():
        m = re.match(r"https://github\.com/([^/]+)/([^/]+?)/?$", info["repo"].rstrip("./"))
        if not m:
            continue
        rp = gh([f"/repos/{m.group(1)}/{m.group(2)}"])
        if not rp or "full_name" not in rp:
            continue                                  # 仓库不存在
        # 综述正文里印的是别人的仓库,不算它自己开源
        if info.get("survey") and info.get("from_pdf"):
            continue
        rows.append({"key": k, "title": pool[k]["title"], "year": pool[k]["year"],
                     "sub": pool[k]["sub"], "indeg": pool[k]["indeg"],
                     "repo": f"https://github.com/{rp['full_name']}",
                     "stars": rp.get("stargazers_count", 0),
                     "pushed": (rp.get("pushed_at") or "")[:10],
                     "archived": rp.get("archived", False), "how": info["how"]})
        time.sleep(0.35)
    rows = dedupe(rows)
    rows.sort(key=lambda x: -x["stars"])

    old = {r["key"]: r for r in load_state("oss_all.json", [])}
    for r in rows:
        old[r["key"]] = r
    allr = sorted(old.values(), key=lambda x: -x["stars"])
    print(f"\n本次新增确认 {len(rows)} 篇;累计 {len(allr)} 篇开源")
    print("来源:", dict(Counter(x["how"].split("·")[0] for x in allr)))
    for r in rows[:15]:
        print(f"  ★{r['stars']:<6} {r['repo'].split('github.com/')[-1][:36]:36} {r['title'][:40]}")
    if not APPLY:
        print("\n(加 --apply 写回 Zotero)")
        return
    save_state("oss_all.json", allr)
    r = subprocess.run([sys.executable, str(HERE / "write_oss.py"), "--apply"],
                       capture_output=True, text=True, timeout=3600)
    print(r.stdout.strip()[-300:] or r.stderr.strip()[-300:])


if __name__ == "__main__":
    main()
