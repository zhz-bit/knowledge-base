#!/usr/bin/env python3
"""litpipe · 把解析好的批次建进 Zotero 并归类

读 state/batch_resolved.json,应用人工修正(FIX/DROP),按 LEAF 表归类建条目。
新桶(如神经科学)会自动创建。

用法:
  python create_batch.py          # 干运行
  python create_batch.py --apply
"""
import json, re, sys, time, urllib.request
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot
from lib_corpus import all_collections, _api_get as _api

APPLY = "--apply" in sys.argv

# —— 人工核查后的修正 ——
# 规律:自动检索里「名称是标题子串」的可信;**不是子串的都匹配错了**
FIX = {
    "Drive-OccWorld": {          # 自动匹配成了 OccWorld(另一篇 ECCV24),已联网确认
        "title": "Driving in the Occupancy World: Vision-Centric 4D Occupancy Forecasting "
                 "and Planning via World Models for Autonomous Driving",
        "ax": "2408.14197", "venue": "AAAI", "published": "2024-08-26",
    },
}
FIX["SuperMap: A Spatio-Temporal SLAM System for Visual-Language Navigation"] = {
    # 自动检索查无(RSS 论文不在 arXiv/OpenAlex),从用户给的 RSS PDF 直接抽取
    "title": "SuperMap: A Spatio-Temporal SLAM System for Visual-Language Navigation",
    "venue": "Robotics: Science and Systems", "published": "2026-07-01",
    "authors": ["Shibo Zhao", "Guofei Chen", "Honghao Zhu", "Zhiheng Li", "Changwei Yao",
                "Nader Zantout", "Seungchan Kim", "Wenshan Wang", "Ji Zhang", "Sebastian Scherer"],
    "summary": 'Robotic navigation in human environments requires a spatio-temporal semantic representation that can reconcile open-vocabulary perception with long-term environmental changes. While foundation models provide strong zero-shot recognition, their predictions are intermittent and view-dependent, and naively integrating them into mapping pipelines leads to identity drift and stale semantics over time. We present SuperMap, a 4D spatio-temporal mapping framework for language-guided navigation that integrates high-frequency geometric SLAM with asynchronous open-vocabulary perception. Our core contribution is a consistency-driven mapping engine that combines 3D-aware instance association/re-activation with a principled existence-andlabel confidence update to maintain stable object identities and prune outdated map content under occlusions and scene changes. SuperMap produces a queryable 4D scene-graph representation that interfaces naturally with Vision-Language Models by supporting compositional queries over object semantics, relations, and history. We demonstrate SuperMap on benchmarks and real robots, including dynamic scenes with appearance/disappearance and relocation, and provide ablations and runtime analysis. We release the full system as open-source to provide the community with a deployable baseline for open-vocabulary spatio-temporal mapping. Project website: superodometry.com/supermap',
    "ax": "", "doi": "",
}

DROP = {
    "WorkDrive",   # 自动匹配成 CogAD(0.50),联网也查不到此名,留给用户确认
}

TOPIC_TAG = "2026-07批次"

# —— 归类:新桶「8 神经科学与类脑智能」会自动建 ——
NEURO = "8 神经科学与类脑智能"
NEW_COLS = {                      # 新叶名 → 父分类名(None=顶层)
    NEURO: None,
    "8.1 神经编码与环路": NEURO,
    "8.2 脑网络与模块化": NEURO,
    "8.3 类脑空间智能与具身": NEURO,
    "8.4 神经科学 × LLM 表征对齐": NEURO,
}

