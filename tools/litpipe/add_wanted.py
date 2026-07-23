#!/usr/bin/env python3
"""litpipe · 按标题清单补录文献到 Zotero

输入 state/wanted_missing.json:[{sec, stars, title, year, venue}, ...]
流程:标题 → Semantic Scholar 搜索取权威元数据(作者/年份/venue/DOI/arXiv/摘要)
      → 建 Zotero 条目 → 按 sec 归到 taxonomy 叶子 → 打 ⭐ 星标签

查不到元数据的**不臆造**:只用清单里的标题/年份建条目,并打 `元数据待补` 标签。

用法:
  python add_wanted.py          # 干运行:只报告将建什么
  python add_wanted.py --apply  # 真建
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, load_state

APPLY = "--apply" in sys.argv

# 逐篇指定叶子(用分类名,脚本自己查 key)。**不按分节一刀切**:
# 分节是按研究问题分的,同一节里的论文常分属不同 taxonomy 叶——
# 例如第 1 节里 T4P 是轨迹预测、EVOLVE-VLA 是 VLA、MindDrive 是在线 RL。
# 键取标题前 34 字符(归一化后),足以唯一定位这 22 篇。
TITLE2LEAF = {
    # ── 1 延迟反馈与在线预测适应 ──
    "online adaptation of neural netwo": "预测",
    "t4p test time training of trajecto": "预测",
    "expanding the deployment envelope ": "预测",
    "test time training for visual fore": "VLM-VLA",
    "test time perturbation learning wi": "VLM-VLA",
    "evolve vla test time training from": "VLM-VLA",
    "minddrive a vision language action": "RL后训练",
    # ── 2 非结构化驾驶 VLM/VLA ──
    "reasoning about traversability lan": "2.2 端到端VLA",
    "anytraverse an off road traversabi": "2.1 模块化",   # 零样本分割+人在环,不是端到端规划
    # ── 3 在线越野可通行性与具身反馈 ──
    "salon self supervised adaptive lea": "2.1 模块化",
    "top nav legged navigation integrat": "2.1 模块化",
    "learning on the drive self supervi": "2.1 模块化",
    "learning smooth state dependent tr": "2.1 模块化",
    # ── 4 贝叶斯后验、概率地图与风险规划 ──
    "meta learning priors for efficient": "0.5 学习范式",  # ALPaCA 是通用方法,属基石
    "step stochastic traversability eva": "2.1 模块化",
    "uncertainty aware accurate elevati": "2.1 模块化",
    # ── 5 TTT/TTA 方法论基础(全部归公用基石)──
    "test time training with self super": "0.5 学习范式",
    "tent fully test time adaptation by": "0.5 学习范式",
    "continual test time domain adaptat": "0.5 学习范式",
    "efficient test time model adaptati": "0.5 学习范式",
    "note robust continual test time ad": "0.5 学习范式",
    "robust test time adaptation in dyn": "0.5 学习范式",
}


def leaf_of(title):
    """按归一化标题的**前缀**匹配 —— 手写截断键容易差一两个字符,前缀匹配免疫。"""
    k = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    for pre, leaf in TITLE2LEAF.items():
        if k.startswith(pre):
            return leaf
    return None


TOPIC_TAG = "延迟物理反馈"       # 统一打上,便于日后在 Zotero 里一键捞出这条线


def _s2_key():
    f = os.path.expanduser("~/.config/zotkit/env")
    try:
        for ln in open(f, encoding="utf-8"):
            if ln.strip().startswith("S2_API_KEY") and "=" in ln:
                return ln.split("=", 1)[1].strip().strip('"\'')
    except Exception:
        pass
    return ""


S2_KEY = _s2_key()
HDR = {"User-Agent": "litpipe/1.0"}
if S2_KEY:
    HDR["x-api-key"] = S2_KEY
SLEEP = 0.3        # OpenAlex 礼貌池不需要保守限速

FIELDS = "title,year,venue,externalIds,abstract,authors,publicationTypes,citationCount"


# 元数据走 OpenAlex,不走 Semantic Scholar:
# 匿名 S2 是全球共享 100 次/5 分钟的池子,几乎每请求必吃 429,单篇会被退避拖到一分半;
# OpenAlex 免费无 key、10 万次/天,带 mailto 进礼貌池,实测 ~1.1 秒/次。
OA = "https://api.openalex.org/works"
OA_HDR = {"User-Agent": "litpipe/1.0 (mailto:h.geo.ai@gmail.com)"}
OA_SELECT = ("id,doi,title,publication_year,cited_by_count,authorships,"
             "primary_location,abstract_inverted_index,type")


def _abstract(inv):
    """OpenAlex 存的是倒排索引,还原成正文。"""
    if not inv:
        return ""
    pos = {}
    for w, idxs in inv.items():
        for i in idxs:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))


def s2_search(title, tries=3):
    q = urllib.parse.quote(re.sub(r"[^\w\s:.-]", " ", title)[:200])
    url = f"{OA}?per-page=3&select={OA_SELECT}&filter=title.search:{q}"
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=OA_HDR), timeout=45)
            res = json.loads(r.read()).get("results") or []
            out = []
            for w in res:
                loc = (w.get("primary_location") or {}).get("source") or {}
                doi = (w.get("doi") or "").replace("https://doi.org/", "")
                ax = ""
                m = re.match(r"10\.48550/arxiv\.(.+)$", doi, re.I)
                if m:
                    ax = m.group(1); doi = ""
                out.append({
                    "title": w.get("title") or "",
                    "year": w.get("publication_year"),
                    "venue": (loc.get("display_name") or "") if "arxiv" not in (loc.get("display_name") or "").lower() else "",
                    "externalIds": {"DOI": doi, "ArXiv": ax},
                    "abstract": _abstract(w.get("abstract_inverted_index")),
                    "authors": [{"name": (a.get("author") or {}).get("display_name", "")}
                                for a in (w.get("authorships") or [])],
                    "citationCount": w.get("cited_by_count", 0),
                })
            return out
        except Exception:
            time.sleep(2 + 2 * i)
    return []


def norm(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def pick(cands, want_title, want_year):
    """从搜索结果里挑真正对得上的那条:标题相似 + 年份不冲突。宁可放弃也不硬认。"""
    wn = norm(want_title)
    best = None
    for c in cands:
        cn = norm(c.get("title", ""))
        if not cn:
            continue
        # 词集合重合度
        a, b = set(wn.split()), set(cn.split())
        ov = len(a & b) / max(1, len(a | b))
        if ov < 0.55:
            continue
        y = c.get("year")
        if y and want_year and abs(int(y) - int(want_year)) > 2:
            continue
        if best is None or ov > best[0]:
            best = (ov, c)
    return best[1] if best else None


def creators(authors):
    out = []
    for a in (authors or [])[:24]:
        nm = (a.get("name") or "").strip()
        if not nm:
            continue
        parts = nm.rsplit(" ", 1)
        out.append({"creatorType": "author",
                    "firstName": parts[0] if len(parts) == 2 else "",
                    "lastName": parts[-1]} if len(parts) == 2 else
                   {"creatorType": "author", "name": nm})
    return out


def main():
    want = json.load(open(HERE / "state" / "wanted_missing.json", encoding="utf-8"))
    z = Zot()
    tree = z.collection_tree(ttl=0)                # 取新鲜结构
    name2key = {}
    for k, v in tree.items():
        name2key.setdefault(v["name"], k)
    unmapped = [w["title"] for w in want if not leaf_of(w["title"])]
    if unmapped:
        print("以下论文没有指定归属,先补 TITLE2LEAF:")
        for t in unmapped: print("   ", re.sub(r"[^a-z0-9]+"," ",t.lower()).strip()[:34], "|", t[:60])
        return
    missing_leaf = {leaf_of(w["title"]) for w in want} - set(name2key)
    if missing_leaf:
        print("以下目标分类在 Zotero 里找不到,先建好再跑:", missing_leaf)
        return

    print(f"待补录 {len(want)} 篇" + ("" if APPLY else "(干运行)"))
    rows = []
    for i, w in enumerate(want):
        cands = s2_search(w["title"])
        m = pick(cands, w["title"], w.get("year"))
        ext = (m or {}).get("externalIds") or {}
        rows.append({
            "want": w, "meta": m,
            "arxiv": ext.get("ArXiv", ""), "doi": ext.get("DOI", ""),
        })
        tag = "✓" if m else "✗查无"
        got = f'{(m or {}).get("year","?")} {((m or {}).get("venue") or "")[:26]}' if m else ""
        print(f'  {tag} {w["title"][:56]:56} {got}', flush=True)
        time.sleep(SLEEP)

    ok = [r for r in rows if r["meta"]]
    print(f"\n拿到权威元数据 {len(ok)}/{len(rows)};其余用清单原文建条目并打「元数据待补」")
    print("归类分布:", dict(Counter(leaf_of(r["want"]["title"]) for r in rows)))
    if not APPLY:
        print("\n(加 --apply 真建)")
        return

    items = []
    for r in rows:
        w, m = r["want"], r["meta"]
        leaf = name2key[leaf_of(w["title"])]
        tags = [{"tag": "⭐" * w["stars"]}, {"tag": TOPIC_TAG}]
        if not m:
            tags.append({"tag": "元数据待补"})
        it = {
            "itemType": "preprint" if (r["arxiv"] and not (m or {}).get("venue")) else
                        ("conferencePaper" if (m or {}).get("venue") else "preprint"),
            "title": (m or {}).get("title") or w["title"],
            "creators": creators((m or {}).get("authors")),
            "abstractNote": (m or {}).get("abstract") or "",
            "date": str((m or {}).get("year") or w.get("year") or ""),
            "url": f"https://arxiv.org/abs/{r['arxiv']}" if r["arxiv"] else "",
            "DOI": r["doi"],
            "collections": [leaf], "relations": {}, "tags": tags,
        }
        if it["itemType"] == "conferencePaper":
            it["proceedingsTitle"] = (m or {}).get("venue") or w.get("venue") or ""
            it.pop("url", None) if not r["arxiv"] else None
        else:
            it["repository"] = "arXiv" if r["arxiv"] else ""
            if r["arxiv"]:
                it["archiveID"] = f"arXiv:{r['arxiv']}"
            # preprint 也保留 DOI:很多论文有正式 DOI 但 OpenAlex 没给 venue 名,
            # 之前一律 pop 掉,结果 9 篇既无链接也无 DOI,后续抓 PDF/引用都定位不到
            if not it.get("DOI"):
                it.pop("DOI", None)
            elif not it.get("url"):
                it["url"] = "https://doi.org/" + it["DOI"]
        items.append(it)

    created = 0
    for i in range(0, len(items), 40):
        batch = items[i:i + 40]
        resp = z.s.post(f"{z.base}/items", json=batch, timeout=90).json()
        created += len(resp.get("successful", {}))
        if resp.get("failed"):
            print("  失败:", json.dumps(resp["failed"], ensure_ascii=False)[:400])
    print(f"\n已建 {created}/{len(items)} 条")


if __name__ == "__main__":
    main()
