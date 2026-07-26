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
from datetime import datetime
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, ROOT_COLLECTION, STATE
from lib_corpus import all_collections

APPLY = "--apply" in sys.argv
LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit": LIMIT = int(sys.argv[i + 1])

CLAUDE = os.path.expanduser("~/.local/bin/claude")
MODEL = "claude-haiku-4-5"
BATCH = 10
INBOX_NAMES = ("_收件箱", "待分类")
# 事务性目录不收文献
SKIP_PATHS = ("7 学校事务",)


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

分类原则(库里有 8 个顶层桶,按论文的**主要贡献**归,不按它顺带提到什么):
- 跨领域通用的骨干/语言模型/多模态基座/生成模型/学习范式 → 0 公用基石
- 深度学习方法本体(架构、图网络、强化学习) → 1 深度学习
- 通用计算机视觉(识别分割、三维渲染、低层视觉、域适应) → 2 计算机视觉
- 自然语言处理本体 → 3 自然语言处理
- 交通流量/轨迹/时空数据预测 → 4 时空序列预测
- 自动驾驶:城区按模块化(感知/建图/预测/占用/规划)或端到端(模块化E2E/VLM-VLA/RL后训练);
  越野/非结构化/地形/可通行性 → 2 非结构化越野 下的细分叶
- 数据集与基准 → 6 数据集,或 5 自动驾驶综述 / 3 数据集与基准
- 神经科学、脑网络、类脑智能 → 8 神经科学与类脑智能

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
    # 扫**全库**分类,不只自驾树 —— 收件箱已移到库顶层,只扫自驾树会找不到它;
    # 而且新论文可能属于任何桶(神经科学、时空预测…),候选叶不能限定在自驾树内。
    cols = all_collections(z)
    # 注意排除事务目录:「7 学校事务 / 9 待分类/杂项」名字里也含「待分类」,
    # 不排掉会把里面 15 篇学校材料一起拖进来自动归类
    inbox_keys = {k for k, v in cols.items()
                  if is_inbox(v["name"]) and not any(x in v["path"] for x in SKIP_PATHS)}
    if not inbox_keys:
        print("找不到收件箱分类(应有名字含「_收件箱」或「待分类」的分类)"); return

    # 候选只给**叶子**分类(没有子分类的):有子分类的是中间层,论文不该挂在那儿。
    parents = {v["parent"] for v in cols.values() if v["parent"]}
    path2key = {v["path"]: k for k, v in cols.items()
                if k not in parents and k not in inbox_keys
                and not any(x in v["path"] for x in SKIP_PATHS)}
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
    print(f"\n判定 {len(results)}/{len(items)} | 高置信将自动归档 {len(hi)} | 待确认 {len(lo)}")
    print("目标分布:", dict(Counter(v["leaf"].split(" / ")[-1] for v in results.values())))
    by_key = {x["key"]: x for x in items}
    if not APPLY:
        # 干运行:逐篇列出**打算**放哪(全部列,不截断;带完整路径,叶名会重复)
        print("\n打算这样归档:")
        for k, v in sorted(results.items(), key=lambda kv: kv[1]["conf"] != "high"):
            print(f'  [{v["conf"]:6}] {by_key[k]["title"][:50]}')
            print(f'            → {v["leaf"]}')
        print("\n(加 --apply 执行:高置信归档、其余打建议标签)"); return

    # ── 执行,并逐篇记录**实际结果** ──
    # 之前这里只打一行汇总数字,事后无从追溯"某篇被放到哪了";而干运行那份清单
    # 是"打算",put_item 失败时日志照样显示了目标叶,看着像成功。
    LOG = STATE / "classify_log.jsonl"
    ok_move, ok_tag, failed = 0, 0, []
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"\n{'结果':<10} {'置信':<8} 论文 → 目标分类")
    print("─" * 78)
    with open(LOG, "a", encoding="utf-8") as lg:
        for k, v in sorted(results.items(), key=lambda kv: kv[1]["conf"] != "high"):
            it = by_key[k]; cur = dict(it["data"])
            target = path2key[v["leaf"]]
            title = it["title"]
            if v["conf"] == "high":
                cols = [c for c in cur.get("collections", []) if c not in inbox_keys]
                if target not in cols: cols.append(target)
                cur["collections"] = cols
                cur["tags"] = [t for t in cur.get("tags", [])
                               if not t.get("tag", "").startswith("建议分类:")]
                done = z.put_item(k, cur, it["version"])
                act = "已归档" if done else "移动失败"
                ok_move += bool(done)
            else:
                tags = [t for t in cur.get("tags", [])
                        if not t.get("tag", "").startswith("建议分类:")]
                tags.append({"tag": "建议分类:" + v["leaf"].split(" / ")[-1]})
                cur["tags"] = tags
                done = z.put_item(k, cur, it["version"])
                act = "留箱+建议标签" if done else "打标签失败"
                ok_tag += bool(done)
            if not done:
                failed.append((k, title, v["leaf"]))
            mark = "✓" if done else "✗"
            print(f"{mark} {act:<9} {v['conf']:<8} {title[:44]}")
            print(f"{'':11} {'':8} → {v['leaf']}")
            # 持久审计:run.log 会被下一趟覆盖,这份 jsonl 是累加的
            lg.write(json.dumps({"at": stamp, "key": k, "title": title,
                                 "leaf": v["leaf"], "conf": v["conf"],
                                 "action": act, "ok": bool(done)}, ensure_ascii=False) + "\n")
            time.sleep(0.32)
    print("─" * 78)
    print(f"自动归档 {ok_move} | 留箱打建议标签 {ok_tag}(待你确认)"
          + (f" | **失败 {len(failed)}**" if failed else ""))
    for k, t, leaf in failed:
        print(f"  ✗ {k} {t[:46]} → {leaf}")
    print(f"逐篇记录已追加到 {LOG.relative_to(HERE)}(可 tail 查历史)")


if __name__ == "__main__":
    main()