# 每篇的目标叶(用**分类名**,脚本自己查 key);键 = batch_raw 里的 t 或 ax
LEAF = {
    # ── 自动驾驶:端到端 / 世界模型 / VLA ──
    "PrismAD": "模块化E2E",
    "2607.17521": "VLM-VLA",                    # GeoWorldAD
    "Drive-OccWorld": "1.2 端到端时代",
    "OccLLaMA": "1.2 端到端时代",
    "UniDriveVLA": "VLM-VLA",
    "ForgeDrive": "1.2 端到端时代",
    "OpenLongTail": "1.2 端到端时代",
    # ── 城区模块化感知 ──
    "SOCC-ICP": "感知",
    "Open-Vocabulary BEV Segmentation with 3D-Aware Geometric Constraints": "感知",
    "GaussianFusion: Unified 3D Gaussian Representation for Multi-Modal Fusion Perception": "感知",
    # ── SLAM / 里程计(越野模块化的几何层)──
    "FAST-LIVO2": "2.1.3.1 点云地面分割与几何原语提取",
    "SA-LIVO": "2.1.3.1 点云地面分割与几何原语提取",
    "MVOFormer": "2.1.3.1 点云地面分割与几何原语提取",
    "PathSpace": "2.1.3.2 高程图与概率地形建图",
    "SemCityLoc": "2.1.3.2 高程图与概率地形建图",
    "SuperMap: A Spatio-Temporal SLAM System for Visual-Language Navigation":
        "2.1.3.3 BEV 语义-几何联合建图与三维占用",
    "FlowDec": "2.1.4.4 野外在线自适应与免标注可通行性",
    "Embodied Artificial Intelligence for Off-Road Robot Navigation: A Review": "2.1.7 综述与评测基准",
    # ── VLN / 具身导航(公用基石的 VLA 叶)──
    "FutureNav: Unified World-Action Modeling for Vision-and-Language Navigation":
        "0.3.3 视觉-语言-动作(VLA)与具身基座",
    "SEDualVLN": "0.3.3 视觉-语言-动作(VLA)与具身基座",
    "CoFL-S: Spatially Queryable Sector Flow Fields for Local Language-Conditioned Navigation":
        "0.3.3 视觉-语言-动作(VLA)与具身基座",
    "SceneGraphGrounder: Zero-Shot 3D Visual Grounding via Structured Scene Graph Matching":
        "0.3.3 视觉-语言-动作(VLA)与具身基座",
    # ── 多模态 / 语言模型 ──
    "From Hallucination to Grounding: Diagnosing Visual Spatial Intelligence via CRISP":
        "0.3.2 多模态大模型与视觉指令微调",
    "Vision-OPD: Learning to See Fine Details for Multimodal LLMs via On-Policy Self-Distillation":
        "0.3.2 多模态大模型与视觉指令微调",
    "DSpark": "0.2.2 高效注意力与新型序列骨干",
    "2606.03979": "0.2.3 预训练语言模型与开源基座",   # Language Models Need Sleep
    "The Coverage Principle: How Pre-Training Enables Post-Training": "0.6.2 数学与分析工具",
    # ── 时空预测 ──
    "Physics-Informed Diffusion Models for Vehicle Speed Trajectory Generation":
        "3.1.1 经典交互与意图建模",
    # ── 神经科学(新桶)──
    "Triple-N dataset: large-scale fMRI-guided dense recordings of nonhuman primate neural responses to natural scenes":
        "8.1 神经编码与环路",
    "Subspace communication in the hippocampal-retrosplenial axis": "8.1 神经编码与环路",
    "Sparse-to-dense coding transformation between hippocampal areas CA3 and CA1": "8.1 神经编码与环路",
    "Flexible modularity in the human brain: How network architecture reconfigures over time":
        "8.2 脑网络与模块化",
    "A unifying framework from neural superposition to sparse interpretable codes":
        "8.2 脑网络与模块化",
    "Brain-inspired spatial intelligence for embodied agents": "8.3 类脑空间智能与具身",
    "Contextual Feature Extraction Hierarchies Converge in Large Language Models and the Brain":
        "8.4 神经科学 × LLM 表征对齐",
}


def creators(names):
    out = []
    for nm in (names or [])[:26]:
        nm = (nm or "").strip()
        if not nm:
            continue
        p = nm.rsplit(" ", 1)
        out.append({"creatorType": "author", "firstName": p[0], "lastName": p[1]}
                   if len(p) == 2 else {"creatorType": "author", "name": nm})
    return out


