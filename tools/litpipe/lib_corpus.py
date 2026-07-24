#!/usr/bin/env python3
"""litlib ① corpus · 扫**整个 Zotero 库**,按真实分类体系推出泳道归属

与自驾页的 generate.py 不同的两点:
  · 不限定在「5 自动驾驶综述」这棵树下,走全库 8 个顶层桶
  · 泳道不硬编码:band = 顶层分类,lane = 二级分类,**完全由 Zotero 目录决定**,
    你在 Zotero 里加一个二级分类,页面就自动多一条泳道

取数策略:整库条目一次性分页拉完(约 14 个请求),再用 data.collections 反查归属,
比按分类逐个查(171 个请求)快一个量级。一篇挂多个分类时取**最深**的那条路径。

输出 state/lib_corpus.json,供 lib_layout.py 排版。

用法: python lib_corpus.py [--refresh]
"""
import json, re, sys, urllib.request
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, arxiv_of, load_state, save_state

# 事务性目录,不是文献,不进图谱
SKIP_BANDS = {"7 学校事务"}
FOUNDATION = "0 公用基石"          # 第一层:顶部横带,内部按子分类再分并列泳道
# 库里有**两个**基石目录:顶层的 V55TE2QG,和自驾树下的 9ZZWDKCB。
# 二者子分类 1:1 对应(「0.1 视觉与几何骨干」对「0.1 视觉骨干」…),按 0.x 前缀合并成一条带。
FOUND_ROOTS = {"V55TE2QG", "9ZZWDKCB"}
# 2026-07 重组后的 6 大类(叶子是 0.x.y,这里按 0.x 前缀归到大类做色系分组)
FOUND_LANES = {"0.1": "0.1 视觉", "0.2": "0.2 语言与序列",
               "0.3": "0.3 多模态与具身", "0.4": "0.4 三维几何与渲染",
               "0.5": "0.5 生成", "0.6": "0.6 学习理论与工具"}


def _api_get(z, url, tries=5):
    """Zotero API 偶发 SSL UNEXPECTED_EOF(瞬时),不重试会把整趟跑打断。"""
    import time as _t
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(url, headers=z.hdr), timeout=60).read())
        except Exception as e:
            if i == tries - 1:
                raise
            _t.sleep(2 * (i + 1))


def all_collections(z):
    """{key: {name, parent}} —— 全库,不限根。"""
    out, start = {}, 0
    while True:
        d = _api_get(z, f"{z.base}/collections?limit=100&start={start}")
        if not d:
            break
        for c in d:
            out[c["key"]] = {"name": c["data"]["name"],
                             "parent": c["data"].get("parentCollection") or None}
        start += 100
        if len(d) < 100:
            break
    # 补全每个分类的完整路径与它所属的顶层桶
    def chain(k):
        seq, seen = [], set()
        while k and k not in seen:
            seen.add(k)
            seq.append(out[k]["name"])
            k = out[k]["parent"]
        return list(reversed(seq))
    def is_found(k):
        seen = set()
        while k and k not in seen:
            if k in FOUND_ROOTS:
                return True
            seen.add(k); k = out[k]["parent"]
        return False
    for k in out:
        c = chain(k)
        out[k]["path"] = " / ".join(c)
        out[k]["depth"] = len(c)
        out[k]["found"] = is_found(k)
        if out[k]["found"]:
            # 基石:band 恒为第一层,lane 取 0.x 前缀对应的规范名
            out[k]["band"] = FOUNDATION
            pref = next((n[:3] for n in c if re.match(r"^0\.\d", n)), "")
            out[k]["lane"] = FOUND_LANES.get(pref, "0.9 其他基石")
        else:
            out[k]["band"] = c[0] if c else ""
            out[k]["lane"] = c[1] if len(c) > 1 else (c[0] if c else "")
    return out


def all_items(z):
    """整库顶层条目(不含附件/笔记),一次分页拉完。"""
    out, start = [], 0
    while True:
        d = _api_get(z, f"{z.base}/items/top?limit=100&start={start}")
        if not d:
            break
        for it in d:
            if it["data"].get("itemType") in ("attachment", "note"):
                continue
            out.append(it)
        start += 100
        if len(d) < 100:
            break
        print(f"  已取 {len(out)} 篇...", flush=True)
    return out


def arxiv_month(ax):
    """arXiv 号 YYMM.NNNNN 的前缀自带 **v1 首发年月**(2007-04 起启用该编号)。
    零成本,不用调 API。"""
    m = re.match(r"^(\d{2})(\d{2})\.\d{4,5}", str(ax or ""))
    if not m:
        return None
    yy, mm = int(m.group(1)), int(m.group(2))
    if not 1 <= mm <= 12:
        return None
    return (2000 + yy) * 12 + mm


def month_of(date):
    m = re.match(r"(\d{4})-(\d{2})", date or "")
    if m:
        return int(m.group(1)) * 12 + int(m.group(2))
    m = re.search(r"(\d{4})", date or "")
    return int(m.group(1)) * 12 + 6 if m else None


