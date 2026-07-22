#!/usr/bin/env python3
"""litpipe · 缺口补录 —— 把 mine_gaps 挖出的候选筛选、归类、建进 Zotero

配合 mine_gaps.py 构成完整功能:
    mine_gaps.py  →  从引用网络发现"被反复引用却不在库"的论文(零 API)
    add_gaps.py   →  分桶筛选 + 抓 arXiv 元数据 + 按 taxonomy 归类 + 建条目

分桶:
  driving     驾驶/感知/规划/预测/点云/越野…… 本领域正典 → 全收(n_by ≥ --min)
  foundation  通用 CV/ML 地基(ResNet/DETR/LSTM/GPT…)→ 只收高频(n_by ≥ --min-fnd)
  noise       PDF 抽取残渣(license agreement 等)→ 丢弃
  other       其余 → 默认不收(--scope all 才收)

用法:
  python add_gaps.py                     # 干运行(默认 scope=b:driving+foundation)
  python add_gaps.py --apply
  python add_gaps.py --scope driving --apply
"""
import json, re, sys, time, html, urllib.request
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, load_state, save_state

APPLY = "--apply" in sys.argv
SCOPE = "b"
MIN_BY, MIN_FND = 4, 8
for i, a in enumerate(sys.argv):
    if a == "--scope": SCOPE = sys.argv[i + 1].lower()
    if a == "--min": MIN_BY = int(sys.argv[i + 1])
    if a == "--min-fnd": MIN_FND = int(sys.argv[i + 1])

NOISE = ("license agreement", "restrictions apply", "authorized licensed use",
         "downloaded on", "see discussions, stats", "all content following",
         "supplementary material", "appendix", "supplemental material", "erratum")

DRIVING = ("driving", "autonomous vehicle", "self-driving", "steering", "carla", "nuscenes",
           "kitti", "waymo", "lidar", "point cloud", "3d object detection", "bird's-eye",
           "bird eye", "bev", "occupancy", "lane", "traffic", "pedestrian", "trajectory",
           "motion planning", "motion prediction", "motion forecast", "behavior cloning",
           "imitation learning", "off-road", "offroad", "terrain", "traversab", "navigation",
           "robot", "vehicle", "collision", "freespace", "semantic map", "hd map")

FOUNDATION = ("resnet", "deep residual", "vgg", "very deep convolutional", "alexnet",
              "imagenet classification", "faster r-cnn", "feature pyramid", "focal loss",
              "object detection with transformers", "fully convolutional", "long short-term memory",
              "rnn encoder", "attention is all", "bert", "gpt", "generative pre-training",
              "unified text-to-text", "instruction-finetuned", "language models are",
              "microsoft coco", "adam", "batch normalization", "dropout", "u-net", "mask r-cnn",
              "yolo", "pointnet", "image is worth", "learning transferable visual",
              "denoising diffusion", "reduction of imitation learning", "segment anything")

# 归类:关键词 → taxonomy 叶子名(按名字模糊匹配当前树)
LEAF_DRIVING = [
    (("off-road", "offroad", "terrain", "traversab", "rugd", "rellis"), "2.1 模块化"),
    (("dataset", "benchmark", "kitti", "nuscenes", "waymo open", "cityscapes"), "3.1 城区"),
    (("occupancy", "occupanc"), "占用"),
    (("hd map", "lane graph", "vectorized map", "semantic map"), "建图"),
    (("motion prediction", "motion forecast", "trajectory pred", "social lstm"), "预测"),
    (("motion planning", "planner", "safe local motion"), "规划"),
    (("3d object detection", "point cloud", "lidar", "pointpillars", "frustum",
      "multi-view 3d", "continuous fusion", "detection network"), "感知"),
    (("vision-language", "vlm", "llm", "reason2drive", "chain-based reasoning"), "VLM-VLA"),
    (("reinforcement", "learning to drive in a day"), "RL后训练"),
    (("behavior cloning", "imitation", "chauffeurnet", "learning by cheating",
      "end to end learning", "end-to-end"), "模块化E2E"),
]

LEAF_FOUNDATION = [
    (("bert", "gpt", "language models are", "generative pre-training", "text-to-text",
      "instruction-finetuned", "rnn encoder", "long short-term memory", "attention is all",
      "phrase representations"), "0.2 语言模型"),
    (("clip", "learning transferable visual", "segment anything", "visual instruction"), "0.3 多模态基座"),
    (("diffusion", "generative adversarial", "variational autoencoder"), "0.4 生成模型"),
    (("reduction of imitation learning", "dagger", "adam:", "batch normalization",
      "dropout", "transfer learning"), "0.5 学习范式"),
    (("resnet", "deep residual", "vgg", "very deep convolutional", "alexnet",
      "imagenet classification", "faster r-cnn", "feature pyramid", "focal loss",
      "fully convolutional", "u-net", "mask r-cnn", "yolo", "pointnet", "image is worth",
      "object detection with transformers", "microsoft coco"), "0.1 视觉骨干"),
]


