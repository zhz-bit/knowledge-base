#!/usr/bin/env python3
"""litpipe · 共识参考挖掘 —— 从引用网络里找"被你的文献反复引用、你却没收藏"的关键论文

原理:refs_cache 里已有全部语料论文的**完整参考列表**(② build_edges 抓好的)。
把这些参考聚合,统计每篇外部论文**被语料内多少篇引用**(n_by):
  n_by 高 = 你这批文献共同的思想源头 → 却不在库里 = 真正该补的缺口。
**零 API 成本**(全用本地缓存),可反复跑。

去重范围:综述树语料 + 你的整个 Zotero 库(用最新 backup),避免把已有的当成缺口。

用法: python mine_gaps.py [--min 4] [--top 40]
"""
import glob, json, os, re, sys, unicodedata
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import load_state, norm_title

MIN_BY = 4
TOP = 40
for i, a in enumerate(sys.argv):
    if a == "--min": MIN_BY = int(sys.argv[i + 1])
    if a == "--top": TOP = int(sys.argv[i + 1])


def main():
    refs_cache = load_state("refs_cache.json", {})
    corpus = load_state("corpus.json", {})
    if not refs_cache:
        print("state/refs_cache.json 为空 —— 请先跑 build_edges.py"); return

    # ---- 已有:综述语料 + 全库 backup ----
    have_ax, have_t = set(), set()
    for k, n in corpus.items():
        if n.get("arxiv"): have_ax.add(n["arxiv"])
        t = norm_title(n.get("title", ""))
        if len(t) >= 10: have_t.add(t)
    bks = sorted(glob.glob(os.path.expanduser("~/.config/zotkit/backups/*.json")), key=os.path.getmtime)
    if bks:
        bk = json.load(open(bks[-1], encoding="utf-8"))
        items = bk if isinstance(bk, list) else bk.get("items", bk.get("data", []))
        for it in items:
            d = it.get("data", it)
            blob = " ".join(str(d.get(f, "")) for f in ("url", "extra", "archiveID", "DOI"))
            for ax in re.findall(r"(\d{4}\.\d{4,5})", blob): have_ax.add(ax)
            t = norm_title(d.get("title", ""))
            if len(t) >= 10: have_t.add(t)
        print(f"去重基准:综述语料 {len(corpus)} + 全库 backup {len(items)} 条")

    # ---- 聚合外部参考 ----
    agg = {}
    for src, refs in refs_cache.items():
        if src not in corpus: continue
        for r in refs or []:
            ax = (r.get("ax") or "").strip()
            t = norm_title(r.get("title", ""))
            if not t or len(t) < 10: continue
            if (ax and ax in have_ax) or t in have_t: continue     # 已有,不算缺口
            key = ax or t
            a = agg.setdefault(key, {"title": r.get("title", ""), "ax": ax,
                                     "year": r.get("year"), "cc": 0, "by": set()})
            a["by"].add(src)
            a["cc"] = max(a["cc"], r.get("cc") or 0)

    rows = [{"title": v["title"], "arxiv": v["ax"], "year": v["year"], "cc": v["cc"],
             "n_by": len(v["by"])} for v in agg.values() if len(v["by"]) >= MIN_BY]
    rows.sort(key=lambda x: (-x["n_by"], -(x["cc"] or 0)))
    from zotero_io import save_state
    save_state("gaps.json", rows)

    print(f"\n候选缺口(被语料内 ≥{MIN_BY} 篇引用、且不在你库里):{len(rows)} 篇")
    print(f"{'被引':>4} {'全局cc':>8}  {'年':>4}  标题")
    for r in rows[:TOP]:
        print(f"{r['n_by']:>4} {r['cc'] or 0:>8}  {str(r['year'] or '?'):>4}  {r['title'][:66]}")
    print(f"\n完整清单已存 state/gaps.json({len(rows)} 篇)")


if __name__ == "__main__":
    main()