STAR2TIER = {5: "S", 4: "A", 3: "B", 2: "C"}


def main():
    z = Zot()
    print("取全库分类结构...", flush=True)
    cols = all_collections(z)
    print(f"  {len(cols)} 个分类", flush=True)
    print("取全库条目...", flush=True)
    items = all_items(z)
    print(f"  {len(items)} 篇", flush=True)

    st = load_state("corpus.json", {})        # build_edges 算好的 indeg/cc(目前只覆盖自驾树)
    nodes, stats = {}, Counter()
    for it in items:
        d = it["data"]
        mine = [cols[c] for c in d.get("collections", []) if c in cols]
        if not mine:
            stats["无分类"] += 1
            continue
        # 归属:**基石优先**(「基石类在第一层」——一篇只要挂在基石下,就归第一层横带,
        # 不因为它在别处有更深的路径而被推走;全库 122 篇跨桶多挂靠,其中 33 篇
        # 基石论文原本会被「最深路径优先」推给计算机视觉)。其余仍取最深路径。
        found = [c for c in mine if c["found"]]
        deep = max(found or mine, key=lambda c: c["depth"])
        if deep["band"] in SKIP_BANDS:
            stats["跳过·事务目录"] += 1
            continue
        m_pub = month_of(d.get("date", ""))          # 书目日期(发表年)
        m_ax = arxiv_month(arxiv_of(d))                # arXiv v1 首发
        # 时间轴取**最早公开日**:一篇 2022 年挂上 arXiv、2024 年才进会议的论文,
        # 从 2022 年起就已经在被引用了,按 2024 摆会让引用边逆着时间走。
        # 书目日期原样保留在 Zotero,这里只影响图上的纵坐标。
        m = min(x for x in (m_pub, m_ax) if x) if (m_pub or m_ax) else None
        if not m:
            stats["无日期"] += 1
            continue
        if m_pub and m_ax and m_pub - m_ax >= 6:
            stats["按arXiv首发提前"] += 1
        k = it["key"]
        tags = [t.get("tag", "") for t in d.get("tags", [])]
        stars = max([len(t) for t in tags if t and set(t) == {"⭐"}] or [0])
        ccf = next((t.split("-")[1] for t in tags if re.match(r"^CCF-[ABC]$", t)), "")
        # 开源仓库:detect_oss 写在 extra 的 `Code: <url>` 行
        cm = re.search(r"^Code:\s*(\S+)", d.get("extra", "") or "", re.M)
        code = cm.group(1) if cm else ""
        zh = ""
        mm = re.search(r"titleTranslation:\s*(\S.*)", d.get("extra", "") or "")
        if mm:
            zh = mm.group(1).strip()
        title = d.get("title", "") or ""
        nodes[k] = {
            "id": k, "key": k, "title": title, "name": (title.split(":")[0][:26] or k),
            "month": m, "year": f"{(m - 1) // 12}" if m else (d.get("date", "") or "")[:4],
            "pubyear": (d.get("date", "") or "")[:4],   # 书目发表年,tip 里与首发年并列
            "band": deep["band"], "lane": deep["lane"], "leaf": deep["name"], "path": deep["path"],
            # 泳道下沉到**最深**一级:基石两棵树的叶子按 0.x 前缀合并回同一条道
            "sub": deep["name"],
            "stars": stars, "tier": STAR2TIER.get(stars, ""), "ccf": ccf, "zh": zh,
            "arxiv": arxiv_of(d), "code": code,
            "doi": (d.get("DOI") or "").strip(),   # S2 批量接口靠它定位,漏了会退化成慢的标题检索
            "indeg": st.get(k, {}).get("indeg", 0), "cc": st.get(k, {}).get("cc", 0),
            "venue": d.get("proceedingsTitle") or d.get("publicationTitle") or "",
        }
        stats["入图"] += 1

    save_state("lib_corpus.json", nodes)
    print(f"\n语料 {len(nodes)} 篇 | " + " ".join(f"{k}:{v}" for k, v in stats.items() if k != "入图"))
    byband = Counter(n["band"] for n in nodes.values())
    print(f"\n{'桶':28} 篇数   泳道(二级分类)")
    for b, c in byband.most_common():
        lanes = Counter(n["lane"] for n in nodes.values() if n["band"] == b)
        mark = " ★第一层" if b == FOUNDATION else ""
        print(f"  {b:26} {c:4}{mark}")
        for ln, lc in lanes.most_common():
            print(f"      {ln:34} {lc:4}")
    print(f"\n有 ⭐ 评级 {sum(1 for n in nodes.values() if n['stars'])} | "
          f"有 CCF {sum(1 for n in nodes.values() if n['ccf'])} | "
          f"有引用数据(indeg/cc) {sum(1 for n in nodes.values() if n['indeg'] or n['cc'])}")


if __name__ == "__main__":
    main()
