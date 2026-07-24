#!/usr/bin/env python3
"""litpipe · 批量解析论文清单 → 元数据 + 查重

输入 state/batch_raw.json:[{t: 标题或名称, ax?: arXiv号, hint?: 检索线索, d: 备注}]
三级解析:
  ① 有 arXiv 号 → arXiv API 直接取(最准,含 v1 首发日)
  ② 有完整标题 → arXiv 标题检索 → OpenAlex 标题检索
  ③ 只有名称(如 "StreamPETR") → 用 hint 走 arXiv 全字段检索,取最相关

对全库查重,已在库的跳过。输出 state/batch_resolved.json。

用法: python resolve_batch.py
"""
import difflib, json, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot
from lib_corpus import all_items

UA = {"User-Agent": "litpipe/1.0 (mailto:h.geo.ai@gmail.com)"}
OA = "https://api.openalex.org/works"
AX = "http://export.arxiv.org/api/query"


def norm(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z一-鿿]+", " ", t)).strip()


def sim(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    sa, sb = set(na.split()), set(nb.split())
    return max(difflib.SequenceMatcher(None, na, nb).ratio(),
               len(sa & sb) / max(1, len(sa | sb)))


def get(url, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45).read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(4 * (i + 1)); continue
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return b""


def parse_ax(xml):
    """arXiv Atom → [{title, ax, published, summary, authors, doi, journal_ref}]"""
    out = []
    for e in xml.decode("utf-8", "replace").split("<entry>")[1:]:
        g = lambda p: (re.search(p, e, re.S).group(1).strip() if re.search(p, e, re.S) else "")
        idu = g(r"<id>http://arxiv\.org/abs/([^<]+)</id>")
        out.append({
            "title": " ".join(g(r"<title>(.*?)</title>").split()),
            "ax": re.sub(r"v\d+$", "", idu),
            "published": g(r"<published>(.*?)</published>")[:10],
            "summary": " ".join(g(r"<summary>(.*?)</summary>").split()),
            "authors": re.findall(r"<name>(.*?)</name>", e),
            "doi": g(r'<arxiv:doi[^>]*>(.*?)</arxiv:doi>'),
            "venue": g(r'<arxiv:journal_ref[^>]*>(.*?)</arxiv:journal_ref>'),
        })
    return out


def by_ids(axs):
    """**一次 id_list 拿多条** —— 逐条调用会把自己打成限流(实测单条 79 秒,
    批量 12 条只要 2.3 秒)。返回 {去版本号的 ax: meta}。"""
    out = {}
    for i in range(0, len(axs), 25):
        chunk = [a for a in axs[i:i + 25] if a]
        if not chunk:
            continue
        for r in parse_ax(get(f"{AX}?id_list={','.join(chunk)}&max_results=40")):
            out[re.sub(r"v\d+$", "", r["ax"])] = r
        time.sleep(3.1)
    return out


def search_ax(q, field="all", n=6):
    return parse_ax(get(f"{AX}?search_query={field}:{urllib.parse.quote(q)}"
                        f"&sortBy=relevance&max_results={n}"))


def _abstract(inv):
    if not inv:
        return ""
    pos = {}
    for w, ix in inv.items():
        for i in ix:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))


def search_oa(q, n=5):
    sel = "id,doi,title,publication_year,publication_date,cited_by_count,authorships,primary_location,abstract_inverted_index,type"
    raw = get(f"{OA}?per-page={n}&select={sel}&filter=title.search:"
              f"{urllib.parse.quote(re.sub(r'[^\w\s:.-]', ' ', q)[:200])}")
    if not raw:
        return []
    out = []
    for w in (json.loads(raw).get("results") or []):
        loc = (w.get("primary_location") or {}).get("source") or {}
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        ax = ""
        m = re.match(r"10\.48550/arxiv\.(.+)$", doi, re.I)
        if m:
            ax, doi = m.group(1), ""
        out.append({"title": w.get("title") or "", "ax": ax, "doi": doi,
                    "published": w.get("publication_date") or "",
                    "venue": loc.get("display_name") or "",
                    "summary": _abstract(w.get("abstract_inverted_index")),
                    "authors": [(a.get("author") or {}).get("display_name", "")
                                for a in (w.get("authorships") or [])],
                    "cc": w.get("cited_by_count", 0)})
    return out