def bucket(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in NOISE) or len(t) < 12: return "noise"
    if any(k in t for k in DRIVING): return "driving"
    if any(k in t for k in FOUNDATION): return "foundation"
    return "other"


def pick_leaf(title, bkt, name2key):
    """桶决定搜哪套规则:地基只进 0.x,驾驶只进驾驶叶——避免 DETR 因含 end-to-end 被塞进驾驶。"""
    t = (title or "").lower()
    rules = LEAF_FOUNDATION if bkt == "foundation" else LEAF_DRIVING
    for kws, leaf in rules:
        if any(k in t for k in kws):
            for nm, ck in name2key.items():
                if leaf in nm: return nm, ck
    fallback = "0 公用基石" if bkt == "foundation" else "1.2 端到端时代"
    for nm, ck in name2key.items():
        if fallback in nm: return nm, ck
    return None, None


def fetch_arxiv(ids):
    out = {}
    for i in range(0, len(ids), 25):
        q = ",".join(ids[i:i + 25])
        try:
            xml = urllib.request.urlopen(urllib.request.Request(
                f"http://export.arxiv.org/api/query?id_list={q}&max_results=40",
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
    gaps = load_state("gaps.json", [])
    if not gaps:
        print("state/gaps.json 为空 —— 先跑 mine_gaps.py"); return
    for g in gaps: g["bucket"] = bucket(g["title"])
    print("候选分桶:", dict(Counter(g["bucket"] for g in gaps)))

    if SCOPE in ("driving", "a"): keep = [g for g in gaps if g["bucket"] == "driving" and g["n_by"] >= MIN_BY]
    elif SCOPE in ("all", "c"): keep = [g for g in gaps if g["bucket"] != "noise" and g["n_by"] >= MIN_BY]
    else:  # b = driving + 高频地基
        keep = [g for g in gaps if (g["bucket"] == "driving" and g["n_by"] >= MIN_BY)
                or (g["bucket"] == "foundation" and g["n_by"] >= MIN_FND)]
    keep.sort(key=lambda x: -x["n_by"])
    print(f"scope={SCOPE} → 选中 {len(keep)} 篇(driving≥{MIN_BY}, foundation≥{MIN_FND})")

    z = Zot()
    name2key = {}
    for k, v in z.collection_tree().items():
        name2key.setdefault(v["name"], k)

    ax_ids = [g["arxiv"] for g in keep if g.get("arxiv")]
    print(f"抓 arXiv 元数据 {len(ax_ids)} 篇 ...")
    meta = fetch_arxiv(ax_ids) if ax_ids else {}
    print(f"  命中 {len(meta)}")

    plan = []
    for g in keep:
        m = meta.get(g.get("arxiv") or "", {})
        title = m.get("title") or g["title"]
        leaf, ck = pick_leaf(title, g["bucket"], name2key)
        plan.append({**g, "title": title, "abstract": m.get("abstract", ""),
                     "date": m.get("date", "") or str(g.get("year") or ""),
                     "authors": m.get("authors", []), "leaf": leaf, "coll": ck, "hasmeta": bool(m)})
    save_state("gaps_plan.json", plan)
    print("\n归类分布:", dict(Counter(p["leaf"] or "❌未映射" for p in plan)))
    for p in plan[:30]:
        print(f'  by{p["n_by"]:>3} [{p["leaf"] or "❌"}] {"✓" if p["hasmeta"] else "⚠仅标题"} {p["title"][:56]}')
    if not APPLY:
        print(f"\n共 {len(plan)} 篇。(加 --apply 建条目)"); return

    def creators(names):
        out = []
        for nm in names[:30]:
            parts = nm.strip().rsplit(" ", 1)
            out.append({"creatorType": "author", "firstName": parts[0], "lastName": parts[1]}
                       if len(parts) == 2 else {"creatorType": "author", "name": nm})
        return out

    items = [{"itemType": "preprint" if p.get("arxiv") else "journalArticle",
              "title": p["title"], "creators": creators(p["authors"]),
              "abstractNote": p["abstract"], "date": p["date"],
              "collections": [p["coll"]] if p["coll"] else [], "relations": {},
              "tags": [{"tag": "补录:引用网络挖掘"}, {"tag": f"被引:{p['n_by']}"}],
              **({"repository": "arXiv", "archiveID": f"arXiv:{p['arxiv']}",
                  "url": f"https://arxiv.org/abs/{p['arxiv']}"} if p.get("arxiv") else {})}
             for p in plan if p["coll"]]
    ok = 0
    for i in range(0, len(items), 40):
        r = z.s.post(f"{z.base}/items", json=items[i:i + 40], timeout=90)
        res = r.json(); ok += len(res.get("successful", {}))
        if res.get("failed"): print("  失败:", json.dumps(res["failed"], ensure_ascii=False)[:300])
        time.sleep(1.2)
    print(f"\n新建 {ok}/{len(items)} 条 → 接着跑 build_edges → enrich → generate --apply")


if __name__ == "__main__":
    main()
