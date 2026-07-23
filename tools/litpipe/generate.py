#!/usr/bin/env python3
"""litpipe ④ generate · 从 Zotero 重建页面数据并注入(纯渲染,不用 LLM/不联网抓取)

单一真源:节点、分类、评级、CCF、翻译**全部来自 Zotero**;引用边来自 ② build_edges 的 state/edges.json。
  · track/para 由该论文在综述树里的**最深分类路径**确定性推出(不靠标题关键词猜)
  · 评级取 Zotero 的 ⭐ 星标签 → 页面显示的 S/A/B/C 由它反推(消除"两套评级")
  · CCF 取 CCF-A/B/C 标签

用法:
  python generate.py           # 干运行:重建数据、报告差异,不改页面
  python generate.py --apply   # 重建并注入页面
"""
import json, re, subprocess, sys
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, arxiv_of, load_state, save_state, STATE

APPLY = "--apply" in sys.argv
PAGE = HERE.parent.parent / "pages" / "e2e-autonomous-driving-vla.html"
STAR2TIER = {5: "S", 4: "A", 3: "B", 2: "C"}


def derive(path: str):
    """综述树里的分类路径 → (track, para)。确定性,优于标题关键词猜测。"""
    s = path or ""
    if "公用基石" in s: return ("shared", "foundation")
    if "1 城区结构化" in s:
        return ("urban", "e2e") if ("1.2" in s or "端到端" in s) else ("urban", "modular")
    if "2 非结构化越野" in s:
        return ("offroad", "e2e") if ("2.2" in s or "端到端" in s) else ("offroad", "modular")
    if "3 数据集" in s:
        return ("offroad", "dataset") if ("3.2" in s or "越野" in s) else ("urban", "dataset")
    return ("urban", "e2e")


def month_of(date: str):
    m = re.match(r"(\d{4})-(\d{2})", date or "")
    if m: return int(m.group(1)) * 12 + int(m.group(2))
    m = re.search(r"(\d{4})", date or "")
    return int(m.group(1)) * 12 + 6 if m else None


def build_corpus():
    z = Zot()
    print("扫描 Zotero 综述树(取最深分类路径)...")
    tree = z.scan_tree()
    st = load_state("corpus.json", {})          # ② 算好的 indeg / cc
    nodes, no_month, in_inbox = {}, 0, 0
    for k, v in tree.items():
        d = v["data"]
        # 收件箱(待分类)里的条目不进图谱:它们没有语义分类,
        # derive() 会把它们全推成默认 urban/e2e,污染泳道
        if any(x in (v.get("leaf") or "") for x in ("_收件箱", "待分类")):
            in_inbox += 1; continue
        m = month_of(d.get("date", ""))
        if not m:
            no_month += 1; continue
        track, para = derive(v["path"])
        tags = [t.get("tag", "") for t in d.get("tags", [])]
        stars = max([len(t) for t in tags if t and set(t) == {"⭐"}] or [0])
        ccf = next((t.split("-")[1] for t in tags if re.match(r"^CCF-[ABC]$", t)), "")
        title = d.get("title", "") or ""
        zh = ""
        mm = re.search(r"titleTranslation:\s*(\S.*)", d.get("extra", "") or "")
        if mm: zh = mm.group(1).strip()
        nodes[k] = {
            "id": k, "key": k, "name": (title.split(":")[0][:22] or k), "title": title,
            "month": m, "year": (d.get("date", "") or "")[:4],
            "track": track, "para": para, "col": v["leaf"], "src": "lib",
            "arxiv": arxiv_of(d),
            # —— 单一真源:以下全来自 Zotero ——
            "stars": stars, "tier": STAR2TIER.get(stars, ""), "ccf": ccf, "zh": zh,
            "indeg": st.get(k, {}).get("indeg", 0), "cc": st.get(k, {}).get("cc", 0),
            "venue": d.get("proceedingsTitle") or d.get("publicationTitle") or "",
        }
    print(f"语料 {len(nodes)} 篇(无日期丢弃 {no_month} | 收件箱待分类跳过 {in_inbox})")
    print("  track/para:", dict(Counter((n['track'], n['para']) for n in nodes.values())))
    print("  评级(来自⭐):", dict(Counter(n['tier'] or '未评' for n in nodes.values())))
    print("  CCF:", dict(Counter(n['ccf'] or '-' for n in nodes.values())))
    save_state("layout_corpus.json", nodes)
    return nodes


def run_layout():
    r = subprocess.run([sys.executable, str(HERE / "layout.py")],
                       capture_output=True, text=True)
    print(r.stdout.strip()[-400:] or r.stderr.strip()[-400:])
    if r.returncode != 0:
        raise SystemExit("layout 失败")
    return json.load(open(STATE / "layout.json", encoding="utf-8"))


def inject(L):
    """只替换页面里 `const L = {...};` 那一行,保留渲染器与页面结构。"""
    html = PAGE.read_text(encoding="utf-8")
    lines = html.split("\n")
    hit = next((i for i, l in enumerate(lines)
                if l.lstrip().startswith("const L = {") and l.rstrip().endswith("};")), None)
    if hit is None:
        raise SystemExit("找不到页面里的 const L 注入点")
    indent = lines[hit][:len(lines[hit]) - len(lines[hit].lstrip())]
    blob = json.dumps(L, ensure_ascii=False, separators=(",", ":"))
    lines[hit] = f"{indent}const L = {blob};"
    PAGE.write_text("\n".join(lines), encoding="utf-8")
    print(f"已注入页面(行 {hit+1}) 节点 {len(L['nodes'])} 边 {len(L['edges'])} 画布 {L['W']}x{L['H']}")


def main():
    build_corpus()
    L = run_layout()
    # 把评级/CCF 带进节点(供页面显示徽章)
    corpus = load_state("layout_corpus.json", {})
    for k, n in L["nodes"].items():
        c = corpus.get(k)
        if c:
            n["tier"] = c["tier"]; n["ccf"] = c["ccf"]; n["key"] = k
            if c.get("zh"): n["zh"] = c["zh"]
    save_state("layout.json", L)
    if APPLY:
        inject(L)
    else:
        old = re.search(r'"stats":\{"n":(\d+)', PAGE.read_text(encoding="utf-8"))
        print(f"\n干运行:页面现有 {old.group(1) if old else '?'} 节点 → 新建 {len(L['nodes'])} 节点")
        print("(加 --apply 注入页面)")


if __name__ == "__main__":
    main()