def main():
    raw = json.load(open(HERE / "state" / "batch_raw.json", encoding="utf-8"))
    print("扫全库建查重索引 ...", flush=True)
    lib = []
    for it in all_items(Zot()):
        d = it["data"]
        if d.get("title"):
            lib.append((norm(d["title"]), it["key"], d["title"]))
    print(f"  库内 {len(lib)} 篇\n")

    # ① 所有 arXiv 号一次批量取回
    axmap = by_ids([r.get("ax", "") for r in raw])
    print(f"批量取回 arXiv {len(axmap)} 条\n", flush=True)

    rows = []
    for i, r in enumerate(raw, 1):
        want, ax, hint = r.get("t", ""), r.get("ax", ""), r.get("hint", "")
        cand = None
        how = ""
        if ax:
            cand, how = axmap.get(re.sub(r"v\d+$", "", ax)), "arXiv号"
        # ② 完整标题:OpenAlex 优先(1s/次),比 arXiv 搜索快一个量级
        if not cand and want and len(want) > 24:
            for c in search_oa(want):
                if sim(c["title"], want) > 0.62:
                    cand, how = c, "OpenAlex"; break
        # ③ 只有名称:用线索走 arXiv 全字段检索(慢,故放最后且限速)
        if not cand:
            q = hint or want
            best = (0, None)
            for c in search_ax(q, "all", 8):
                sc = max(sim(c["title"], want), sim(c["title"], q) * 0.9)
                if want and len(norm(want)) > 4 and norm(want) in norm(c["title"]):
                    sc = max(sc, 0.8)
                if sc > best[0]:
                    best = (sc, c)
            time.sleep(3.1)
            if best[0] > 0.5:
                cand, how = best[1], f"arXiv检索{best[0]:.2f}"
            else:                                  # 再退回 OpenAlex 用线索搜
                for c in search_oa(q):
                    if max(sim(c["title"], want), sim(c["title"], q)) > 0.55:
                        cand, how = c, "OpenAlex线索"; break

        got = cand["title"] if cand else ""
        # 查重
        dupk = dupt = ""
        probe = got or want
        if probe:
            np = norm(probe)
            for nl, k, t in lib:
                if nl == np or (len(np) > 22 and (np in nl or nl in np)
                                and min(len(np), len(nl)) / max(len(np), len(nl)) > 0.75) \
                   or difflib.SequenceMatcher(None, np, nl).ratio() > 0.9:
                    dupk, dupt = k, t; break

        rows.append({**r, "meta": cand, "how": how, "dup_key": dupk, "dup_title": dupt})
        mark = "◆已在库" if dupk else ("✓" if cand else "✗查无")
        print(f"{i:3}. {mark:6} [{how:12}] {(want or ax)[:44]:44} → {got[:46]}", flush=True)
        time.sleep(0.4)

    json.dump(rows, open(HERE / "state" / "batch_resolved.json", "w"),
              ensure_ascii=False, indent=1)
    ok = [r for r in rows if r["meta"] and not r["dup_key"]]
    dup = [r for r in rows if r["dup_key"]]
    no = [r for r in rows if not r["meta"] and not r["dup_key"]]
    print(f"\n可新建 {len(ok)} | 已在库 {len(dup)} | 查无 {len(no)}")
    if dup:
        print("\n已在库(跳过):")
        for r in dup:
            print(f"   {r['dup_key']}  {r['dup_title'][:62]}")
    if no:
        print("\n查无(需人工给链接):")
        for r in no:
            print(f"   {(r.get('t') or r.get('ax'))[:60]}   备注:{r.get('d','')}")


if __name__ == "__main__":
    main()
