#!/usr/bin/env python3
"""litpipe · 把分类方案落到 Zotero

输入 state/found_plan.json 或 state/offroad_plan.json(工作流产出),
建子分类 → 把论文从旧叶移到新叶 → 迁出的挪到目标桶。

**多挂靠保护**:只从「本次要重组的那几个旧叶」里摘掉条目,不动它在别处的挂靠。
基石那批很多同时挂在自驾树下,全摘会让自驾综述页凭空少掉几十篇。

**破坏性动作隔离**:标了「合并去重:删除本条」的只报告、不执行,交人工确认。

用法:
  python apply_plan.py found            # 干运行
  python apply_plan.py found --apply
  python apply_plan.py offroad --apply
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, load_state

WHICH = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
APPLY = "--apply" in sys.argv

CFG = {
    # 方案文件, 新叶建在哪个分类下, 需要清空的旧叶名(只从这些里摘)
    "found": {
        "plan": "found_plan.json",
        "parent_key": "V55TE2QG",           # 顶层「0 公用基石」
        "old_leaf_names": {"0.1 视觉与几何骨干", "0.2 语言模型与推理", "0.3 多模态基座",
                           "0.4 生成模型", "0.5 学习范式与数学工具"},
    },
    "offroad": {
        "plan": "offroad_plan.json",
        "parent_name": "2.1 模块化",         # 建在这个叶子下面,变成它的子分类
        "old_leaf_names": {"2.1 模块化"},
    },
}


def api_get(z, path):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{z.base}{path}", headers=z.hdr), timeout=60).read())


def main():
    if WHICH not in CFG:
        print(__doc__); return
    cfg = CFG[WHICH]
    plan = load_state(cfg["plan"], {})
    if not plan:
        raise SystemExit(f"找不到 state/{cfg['plan']}")

    z = Zot()
    tree = z.collection_tree(ttl=0)
    name2key = {}
    for k, v in tree.items():
        name2key.setdefault(v["name"], k)

    parent = cfg.get("parent_key") or name2key.get(cfg.get("parent_name"))
    if not parent:
        raise SystemExit(f"找不到父分类 {cfg.get('parent_name')}")
    old_keys = {k for k, v in tree.items() if v["name"] in cfg["old_leaf_names"]}
    # 顶层基石不在自驾树 tree 里,单独补
    if WHICH == "found":
        allcol = api_get(z, "/collections?limit=100")
        while True:
            for c in allcol:
                if c["data"].get("parentCollection") == parent:
                    if c["data"]["name"] in cfg["old_leaf_names"]:
                        old_keys.add(c["key"])
                    name2key.setdefault(c["data"]["name"], c["key"])
            if len(allcol) < 100:
                break
            allcol = api_get(z, f"/collections?limit=100&start={len(allcol)}")
    print(f"父分类 {parent} | 待清空的旧叶 {len(old_keys)} 个")

    leaves = plan["leaves"]
    A = plan["assignments"]
    dup = [x for x in A if str(x.get("evict_to", "")).startswith("合并去重")]
    ev = [x for x in A if x["leaf"] == "EVICT" and x not in dup]
    mv = [x for x in A if x["leaf"] != "EVICT"]
    print(f"方案:{len(leaves)} 个新叶 | 归类 {len(mv)} 篇 | 迁出 {len(ev)} 篇 | 疑似重复 {len(dup)} 篇(只报告)")

    print("\n新叶及篇数:")
    cnt = Counter(x["leaf"] for x in mv)
    for l in leaves:
        print(f"  {l['code']:10} {l['name']:38} {cnt.get(l['code'], 0):3} 篇")
    miss = set(cnt) - {l["code"] for l in leaves}
    if miss:
        print("  ⚠ 归类里出现方案未定义的叶:", miss)

    if dup:
        print("\n⚠ 疑似重复条目(**不自动删除**,请在 Zotero 里人工确认后处理):")
        for x in dup:
            print(f"   {x['key']}  {x.get('title', '')[:62]}")
    if ev:
        print("\n迁出本类:")
        for x in ev:
            print(f"   → {x.get('evict_to', '?')[:28]:28} {x.get('title', '')[:46]}")

    if not APPLY:
        print("\n(加 --apply 执行)")
        return

    # ---------- 建分类 ----------
    code2key = {}
    for l in leaves:
        full = f"{l['code']} {l['name']}" if not l["name"].startswith(l["code"]) else l["name"]
        if full in name2key:
            code2key[l["code"]] = name2key[full]
            print(f"  已存在 {full}")
            continue
        r = z.s.post(f"{z.base}/collections",
                     json=[{"name": full, "parentCollection": parent}], timeout=60)
        res = r.json()
        succ = res.get("successful", {})
        if succ:
            key = list(succ.values())[0]["key"]
            code2key[l["code"]] = key
            print(f"  ✓ 建 {full}  {key}")
        else:
            print(f"  ✗ 建失败 {full}: {json.dumps(res.get('failed', {}), ensure_ascii=False)[:160]}")
        time.sleep(0.3)

    # ---------- 移动条目 ----------
    ok = fail = 0
    for x in mv:
        tgt = code2key.get(x["leaf"])
        if not tgt:
            fail += 1; continue
        try:
            it = api_get(z, f"/items/{x['key']}")
        except Exception as e:
            print(f"  ✗ 取条目失败 {x['key']} {e}"); fail += 1; continue
        d = dict(it["data"])
        cols = [c for c in d.get("collections", []) if c not in old_keys]  # 只摘旧叶
        if tgt not in cols:
            cols.append(tgt)
        d["collections"] = cols
        if z.put_item(x["key"], d, it["version"]):
            ok += 1
        else:
            fail += 1
        if ok % 20 == 0:
            print(f"  已移动 {ok}/{len(mv)}", flush=True)
        time.sleep(0.28)
    print(f"\n归类完成 {ok}/{len(mv)}(失败 {fail})")
    print(f"迁出的 {len(ev)} 篇与疑似重复 {len(dup)} 篇未自动处理,见上方清单")


if __name__ == "__main__":
    main()
