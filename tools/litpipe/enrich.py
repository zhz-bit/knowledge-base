#!/usr/bin/env python3
"""litpipe ③ enrich · 用 Haiku 做 ⭐评级 + 标题翻译,写回 Zotero

与早期版本的关键差别:**评级带上客观被引信号**
  · indeg = 语料内被引数(本综述里多少篇引用它)→ 对该领域正典的中心度
  · cc    = 全局被引数(Semantic Scholar)        → 广泛影响力
  两者由 ② build_edges 算好放在 state/corpus.json,所以本步**必须跑在 ② 之后**。
  LLM 在这两个锚上做调整(新论文被引少但重要要提;老而窄的工具要降)。

评级只用 ⭐ 星标签一种表示(用户要求单一真源);S=5⭐ A=4⭐ B=3⭐ C=2⭐。

用法:
  python enrich.py              # 干运行(只看会怎么评)
  python enrich.py --apply      # 写回 Zotero
  python enrich.py --limit 40   # 本轮只处理 40 篇
  python enrich.py --all        # 连已有 ⭐ 的也重评(统一标准用)
"""
import json, os, re, subprocess, sys, time
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zotero_io import Zot, load_state, save_state

APPLY = "--apply" in sys.argv
REDO_ALL = "--all" in sys.argv
LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit": LIMIT = int(sys.argv[i + 1])

CLAUDE = os.path.expanduser("~/.local/bin/claude")
MODEL = "claude-haiku-4-5"
BATCH = 14
STARS = {"S": 5, "A": 4, "B": 3, "C": 2}

RUBRIC = """你是自动驾驶文献助手。给每篇论文做两件事,只输出 JSON 数组。

(1) 评级 S/A/B/C —— 重要度,绝对标准(不在本批内相对比较)。
给了两个客观信号,**以它们为锚**:
  · indeg = 这批自动驾驶文献里有多少篇引用了它(领域正典中心度,最重要的信号)
  · cc    = 全球被引总数(广泛影响力)
分档参考:
  S = 奠基/里程碑:定义方向或被反复当基石引用。通常 indeg 很高(≥15)或 cc 极高且是驾驶/视觉基石
      (如 UniAD、VAD、nuScenes、CARLA、ResNet、Transformer、CLIP、BEVFormer、RELLIS-3D)。
  A = 重要代表作,被广泛采用。indeg 中高(约 5–14)或 cc 高。
  B = 扎实但增量/小众。indeg 低(1–4)。
  C = 边缘/影响有限。indeg 0 且无明显重要性。
**但要用判断修正锚**:2024–2026 的新论文天然 indeg/cc 低,若确属重要方向的代表作可给 A(甚至 S);
反之老而窄的工具即使 cc 不低也可给 B。数据集/基准是"使能者",同等 indeg 下可略高。

(2) 若该项 need_trans=true,把标题翻成自然中文;模型/方法/数据集名与缩写保留英文
   (Transformer/BEV/LiDAR/UniAD/GPT-4/VLA/NeRF/Gaussian Splatting 等)。need_trans=false 则 zh 填 ""。

输出格式:[{"i":序号,"tier":"S|A|B|C","zh":"中文标题或空"}],不要任何多余文字。"""


def call_haiku(batch):
    lines = []
    for j, b in enumerate(batch):
        lines.append(f'{j+1}. [{b["leaf"]}|{b["year"]}|{b["venue"] or "预印本"}|'
                     f'indeg={b["indeg"]}|cc={b["cc"]}|need_trans={str(b["need_trans"]).lower()}] {b["title"]}')
    prompt = RUBRIC + "\n\n论文:\n" + "\n".join(lines)
    for _ in range(3):
        try:
            r = subprocess.run([CLAUDE, "-p", prompt, "--model", MODEL],
                               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=240)
            m = re.search(r"\[\s*\{.*\}\s*\]", r.stdout, re.S)
            if m: return json.loads(m.group(0))
        except Exception:
            time.sleep(4)
    return None


def main():
    corpus = load_state("corpus.json", {})
    if not corpus:
        print("state/corpus.json 为空 —— 请先跑 build_edges.py"); return
    z = Zot()
    print("扫描 Zotero 取当前标签/翻译状态 ...")
    tree = z.scan_tree()

    todo = []
    for k, v in tree.items():
        d = v["data"]
        tags = [t.get("tag", "") for t in d.get("tags", [])]
        has_star = any("⭐" in t for t in tags)
        extra = d.get("extra", "") or ""
        need_trans = not re.search(r"titleTranslation:\s*\S", extra)
        if has_star and not need_trans and not REDO_ALL:
            continue
        c = corpus.get(k, {})
        todo.append({"key": k, "title": d.get("title", ""), "year": (d.get("date", "") or "")[:4],
                     "leaf": v["leaf"], "venue": d.get("proceedingsTitle") or d.get("publicationTitle") or "",
                     "indeg": c.get("indeg", 0), "cc": c.get("cc", 0),
                     "need_trans": need_trans, "version": v["version"], "data": d})
    if LIMIT: todo = todo[:LIMIT]
    print(f"待处理 {len(todo)} 篇(重评全部={REDO_ALL})")
    if not todo: return

    results = {}
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        arr = call_haiku(batch)
        if not arr:
            print(f"  批 {i//BATCH+1} 失败,跳过"); continue
        for obj in arr:
            idx = obj.get("i", 0) - 1
            if 0 <= idx < len(batch):
                results[batch[idx]["key"]] = {"tier": obj.get("tier", "B"), "zh": obj.get("zh", "")}
        print(f"  批 {i//BATCH+1}/{(len(todo)+BATCH-1)//BATCH} 完成,累计 {len(results)}")
        time.sleep(1)

    print(f"\n评级分布 {dict(Counter(v['tier'] for v in results.values()))}")
    if not APPLY:
        for k, v in list(results.items())[:8]:
            t = next(x for x in todo if x["key"] == k)
            print(f"  {v['tier']} (indeg{t['indeg']},cc{t['cc']}) {t['title'][:46]}")
        print("(加 --apply 写回 Zotero)"); return

    by_key = {t["key"]: t for t in todo}
    ok = 0
    for k, r in results.items():
        t = by_key.get(k)
        if not t: continue
        tier = r["tier"] if r["tier"] in STARS else "B"
        cur = t["data"]
        # extra:补 titleTranslation
        zh = (r.get("zh") or "").strip()
        lines = (cur.get("extra", "") or "").split("\n")
        if zh and not any(re.match(r"\s*titleTranslation\s*[:：]\s*\S", x) for x in lines):
            for j, x in enumerate(lines):
                if re.match(r"\s*titleTranslation\s*[:：]\s*$", x):
                    lines[j] = f"titleTranslation: {zh}"; break
            else:
                lines.append(f"titleTranslation: {zh}")
        cur["extra"] = "\n".join([x for x in lines if x.strip()])
        # tags:只留 ⭐ 一种评级表示
        cur["tags"] = [x for x in cur.get("tags", []) if "⭐" not in x.get("tag", "")] + \
                      [{"tag": "⭐" * STARS[tier]}]
        if z.put_item(k, cur, t["version"]): ok += 1
        time.sleep(0.32)
    print(f"写回成功 {ok}/{len(results)}")


if __name__ == "__main__":
    main()
