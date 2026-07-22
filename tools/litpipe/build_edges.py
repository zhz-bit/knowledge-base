#!/usr/bin/env python3
"""litpipe ② build_edges · 增量抓引用边(整条管线的命门)

设计要点:
  · refs_cache 存**每篇的完整原始参考列表**(不是只存匹配上的边)——
    这样以后新加论文 P 时,"谁引用了 P"只需本地扫一遍缓存,不用重抓全库。
  · 抓取是增量的(只抓没缓存过的);边是**每次从缓存全量重算**(本地、快、永远自洽),
    因此正向(P→别人)和反向(别人→P)天然都覆盖,无需特殊处理。
  · 顺带记录每篇的全局被引数 cc,供 ③ enrich 评级使用。

用法:
  python build_edges.py            # 增量抓 + 重算边
  python build_edges.py --limit 20 # 本轮最多抓 20 篇(限流时分批推进,可反复跑)
  python build_edges.py --no-fetch # 只用现有缓存重算边,不联网
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zotero_io import (Zot, arxiv_of, norm_title, load_state, save_state,
                       build_match_index, match_ref, STATE)

LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit": LIMIT = int(sys.argv[i + 1])
NO_FETCH = "--no-fetch" in sys.argv

S2 = "https://api.semanticscholar.org/graph/v1"
REF_FIELDS = "externalIds,title,year,citationCount"
SEED = Path("/private/tmp/claude-501/-Users-zhaozhihua-knowledge-base/"
            "c5dbaf72-2174-4ab8-bbf0-dd3fd6e317ee/scratchpad/gaps_refs_cache.json")


def s2_get(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "litpipe/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=45).read())
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            if e.code == 429: time.sleep(6 + 5 * i); continue
            time.sleep(3)
        except Exception:
            time.sleep(3)
    return None


def fetch_refs(paper):
    """抓一篇的完整参考列表 + 它自己的全局被引数。返回 (refs, cc) 或 (None, None)。"""
    pid = None
    if paper.get("arxiv"): pid = f"arXiv:{paper['arxiv']}"
    elif paper.get("doi") and not paper["doi"].startswith("10.48550"):
        pid = f"DOI:{urllib.parse.quote(paper['doi'])}"
    meta = s2_get(f"{S2}/paper/{pid}?fields=citationCount") if pid else None
    if meta is None and not pid:
        q = urllib.parse.quote(__import__("re").sub(r"[^\w\s]", " ", paper["title"])[:110])
        srch = s2_get(f"{S2}/paper/search?query={q}&fields=title,citationCount,externalIds&limit=3")
        for c in (srch or {}).get("data", []):
            if norm_title(c.get("title", "")) == norm_title(paper["title"]):
                pid = c["paperId"]; meta = c; break
    if not pid: return None, None
    r = s2_get(f"{S2}/paper/{pid}/references?fields={REF_FIELDS}&limit=500")
    if r is None: return None, None
    refs = []
    for it in r.get("data", []) or []:
        cp = it.get("citedPaper") or {}
        ex = cp.get("externalIds") or {}
        refs.append({"ax": ex.get("ArXiv"), "doi": ex.get("DOI"),
                     "title": cp.get("title", ""), "year": cp.get("year"),
                     "cc": cp.get("citationCount") or 0})
    return refs, (meta or {}).get("citationCount", 0)


def main():
    z = Zot()
    print("扫描 Zotero 综述树 ...")
    tree = z.scan_tree()
    corpus = {}
    for k, v in tree.items():
        d = v["data"]
        corpus[k] = {"title": d.get("title", ""), "arxiv": arxiv_of(d),
                     "doi": (d.get("DOI") or ""), "year": (d.get("date", "") or "")[:4],
                     "leaf": v["leaf"], "itemType": d.get("itemType")}
    print(f"语料 {len(corpus)} 篇")

    refs_cache = load_state("refs_cache.json", {})

    # 首次播种:把已有的完整 refs 缓存(按 arxiv 键)映射到 Zotero key
    if not refs_cache and SEED.exists():
        seed = json.load(open(SEED, encoding="utf-8"))
        ax2key = {n["arxiv"]: k for k, n in corpus.items() if n.get("arxiv")}
        n = 0
        for ax, refs in seed.items():
            k = ax2key.get(ax)
            if k and isinstance(refs, list) and (not refs or isinstance(refs[0], dict)):
                refs_cache[k] = refs; n += 1
        print(f"从既有缓存播种 {n} 篇(省掉同样多次抓取)")

    # 增量抓:只抓没缓存过的
    todo = [k for k in corpus if k not in refs_cache]
    if NO_FETCH:
        print(f"--no-fetch:跳过抓取(还有 {len(todo)} 篇没缓存)")
    else:
        if LIMIT: todo = todo[:LIMIT]
        print(f"待抓 {len(todo)} 篇 ...")
        cc_map = load_state("cc.json", {})
        for i, k in enumerate(todo):
            refs, cc = fetch_refs(corpus[k])
            refs_cache[k] = refs if refs is not None else []
            if cc is not None: cc_map[k] = cc
            if (i + 1) % 5 == 0:
                save_state("refs_cache.json", refs_cache); save_state("cc.json", cc_map)
                print(f"  {i+1}/{len(todo)} 已抓(缓存 {len(refs_cache)})")
            time.sleep(3.2)
        save_state("cc.json", cc_map)
    save_state("refs_cache.json", refs_cache)

    # 全量重算边(本地):正向反向一次覆盖
    idx = build_match_index(corpus)
    edges, indeg = set(), Counter()
    harvest = {}          # 从别人的参考列表里"收割"全局被引数(零 API 成本)
    for src, refs in refs_cache.items():
        if src not in corpus: continue          # 已移出树的旧论文不参与
        for ref in refs or []:
            dst = match_ref(ref, idx)
            if dst and dst != src:
                edges.add((src, dst)); indeg[dst] += 1
                c = ref.get("cc") or 0
                if c > harvest.get(dst, 0): harvest[dst] = c
    edges = sorted(edges)
    save_state("edges.json", [list(e) for e in edges])

    # cc:优先用抓取时拿到的;缺的用收割值补(被引过的论文基本都能补上)
    cc_map = load_state("cc.json", {})
    for k, c in harvest.items():
        if not cc_map.get(k): cc_map[k] = c
    save_state("cc.json", cc_map)
    for k, n in corpus.items():
        n["indeg"] = indeg.get(k, 0)
        n["cc"] = cc_map.get(k, 0)
    save_state("corpus.json", corpus)

    cached = sum(1 for k in corpus if k in refs_cache)
    print(f"\n缓存覆盖 {cached}/{len(corpus)} 篇 | 引用边 {len(edges)} 条")
    top = sorted(corpus.items(), key=lambda kv: -kv[1]["indeg"])[:8]
    print("语料内被引 Top:")
    for k, n in top:
        print(f"  indeg{n['indeg']:3}  cc{n['cc']:>6}  {n['title'][:52]}")
    if not NO_FETCH and len(todo) and len([k for k in corpus if k not in refs_cache]):
        print(f"\n还有 {len([k for k in corpus if k not in refs_cache])} 篇未缓存,再跑一次(或加 --limit)继续。")


if __name__ == "__main__":
    main()