def main():
    rows = json.load(open(HERE / "state" / "batch_resolved.json", encoding="utf-8"))
    z = Zot()
    cols = all_collections(z)
    n2k = {}
    for k, v in cols.items():
        n2k.setdefault(v["name"], k)

    plan, skip = [], []
    for r in rows:
        key = r.get("t") or r.get("ax", "")
        if r.get("dup_key"):
            skip.append((key, f"已在库 {r['dup_key']}")); continue
        if key in DROP:
            skip.append((key, "自动匹配错误,联网也查不到,留待人工")); continue
        m = dict(r["meta"] or {})
        if key in FIX:
            m.update(FIX[key])
        if not m.get("title"):
            skip.append((key, "查无")); continue
        leaf = LEAF.get(key) or LEAF.get(r.get("ax", ""))
        if not leaf:                       # 简称键 vs 全标题:前缀匹配兜底
            for lk, lv in LEAF.items():
                if key.startswith(lk) or (len(lk) > 8 and lk in key):
                    leaf = lv; break
        if not leaf:
            skip.append((key, "★未指定归属")); continue
        plan.append({"raw": key, "m": m, "leaf": leaf})

    print(f"待建 {len(plan)} 篇 | 跳过 {len(skip)} 篇")
    print("\n归类分布:")
    for l, c in Counter(p["leaf"] for p in plan).most_common():
        mark = " ← 新建" if l in NEW_COLS else ("" if l in n2k else "  ⚠ 找不到该分类")
        print(f"  {l:42} {c:2}{mark}")
    print("\n跳过:")
    for k, why in skip:
        print(f"  {k[:56]:56} {why}")

    miss = {p["leaf"] for p in plan} - set(n2k) - set(NEW_COLS)
    if miss:
        print(f"\n⚠ 以下目标分类在库里找不到,先建好:{miss}")
        return
    if not APPLY:
        print("\n(加 --apply 执行)")
        return

    # 建新分类(先父后子)
    for name, parent in NEW_COLS.items():
        if name in n2k:
            continue
        body = {"name": name}
        if parent:
            body["parentCollection"] = n2k[parent]
        res = z.s.post(f"{z.base}/collections", json=[body], timeout=60).json()
        succ = res.get("successful", {})
        if succ:
            n2k[name] = list(succ.values())[0]["key"]
            print(f"  ✓ 建分类 {name}  {n2k[name]}")
        else:
            print(f"  ✗ 建分类失败 {name}: {json.dumps(res.get('failed', {}), ensure_ascii=False)[:150]}")
        time.sleep(0.3)

    # 补建保护:已在库的标题跳过(上一次可能部分成功)
    import unicodedata as _u
    def _n(t):
        return re.sub(r"[^0-9a-z]+", " ", _u.normalize("NFKC", t or "").lower()).strip()
    have = set()
    start = 0
    while True:
        d = _api(z, f"{z.base}/items/top?limit=100&start={start}")
        if not d:
            break
        for x in d:
            if x["data"].get("title"):
                have.add(_n(x["data"]["title"]))
        start += 100
        if len(d) < 100:
            break
    before = len(plan)
    plan = [p for p in plan if _n(p["m"]["title"]) not in have]
    if before != len(plan):
        print(f"  补建模式:{before - len(plan)} 篇已在库,跳过;实建 {len(plan)} 篇")

    items = []
    for p in plan:
        m, leaf = p["m"], p["leaf"]
        ax, doi = m.get("ax", ""), m.get("doi", "")
        pub = m.get("published", "") or ""
        it = {
            "itemType": "conferencePaper" if m.get("venue") else "preprint",
            "title": m["title"],
            "creators": creators(m.get("authors")),
            "abstractNote": m.get("summary", "") or "",
            "date": pub[:10] or "",
            "collections": [n2k[leaf]], "relations": {},
            "tags": [{"tag": TOPIC_TAG}],
        }
        if m.get("venue"):
            it["proceedingsTitle"] = m["venue"]
            if doi:
                it["DOI"] = doi
        else:
            it["repository"] = "arXiv" if ax else ""
        if ax:
            # archiveID 只对 preprint 合法,conferencePaper 会被 Zotero 以 400 拒绝
            if it["itemType"] == "preprint":
                it["archiveID"] = f"arXiv:{ax}"
            it["url"] = f"https://arxiv.org/abs/{ax}"
        elif doi:
            it["url"] = f"https://doi.org/{doi}"
            it["DOI"] = doi
        items.append(it)

    created = 0
    keys = []
    for i in range(0, len(items), 40):
        res = z.s.post(f"{z.base}/items", json=items[i:i + 40], timeout=90).json()
        succ = res.get("successful", {})
        created += len(succ)
        keys += [v["key"] for v in succ.values()]
        if res.get("failed"):
            print("  失败:", json.dumps(res["failed"], ensure_ascii=False)[:400])
        time.sleep(0.5)
    json.dump(keys, open(HERE / "state" / "batch_keys.json", "w"))
    print(f"\n已建 {created}/{len(items)} 条,key 写入 state/batch_keys.json")


if __name__ == "__main__":
    main()
