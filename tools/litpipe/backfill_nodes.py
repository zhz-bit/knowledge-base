#!/usr/bin/env python3
"""litpipe · 回填「在页面上但不在 Zotero 树里」的节点

背景:早期靠引用挖掘加进图的祖先节点(src=anc)从没归档进 Zotero。
一旦按"Zotero 是唯一真源"重建页面,它们就会消失。本脚本把它们补进综述树,
让页面内容全部有 Zotero 背书。

做法:比对 页面现有 L.nodes 与 state/layout.json(新建的),找出差集 →
      从节点 id 取 arXiv → arXiv API 抓元数据 → 按 track/para 映射到 taxonomy 叶子 → 建条目。

用法: python backfill_nodes.py [--apply]
"""
import json, re, sys, time, html, unicodedata, urllib.request
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, load_state

APPLY = "--apply" in sys.argv
PAGE = HERE.parent.parent / "pages" / "e2e-autonomous-driving-vla.html"


def nt(t): return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", t or "").lower().split(":")[0])


# (track, para) → 综述树里的目标叶子名(按名字模糊匹配当前树)
LEAF_RULES = [
    (("shared", "foundation"), ["0 公用基石"]),
    (("urban", "dataset"), ["3.1 城区", "数据集"]),
    (("offroad", "dataset"), ["3.2 越野", "数据集"]),
    (("offroad", "modular"), ["2.1 模块化"]),
    (("offroad", "e2e"), ["2.2 端到端VLA", "2.2"]),
    (("urban", "modular"), ["1.1 模块化时代"]),
    (("urban", "e2e"), ["1.2 端到端时代"]),
]
# 子类更精确的落点(优先于上面的粗分)
SUB_RULES = {"感知": ["感知"], "建图": ["建图"], "预测规划": ["预测"], "占用": ["占用"],
             "端到端": ["模块化E2E", "1.2 端到端时代"]}


def fetch_arxiv(ids):
    out = {}
    for i in range(0, len(ids), 25):
        q = ",".join(ids[i:i + 25])
        try:
            xml = urllib.request.urlopen(
                urllib.request.Request(f"http://export.arxiv.org/api/query?id_list={q}&max_results=40",
                                       headers={"User-Agent": "litpipe/1.0"}), timeout=60).read().decode()
        except Exception:
            time.sleep(4); continue
        for e in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
            aid = re.search(r"<id>http://arxiv\.org/abs/([\d.]+)", e)
            if not aid: continue
            out[aid.group(1)] = {
                "title": html.unescape(re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", e, re.S).group(1)).strip()),
                "abstract": html.unescape(re.sub(r"\s+", " ", re.search(r"<summary>(.*?)</summary>", e, re.S).group(1)).strip()),
                "date": (re.search(r"<published>(\d{4}-\d{2}-\d{2})", e) or [None, ""])[1],
                "authors": [html.unescape(a.strip()) for a in re.findall(r"<author>\s*<name>(.*?)</name>", e, re.S)]}
        time.sleep(3)
    return out


def main():
    # 1) 差集
    h = PAGE.read_text(encoding="utf-8")
    i = h.find("const L = ")
    old = json.loads(h[i + 10: h.index("};", i) + 1])["nodes"]
    new = json.load(open(HERE / "state" / "layout.json", encoding="utf-8"))["nodes"]
    have = {nt(n["title"]) for n in new.values()}
    miss = [n for n in old.values() if nt(n["title"]) not in have]
    print(f"页面 {len(old)} | 新建 {len(new)} | 缺 {len(miss)}")

    # 2) 取 arXiv id(节点 id 形如 A_2203.17270)
    for n in miss:
        m = re.match(r"^[A-Z]_(\d{4}\.\d{4,5})$", n.get("id", "") or "")
        n["arxiv"] = m.group(1) if m else ""
    with_ax = [n for n in miss if n["arxiv"]]
    print(f"  有 arXiv 可自动补元数据 {len(with_ax)} | 无 arXiv {len(miss)-len(with_ax)}")

    # 3) 目标叶子
    z = Zot()
    tree = z.collection_tree()
    name2key = {}
    for k, v in tree.items():
        name2key.setdefault(v["name"], k)

    def pick_leaf(n):
        sub = n.get("sub", "")
        for cand in SUB_RULES.get(sub, []):
            for nm, k in name2key.items():
                if cand in nm: return nm, k
        for (tr, pa), cands in LEAF_RULES:
            if n.get("track") == tr and n.get("para") == pa:
                for cand in cands:
                    for nm, k in name2key.items():
                        if cand in nm: return nm, k
        return None, None

    meta = fetch_arxiv([n["arxiv"] for n in with_ax]) if with_ax else {}
    print(f"  arXiv 元数据命中 {len(meta)}")

    plan = []
    for n in miss:
        leaf, ck = pick_leaf(n)
        m = meta.get(n["arxiv"], {})
        plan.append({"title": m.get("title") or n["title"], "arxiv": n["arxiv"],
                     "abstract": m.get("abstract", ""), "date": m.get("date", "") or str(n.get("year", "")),
                     "authors": m.get("authors", []), "leaf": leaf, "coll": ck,
                     "indeg": n.get("indeg", 0), "hasmeta": bool(m)})
    print("\n目标叶子分布:", dict(Counter(p["leaf"] or "❌未映射" for p in plan)))
    for p in sorted(plan, key=lambda x: -x["indeg"]):
        print(f'  indeg{p["indeg"]:3} [{p["leaf"] or "❌"}] {"✓" if p["hasmeta"] else "⚠仅标题"} {p["title"][:52]}')

    if not APPLY:
        print("\n(加 --apply 建条目)"); return

    def creators(names):
        out = []
        for nm in names[:30]:
            parts = nm.strip().rsplit(" ", 1)
            out.append({"creatorType": "author", "firstName": parts[0], "lastName": parts[1]}
                       if len(parts) == 2 else {"creatorType": "author", "name": nm})
        return out

    items = []
    for p in plan:
        if not p["coll"]: continue
        it = {"itemType": "preprint" if p["arxiv"] else "journalArticle",
              "title": p["title"], "creators": creators(p["authors"]),
              "abstractNote": p["abstract"], "date": p["date"],
              "collections": [p["coll"]], "relations": {},
              "tags": [{"tag": "补录:页面回填"}]}
        if p["arxiv"]:
            it.update({"repository": "arXiv", "archiveID": f"arXiv:{p['arxiv']}",
                       "url": f"https://arxiv.org/abs/{p['arxiv']}"})
        items.append(it)
    ok = 0
    for i in range(0, len(items), 40):
        r = z.s.post(f"{z.base}/items", json=items[i:i + 40], timeout=90)
        res = r.json()
        ok += len(res.get("successful", {}))
        if res.get("failed"): print("  失败:", json.dumps(res["failed"], ensure_ascii=False)[:300])
        time.sleep(1.2)
    print(f"\n新建 {ok}/{len(items)} 条")


if __name__ == "__main__":
    main()
