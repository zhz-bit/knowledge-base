#!/usr/bin/env python3
"""litlib ② layout · 全库泳道排版

结构照用户定的形状:
  第一层(顶部横带) = 0 公用基石,内部按 5 个子分类分并列泳道
  第二层(主河流)   = 其余顶层桶并列,每桶内部再按二级分类分细泳道;纵轴 = 时间

泳道**完全由 Zotero 目录生成**(lib_corpus 的 band/lane 字段),不硬编码:
在 Zotero 里加一个二级分类,这里就自动多一条道,宽度按论文数分配。

输入 state/lib_corpus.json(含 indeg/cc) + state/lib_edges.json
输出 state/lib_layout.json
"""
import json, math, sys
from pathlib import Path
from collections import defaultdict, Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import load_state, save_state

FOUNDATION = "0 公用基石"

# 桶配色(第一层单独一色;其余按领域)
BAND_COL = {
    "0 公用基石":     "#b49bff",
    "5 自动驾驶综述": "#46d7cc",
    "4 时空序列预测": "#6aa6ff",
    "2 计算机视觉":   "#f0806c",
    "3 自然语言处理": "#f0bf4c",
    "1 深度学习":     "#8fd67a",
    "6 数据集":       "#e08fd0",
}
BAND_ORDER = ["5 自动驾驶综述", "4 时空序列预测", "2 计算机视觉",
              "3 自然语言处理", "1 深度学习", "6 数据集"]

PAD = 26            # 画布左右留白
LANE_GAP = 10       # 泳道间距
GROUP_GAP = 34      # 桶之间的间距
MIN_LANE = 62       # 泳道最小宽度(太窄放不下节点)
PX_PER_PAPER = 1.5  # 泳道宽度 ∝ 论文数
TOP_H = 300         # 第一层横带高度
ROW_H = 15          # 每月的纵向像素
XG, YG = 15, 15     # 同月多篇时的网格间距


def radius(indeg, cc):
    """点大小:主要看库内被引(indeg),全局被引(cc)只作微调,避免 ResNet 一家独大。"""
    r = 3.4 + (indeg ** 0.55) * 1.5
    if cc:
        r += min(2.4, math.log10(cc + 1) * 0.45)
    return round(min(r, 17), 1)


