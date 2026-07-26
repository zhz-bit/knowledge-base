#!/usr/bin/env python3
"""litpipe ① maintain · 确定性元数据校正(不联网抓取、不用 LLM)

对综述树里的会议/期刊条目:
  · 会议名规范化 —— 统一成规范全称(去年份/去"(CVPR)"后缀/去 LNCS 丛书前缀),
    否则 easyScholar「期刊标签」按名字匹配不上,认不出分区/CCF。
  · 打官方 CCF-A/B/C 标签 —— 用内置 ccf_db.json(575 条,抽自 ccfinfo 插件)离线查表,
    比插件那套"标题→在线 DBLP"可靠。非 CCF 会议(ICLR/CoRL/RSS/WACV/RA-L)不打是正确的。

这一步的逻辑将来可原样移植进 Zotero 插件(加论文时即时执行)。

用法: python maintain.py [--apply]
"""
import json, re, sys, time
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib_corpus import _api_get as api
from zotero_io import Zot

APPLY = "--apply" in sys.argv
SCOPE = "all"                      # 默认全库;--scope e2e 只跑自驾树
for _i, _a in enumerate(sys.argv):
    if _a == "--scope":
        SCOPE = sys.argv[_i + 1]
CCF = json.load(open(HERE / "ccf_db.json", encoding="utf-8"))

CANON = {
 "CVPR": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
 "ICCV": "IEEE/CVF International Conference on Computer Vision",
 "ECCV": "European Conference on Computer Vision",
 "NeurIPS": "Advances in Neural Information Processing Systems",
 "ICLR": "International Conference on Learning Representations",
 "ICML": "International Conference on Machine Learning",
 "AAAI": "Proceedings of the AAAI Conference on Artificial Intelligence",
 "IJCAI": "International Joint Conference on Artificial Intelligence",
 "ICRA": "IEEE International Conference on Robotics and Automation",
 "IROS": "IEEE/RSJ International Conference on Intelligent Robots and Systems",
 "CoRL": "Conference on Robot Learning", "RSS": "Robotics: Science and Systems",
 "WACV": "IEEE/CVF Winter Conference on Applications of Computer Vision",
 "ACMMM": "ACM International Conference on Multimedia",
 "TPAMI": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
 "RA-L": "IEEE Robotics and Automation Letters", "T-RO": "IEEE Transactions on Robotics",
 "T-ITS": "IEEE Transactions on Intelligent Transportation Systems",
 "T-IV": "IEEE Transactions on Intelligent Vehicles",
 "IJCV": "International Journal of Computer Vision",
 "TMLR": "Transactions on Machine Learning Research", "Nature": "Nature",
}
DETECT = [("winter conference on applications","WACV"),("wacv","WACV"),
 ("pattern analysis and machine intel","TPAMI"),("robotics and automation letters","RA-L"),
 ("transactions on robotics","T-RO"),("transactions on intelligent transportation","T-ITS"),
 ("transactions on intelligent vehicles","T-IV"),("international journal of computer vision","IJCV"),
 ("machine learning research","TMLR"),("pattern recognition","CVPR"),("cvpr","CVPR"),
 ("eccv","ECCV"),("european conference on computer vision","ECCV"),
 ("international conference on computer vision","ICCV"),("iccv","ICCV"),
 ("neural information processing","NeurIPS"),("neurips","NeurIPS"),("nips","NeurIPS"),
 ("learning representations","ICLR"),("iclr","ICLR"),("robot learning","CoRL"),("corl","CoRL"),
 ("international conference on robotics and automation","ICRA"),("icra","ICRA"),
 ("intelligent robots and systems","IROS"),("iros","IROS"),("aaai","AAAI"),
 ("international conference on machine learning","ICML"),("robotics: science and systems","RSS"),
 ("robotics science and systems","RSS"),("multimedia","ACMMM"),("nature","Nature")]
ALIAS = {"T-ITS": "TITS", "T-RO": "TR", "ACMMM": "ACM MM"}
VF = {"conferencePaper": "proceedingsTitle", "journalArticle": "publicationTitle"}


def detect(venue):
    v = (venue or "").lower()
    if "workshop" in v: return None          # 工作坊不强改(通常无 CCF)
    for kw, ab in DETECT:
        if kw in v: return ab
    return None


_CCF_UP = None


def rank_of(ab):
    """CCF 等级。库键名保留原大小写(NeurIPS 而非 NEURIPS),故做大小写不敏感回退。"""
    global _CCF_UP
    return CCF.get(ALIAS.get(ab, ab), {}).get("rank") if ab else None


def main():
    z = Zot()
    if SCOPE == "all":
        # 扫**全库**:只扫自驾树会漏掉 500+ 篇有 venue 的论文(T-ITS/RA-L/AAAI/CVPR…),
        # 它们的 CCF 等级本来就查得到,没理由不打
        print("扫描全库 ...")
        tree = {}
        start = 0
        while True:
            d = api(z, f"{z.base}/items/top?limit=100&start={start}")
            if not d:
                break
            for x in d:
                if x["data"].get("itemType") not in ("attachment", "note"):
                    tree[x["key"]] = {"data": x["data"], "version": x["version"]}
            start += 100
            if len(d) < 100:
                break
    else:
        print("扫描综述树 ...")
        tree = z.scan_tree()
    todo, stat = [], Counter()
    for k, v in tree.items():
        d = v["data"]
        ty = d.get("itemType")
        # preprint 没有 venue 字段,但 fill_venue.py 把真实出处写进了 extra 的
        # `Venue:` 行 —— 不放它进来的话那 142 篇永远打不上 CCF(踩过)
        if ty not in VF and not (ty == "preprint"
                                 and re.search(r"^Venue:", d.get("extra", "") or "", re.M)):
            continue
        cur = dict(d); changed = False
        venue = cur.get(VF[ty], "") if ty in VF else ""
        ab = detect(venue)
        if not ab:
            # 预印本的 venue 字段是空的:读 fill_venue.py 从 arXiv journal_ref/comment
            # 挖到并写进 extra 的 `Venue: CVPR 2024` 行(存的已经是缩写,不必再 detect)
            m = re.search(r"^Venue:\s*([A-Za-z][A-Za-z0-9-]*)", cur.get("extra", "") or "", re.M)
            if m:
                ab = m.group(1)
        if ty in VF and ab and ab in CANON and venue.strip() != CANON[ab]:
            cur[VF[ty]] = CANON[ab]
            if ty == "conferencePaper": cur["conferenceName"] = CANON[ab]
            changed = True; stat["规范venue"] += 1
        rk = rank_of(ab)
        if rk:
            stat[f"CCF-{rk}"] += 1
            if not any(t.get("tag") == f"CCF-{rk}" for t in cur.get("tags", [])):
                cur["tags"] = [t for t in cur.get("tags", []) if not re.match(r"^CCF-[ABC]$", t.get("tag", ""))] \
                              + [{"tag": f"CCF-{rk}"}]
                changed = True; stat["打CCF标签"] += 1
        if changed: todo.append((k, cur, v["version"]))
    print(f"范围 {SCOPE} {len(tree)} 条 | 需改 {len(todo)} | {dict(stat)}")
    if not APPLY:
        print("(加 --apply 写回)"); return
    ok = 0
    for k, cur, ver in todo:
        if z.put_item(k, cur, ver): ok += 1
        time.sleep(0.32)
    print(f"写回 {ok}/{len(todo)}")


if __name__ == "__main__":
    main()
