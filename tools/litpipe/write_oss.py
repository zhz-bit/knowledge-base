#!/usr/bin/env python3
"""litpipe · 把 state/oss_all.json 的开源结论写回 Zotero

写:标签 `开源` / `未见开源`,以及 extra 里的 `Code: <url>` 行。
插件的开源列读的就是这两处(它自己不联网)。

用法: python write_oss.py [--apply]
"""
import json, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, load_state
from lib_corpus import _api_get as api

APPLY = "--apply" in sys.argv
rows = json.load(open(HERE / "state" / "oss_all.json", encoding="utf-8"))
C = load_state("lib_corpus.json", {})
SCOPE = "all"
for i, a in enumerate(sys.argv):
    if a == "--scope":
        SCOPE = sys.argv[i + 1]
pool = ({k for k, v in C.items()
         if v["band"] == "5 自动驾驶综述"
         and ("端到端" in v["sub"] or v["sub"] in ("VLM-VLA", "模块化E2E", "RL后训练"))}
        if SCOPE == "e2e" else set(C))
oss = {r["key"]: r for r in rows}
print(f"范围 {SCOPE} {len(pool)} 篇:开源 {len(oss)}、未见 {len(pool) - len(oss)}")
if not APPLY:
    print("(加 --apply 写回)"); raise SystemExit

z = Zot()
# 批量取,避免逐条被 SSL 打断
data = {}
keys = list(pool)
for i in range(0, len(keys), 50):
    for x in api(z, f"{z.base}/items?itemKey={','.join(keys[i:i+50])}&limit=50"):
        data[x["key"]] = x
    time.sleep(0.3)
print(f"取回 {len(data)}/{len(keys)}")

a = b = 0
for k in keys:
    it = data.get(k)
    if not it:
        continue
    d = dict(it["data"])
    tags = [t for t in d.get("tags", []) if t.get("tag") not in ("开源", "未见开源", "开源:疑似")]
    ex = re.sub(r"^Code:.*$\n?", "", d.get("extra", "") or "", flags=re.M)
    if k in oss:
        o = oss[k]
        tags.append({"tag": "开源"})
        # star 与最后提交日一并写进 extra —— 插件列与页面都从这里读,不必联网
        line = f"Code: {o['repo']}"
        if isinstance(o.get("stars"), int) and o["stars"] >= 0:
            line += f" | ★{o['stars']}"
        if o.get("pushed"):
            line += f" | 更新 {o['pushed']}"
        if o.get("archived"):
            line += " | 已归档"
        d["extra"] = (line + "\n" + ex).strip()
        a += 1
    else:
        tags.append({"tag": "未见开源"})
        d["extra"] = ex.strip()
        b += 1
    d["tags"] = tags
    if not z.put_item(k, d, it["version"]):
        print(f"  ✗ 写入失败 {k}")
    time.sleep(0.28)
    if (a + b) % 40 == 0:
        print(f"  {a+b}/{len(keys)}", flush=True)
print(f"\n标「开源」{a} | 标「未见开源」{b}")