def pack(items, x0, x1, yof, taken):
    """把一组 (key, month) 放进泳道:同月的横向铺开,铺不下就换行(月内微调 y)。"""
    out = {}
    cx = (x0 + x1) / 2
    half = max(6.0, (x1 - x0) / 2 - 5)
    cols = max(1, int(half * 2 // XG))
    bym = defaultdict(list)
    for k, m in items:
        bym[m].append(k)
    for m, ks in sorted(bym.items()):
        for i, k in enumerate(ks):
            col = i % cols
            row = i // cols
            x = cx - half + XG * col + XG / 2 if cols > 1 else cx
            out[k] = (round(min(max(x, x0 + 5), x1 - 5), 1), round(yof(m) + row * YG, 1))
    return out


def main():
    C = load_state("lib_corpus.json", {})
    E = [tuple(e) for e in load_state("lib_edges.json", [])]
    if not C:
        raise SystemExit("先跑 lib_corpus.py")
    print(f"语料 {len(C)} 篇 | 边 {len(E)} 条")

    found = {k: n for k, n in C.items() if n["band"] == FOUNDATION}
    rest = {k: n for k, n in C.items() if n["band"] != FOUNDATION}

    # ---------- 泳道定义 ----------
    lanes = {}          # lane_id -> {x0,x1,label,band,col,n}
    x = PAD

    def add_lanes(band, pool):
        nonlocal x
        cnt = Counter(n["lane"] for n in pool.values())
        for lane, c in sorted(cnt.items()):
            w = max(MIN_LANE, c * PX_PER_PAPER)
            lid = f"{band}|{lane}"
            lanes[lid] = {"x0": round(x, 1), "x1": round(x + w, 1), "label": lane,
                          "band": band, "col": BAND_COL.get(band, "#999"), "n": c}
            x += w + LANE_GAP
        x += GROUP_GAP - LANE_GAP

    # 第一层:基石的 5 条道单独一套坐标(横带内)
    fx = PAD
    flanes = {}
    fcnt = Counter(n["lane"] for n in found.values())
    ftotal = sum(fcnt.values())
    for lane, c in sorted(fcnt.items()):
        w = max(140, c * 6.0)
        lid = f"{FOUNDATION}|{lane}"
        flanes[lid] = {"x0": round(fx, 1), "x1": round(fx + w, 1), "label": lane,
                       "band": FOUNDATION, "col": BAND_COL[FOUNDATION], "n": c}
        fx += w + LANE_GAP

    for band in BAND_ORDER:
        pool = {k: n for k, n in rest.items() if n["band"] == band}
        if pool:
            add_lanes(band, pool)
    # 目录里冒出的新桶(BAND_ORDER 没登记的)也不丢
    for band in sorted({n["band"] for n in rest.values()} - set(BAND_ORDER)):
        add_lanes(band, {k: n for k, n in rest.items() if n["band"] == band})

    W = max(x, fx) + PAD
    # 基石横带按比例铺满同样宽度
    if ftotal:
        scale = (W - 2 * PAD) / max(1, fx - PAD - LANE_GAP)
        for v in flanes.values():
            v["x0"] = round(PAD + (v["x0"] - PAD) * scale, 1)
            v["x1"] = round(PAD + (v["x1"] - PAD) * scale, 1)

    # ---------- 时间轴 ----------
    months = [n["month"] for n in rest.values()]
    m0, m1 = min(months), max(months)
    # 2015 之前的老论文压缩:否则 1958–2014 会拉出一大片空白
    CUT = 2015 * 12

    def yof2(m):
        """2015 前压进一条 120px 的窄带,之后按月线性展开 —— 否则 1958–2014 拉出一大片空白。"""
        if m < CUT:
            return TOP_H + 70 + (m - m0) / max(1, CUT - m0) * 120
        return TOP_H + 195 + (m - CUT) * ROW_H

    H = yof2(m1) + 90

    # ---------- 落点 ----------
    nodes = {}

    def emit(k, xx, yy, lid):
        n = C[k]
        nodes[k] = {"x": xx, "y": yy, "r": radius(n["indeg"], n["cc"]),
                    "lane": lid, "band": n["band"], "col": lanes.get(lid, flanes.get(lid, {})).get("col", "#999"),
                    "t": n["title"][:110], "zh": n.get("zh", ""), "y4": n["year"],
                    "tier": n["tier"], "ccf": n["ccf"], "indeg": n["indeg"], "cc": n["cc"],
                    "ax": n.get("arxiv", ""), "leaf": n["leaf"], "venue": (n.get("venue") or "")[:46]}

    # 第一层横带:道内按库内被引降序网格铺开。
    # 间距必须 ≥ 最大半径×2,否则大点(ResNet r=17)会糊成一条 —— 上一版用 17px 就糊了。
    for lid, ln in flanes.items():
        pool = [k for k, n in found.items() if f'{n["band"]}|{n["lane"]}' == lid]
        pool.sort(key=lambda k: -C[k]["indeg"])
        GX = GY = 34
        inner = ln["x1"] - ln["x0"] - 18
        cols = max(1, int(inner // GX))
        rows = math.ceil(len(pool) / cols) or 1
        # 竖向居中于横带内(带高 TOP_H-86,留出标题行)
        y_top = 92 + max(0, (TOP_H - 110 - rows * GY) / 2)
        for i, k in enumerate(pool):
            xx = ln["x0"] + 9 + GX / 2 + (i % cols) * GX
            yy = y_top + (i // cols) * GY
            emit(k, round(xx, 1), round(yy, 1), lid)

    for lid, ln in lanes.items():
        pool = [(k, C[k]["month"]) for k, n in rest.items() if f'{n["band"]}|{n["lane"]}' == lid]
        for k, (xx, yy) in pack(pool, ln["x0"], ln["x1"], yof2, None).items():
            emit(k, xx, yy, lid)

    edges = [[a, b] for a, b in E if a in nodes and b in nodes]
    L = {
        "nodes": nodes, "edges": edges,
        "lanes": {**flanes, **lanes},
        "bands": [{"name": b, "col": BAND_COL.get(b, "#999"),
                   "n": sum(1 for n in C.values() if n["band"] == b)}
                  for b in [FOUNDATION] + BAND_ORDER],
        "W": round(W), "H": round(H), "topH": TOP_H, "cut": CUT, "m0": m0, "m1": m1,
        "stats": {"n": len(nodes), "e": len(edges), "lanes": len(lanes) + len(flanes),
                  "found": len(found)},
    }
    save_state("lib_layout.json", L)
    print(f"画布 {L['W']}×{L['H']} | 节点 {len(nodes)} | 边 {len(edges)} | 泳道 {L['stats']['lanes']}")
    print(f"第一层基石 {len(found)} 篇 / {len(flanes)} 道;主河流 {len(rest)} 篇 / {len(lanes)} 道")


if __name__ == "__main__":
    main()
