#!/usr/bin/env python3
"""litpipe · 补齐全局被引数(cc)

cc 原本只在抓参考列表时顺带拿到,覆盖率只有 ~37%。S2 的批量接口本来就返回
citationCount,单独跑一趟 50 篇/批,1205 篇只要约 25 个请求。

用法: python fill_cc.py [--apply]
"""
import json, sys, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import load_state, save_state
from build_edges import S2, HDR, s2_id

APPLY = "--apply" in sys.argv
FIELDS = "title,citationCount,externalIds"


def batch(ids, tries=10):
    body = json.dumps({"ids": ids}).encode()
    hdr = {**HDR, "Content-Type": "application/json"}
    for _ in range(tries):
        try:
            req = urllib.request.Request(f"{S2}/paper/batch?fields={FIELDS}",
                                         headers=hdr, data=body)
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(1.2); continue      # 429 快速重试,别退避
            if e.code in (400, 404):
                return None
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return None


def main():
    C = load_state("lib_corpus.json", {})
    cc = load_state("cc.json", {})
    have = sum(1 for k in C if cc.get(k))
    print(f"语料 {len(C)} 篇,已有 cc {have} 篇({have * 100 // len(C)}%)")

    idmap = {}
    for k, v in C.items():
        if cc.get(k):
            continue
        sid = s2_id(v)
        if sid:
            idmap.setdefault(sid, k)
    ids = list(idmap)
    noid = sum(1 for k, v in C.items() if not cc.get(k) and not s2_id(v))
    print(f"待补 {len(C) - have} 篇:可批量定位 {len(ids)},无 ID 无法定位 {noid}")
    if not APPLY:
        print("\n(加 --apply 执行)")
        return

    got = 0
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        recs = batch(chunk)
        if not recs:
            print(f"  批 {i // 50 + 1} 失败,跳过", flush=True); continue
        for sid, rec in zip(chunk, recs):
            if rec and rec.get("citationCount") is not None:
                cc[idmap[sid]] = rec["citationCount"]; got += 1
        save_state("cc.json", cc)
        print(f"  {min(i + 50, len(ids))}/{len(ids)} 已补 {got}", flush=True)
        time.sleep(1.2)

    # 回写进语料,layout 直接读
    for k, v in C.items():
        v["cc"] = cc.get(k, v.get("cc", 0))
    save_state("lib_corpus.json", C)
    now = sum(1 for v in C.values() if v.get("cc"))
    print(f"\ncc 覆盖 {have} → {now}/{len(C)}({now * 100 // len(C)}%)")


if __name__ == "__main__":
    main()
