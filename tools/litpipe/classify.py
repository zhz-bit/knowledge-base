#!/usr/bin/env python3
"""litpipe · 收件箱自动归类(Haiku)

工作流:新论文一律先丢进「_收件箱(待分类)」,不必当场决定放哪。
本步骤读收件箱里的条目 → Haiku 依据标题/摘要建议 taxonomy 叶子:
  · 高置信 → **自动归档**(移出收件箱、放进目标叶子)
  · 中/低置信 → 留在收件箱,打 `建议分类:XXX` 标签等你确认(收件箱本身即安全网)

为什么分类必须单独一步:venue/CCF/评级/翻译都与分类无关,可以先做;
只有 track/para(图谱泳道)依赖分类路径,所以未归类的条目由 generate 排除,不进图谱。

用法: python classify.py [--apply] [--limit N]
"""
import json, os, re, subprocess, sys, time
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, ROOT_COLLECTION

APPLY = "--apply" in sys.argv
LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit": LIMIT = int(sys.argv[i + 1])

CLAUDE = os.path.expanduser("~/.local/bin/claude")
MODEL = "claude-haiku-4-5"
BATCH = 10
INBOX_NAMES = ("_收件箱", "待分类")


def is_inbox(name):
    return any(k in name for k in INBOX_NAMES)


def call_haiku(batch, leaves):
    opts = "\n".join(f"  - {p}" for p in leaves)
    lines = []
    for j, b in enumerate(batch):
        ab = (b["abstract"] or "")[:300].replace("\n", " ")
        lines.append(f'{j+1}. 标题:{b["title"]}\n   年份:{b["year"]} 出处:{b["venue"] or "预印本"}\n   摘要:{ab}')
    prompt = f"""你是自动驾驶文献分类助手。把每篇论文归到下面**已有的**分类叶子之一(必须原样照抄叶子全路径,不要自创):

{opts}

分类原则:
- 通用视觉/语言/多模态/生成模型等**非驾驶专属的基础模型** → 0 公用基石 下对应子类
- 城区/结构化道路场景:按模块化(感知/建图/预测/占用/规划)或端到端(模块化E2E/VLM-VLA/RL后训练)归
- 越野/非结构化/野外/地形/可通行性 → 2 非结构化越野 下对应子类
- 数据集与基准 → 3 数据集与基准 下(城区/越野各自的子类)

对每篇输出:
  leaf = 选中的叶子**全路径**(照抄上面列表里的字符串)
  confidence = high / medium / low(只有你很确定该归这里才给 high)

只输出 JSON 数组 [{{"i":序号,"leaf":"...","confidence":"..."}}],不要多余文字。

论文:
""" + "\n".join(lines)
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
    z = Zot()
    tree = z.collection_tree()
    inbox_keys = {k for k, v in tree.items() if is_inbox(v["name"])}
    if not inbox_keys:
        print("找不到收件箱分类"); return
    # 可选叶子 = 树里除收件箱外的所有分类(用全路径,便于 Haiku 精确指认)
    path2key = {v["path"]: k for k, v in tree.items() if k not in inbox_keys}
    leaves = sorted(path2key)

    # 收件箱里的条目
    items = []
    for ck in inbox_keys:
        for it in z.items_in_collection(ck):
            d = it["data"]
            if d.get("itemType") in ("attachment", "note"): continue
            items.append({"key": it["key"], "version": it["version"], "data": d,
                          "title": d.get("title", ""), "year": (d.get("date", "") or "")[:4],
                          "venue": d.get("proceedingsTitle") or d.get("publicationTitle") or "",
                          "abstract": d.get("abstractNote", "")})
    if LIMIT: items = items[:LIMIT]
    print(f"收件箱待分类 {len(items)} 篇 | 可选叶子 {len(leaves)} 个")
    if not items:
        print("收件箱是空的,无需分类"); return

    results = {}
    for i in range(0, len(items), BATCH):
        b = items[i:i + BATCH]
        arr = call_haiku(b, leaves)
        if not arr:
            print(f"  批 {i//BATCH+1} 失败,跳过"); continue
        for o in arr:
            idx = o.get("i", 0) - 1
            if 0 <= idx < len(b):
                leaf = o.get("leaf", "")
                if leaf in path2key:
                    results[b[idx]["key"]] = {"leaf": leaf, "conf": o.get("confidence", "low")}
                else:
                    print(f"  ⚠ 叶子不存在,跳过:{leaf!r}")
        print(f"  批 {i//BATCH+1}/{(len(items)+BATCH-1)//BATCH} 完成")
        time.sleep(1)

    hi = {k: v for k, v in results.items() if v["conf"] == "high"}
    lo = {k: v for k, v in results.items() if v["conf"] != "high"}
    print(f"\n判定 {len(results)}/{len(items)} | 高置信自动归档 {len(hi)} | 待确认 {len(lo)}")
    print("目标分布:", dict(Counter(v["leaf"].split(" / ")[-1] for v in results.values())))
    by_key = {x["key"]: x for x in items}
    for k, v in list(results.items())[:12]:
        print(f'  [{v["conf"]:6}] {by_key[k]["title"][:44]} → {v["leaf"].split(" / ")[-1]}')
    if not APPLY:
        print("\n(加 --apply 执行:高置信归档、其余打建议标签)"); return

    ok_move, ok_tag = 0, 0
    for k, v in results.items():
        it = by_key[k]; cur = dict(it["data"])
        target = path2key[v["leaf"]]
        if v["conf"] == "high":
            # 移出收件箱 → 放进目标叶子
            cols = [c for c in cur.get("collections", []) if c not in inbox_keys]
            if target not in cols: cols.append(target)
            cur["collections"] = cols
            cur["tags"] = [t for t in cur.get("tags", []) if not t.get("tag", "").startswith("建议分类:")]
            if z.put_item(k, cur, it["version"]): ok_move += 1
        else:
            tags = [t for t in cur.get("tags", []) if not t.get("tag", "").startswith("建议分类:")]
            tags.append({"tag": "建议分类:" + v["leaf"].split(" / ")[-1]})
            cur["tags"] = tags
            if z.put_item(k, cur, it["version"]): ok_tag += 1
        time.sleep(0.32)
    print(f"自动归档 {ok_move} | 打建议标签 {ok_tag}(仍留收件箱待你确认)")


if __name__ == "__main__":
    main()
