#!/usr/bin/env python3
"""litpipe · 给预印本补真实发表出处(补完就能算 CCF)

为什么需要:库里 488 篇条目是 preprint、venue 为空,所以 CCF 查不到,
ZoteroStyle 的「期刊标签」列也大面积空白 —— 但其中很多**其实已被会议接收**,
作者把这个信息写在了 arXiv 的 journal_ref 或 comment 里。

两个来源,都是作者自己填的,可信:
  ① `<arxiv:journal_ref>` —— 作者亲标的发表信息,最权威
  ② `<arxiv:comment>` —— "Accepted to CVPR 2024" 这类,占多数

**必须排除的**(这些不是主会论文,不能算 CCF):
  workshop / challenge / competition / technical report / demo / extended abstract
"Accepted at CVPR 2021 Workshop on Autonomous Driving" 是 workshop,给它标 CCF-A 就错了。

写回 Zotero:conferencePaper 的 proceedingsTitle,或在 extra 加 `Venue: <会议> <年>`
(preprint 类型没有 proceedingsTitle 字段,写 extra 由 maintain 与插件读)。

用法:
  python fill_venue.py            # 干运行
  python fill_venue.py --apply
"""
import json, re, sys, time, urllib.request
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, load_state
from lib_corpus import _api_get as api
from maintain import detect as detect_full   # 全称 → 缩写(复用 maintain 的 DETECT 表)

APPLY = "--apply" in sys.argv
UA = {"User-Agent": "litpipe/1.0"}

# **期刊要先匹配**:"Published in RA-L with ICRA presentation option" 是一篇
# RA-L 期刊论文(ICRA 只是去做了报告),按会议表顺序会误判成 ICRA。
JOURNALS = ["TPAMI", "IJCV", "TITS", "T-ITS", "TIV", "T-IV", "RA-L", "RAL",
            "T-RO", "TRO", "TIP", "TMLR", "JMLR", "TNNLS"]
CONFS = ["CVPR", "ICCV", "ECCV", "NeurIPS", "NIPS", "ICLR", "ICML", "AAAI", "IJCAI",
         "ICRA", "IROS", "CoRL", "RSS", "WACV", "ACL", "EMNLP", "NAACL", "SIGGRAPH",
         "BMVC", "ACCV", "3DV", "MICCAI", "KDD", "WWW", "CIKM", "AISTATS", "COLT"]
VENUES = JOURNALS + CONFS
J_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(map(re.escape, JOURNALS)) + r")(?![A-Za-z])", re.I)
C_RE = re.compile(r"\b(" + "|".join(CONFS) + r")\b", re.I)
V_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(map(re.escape, VENUES)) + r")(?![A-Za-z])", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# 缩写 → CCF 官方目录里的键名。目录里**没有** RA-L / T-IV / CoRL / TMLR ——
# 这些出处本来就不在 CCF 推荐列表,查不到等级是事实而非漏标。
ALIAS = {"T-ITS": "TITS", "T-RO": "TR", "TRO": "TR", "T-IV": "TIV", "RA-L": "RAL"}
# 这些说明不是主会论文
EXCLUDE = re.compile(r"workshop|challenge|competition|technical\s+report|demo\b|"
                     r"extended\s+abstract|poster|tutorial|preprint\s+only", re.I)
# 只有这些句式才算"已被接收"
ACCEPT = re.compile(r"accept|published|to\s+appear|camera[- ]ready|"
                    r"^\s*(?:" + "|".join(VENUES) + r")\s*'?\d{2,4}", re.I)


def arxiv_batch(ids):
    out = {}
    for i in range(0, len(ids), 25):
        chunk = [x for x in ids[i:i + 25] if x]
        if not chunk:
            continue
        try:
            xml = urllib.request.urlopen(urllib.request.Request(
                f"http://export.arxiv.org/api/query?id_list={','.join(chunk)}&max_results=40",
                headers=UA), timeout=60).read().decode("utf-8", "replace")
        except Exception:
            time.sleep(5); continue
        for e in xml.split("<entry>")[1:]:
            g = lambda p: (re.search(p, e, re.S).group(1).strip()
                           if re.search(p, e, re.S) else "")
            ax = re.sub(r"v\d+$", "", g(r"<id>http://arxiv\.org/abs/([^<]+)</id>"))
            out[ax] = {
                "jr": " ".join(g(r"<arxiv:journal_ref[^>]*>(.*?)</arxiv:journal_ref>").split()),
                "cm": " ".join(g(r"<arxiv:comment[^>]*>(.*?)</arxiv:comment>").split()),
            }
        print(f"  arXiv {min(i+25, len(ids))}/{len(ids)}", flush=True)
        time.sleep(3.2)
    return out


def pick(jr, cm):
    """返回 (会议缩写, 年份, 来源, 原文) 或 None。"""
    for src, txt in (("journal_ref", jr), ("comment", cm)):
        if not txt:
            continue
        if EXCLUDE.search(txt):
            continue                       # workshop/challenge 等,不算主会
        m = J_RE.search(txt) or C_RE.search(txt)     # 期刊优先
        if not m:
            # 缩写没命中,试全称("Accepted to IEEE Transactions on Robotics")
            full_ab = detect_full(txt)
            if not full_ab:
                continue
            if src == "comment" and not ACCEPT.search(txt):
                continue
            y0 = YEAR_RE.search(txt)
            return (ALIAS.get(full_ab.upper(), full_ab.upper()),
                    (y0.group(0) if y0 else ""), src + "·全称", txt[:70])
        # comment 里只是"提到"会议名不算被接收;但短文本里的「出处 年份」
        # (如 "IEEE T-ITS 2023"、"CVPR 2025")是常见的陈述式,认。
        if src == "comment" and not ACCEPT.search(txt) \
           and not (len(txt) < 46 and YEAR_RE.search(txt)):
            continue
        y = YEAR_RE.search(txt)
        ab = m.group(1).upper()
        return ALIAS.get(ab, ab), (y.group(0) if y else ""), src, txt[:70]
    return None


def main():
    z = Zot()
    C = load_state("lib_corpus.json", {})
    pool = [(k, v) for k, v in C.items() if not v.get("venue") and v.get("arxiv")]
    print(f"无出处但有 arXiv 号的 {len(pool)} 篇,查 journal_ref / comment ...\n", flush=True)

    meta = arxiv_batch([v["arxiv"] for _, v in pool])
    hits, excluded = [], 0
    for k, v in pool:
        m = meta.get(v["arxiv"])
        if not m:
            continue
        if (m["jr"] or m["cm"]) and EXCLUDE.search(m["jr"] + " " + m["cm"]):
            excluded += 1
        got = pick(m["jr"], m["cm"])
        if got:
            ab, yr, src, raw = got
            hits.append({"key": k, "title": v["title"], "ab": ab, "year": yr,
                         "src": src, "raw": raw})

    print(f"\n可补出处 {len(hits)}/{len(pool)} 篇 | 因 workshop/challenge 等排除 {excluded} 篇")
    print("出处分布:", dict(Counter(h["ab"] for h in hits).most_common(12)))
    print(f"\n{'来源':<12} {'出处':<10} 论文")
    for h in hits[:30]:
        print(f"{h['src']:<12} {h['ab']+' '+h['year']:<10} {h['title'][:52]}")
        print(f"{'':12} 依据:{h['raw']}")
    json.dump(hits, open(HERE / "state" / "venue_fill.json", "w"),
              ensure_ascii=False, indent=1)
    if not APPLY:
        print("\n(加 --apply 写回 Zotero)")
        return

    ok = 0
    for h in hits:
        it = api(z, f"{z.base}/items/{h['key']}")
        d = dict(it["data"])
        line = f"Venue: {h['ab']}{' ' + h['year'] if h['year'] else ''}"
        ex = re.sub(r"^Venue:.*$\n?", "", d.get("extra", "") or "", flags=re.M)
        d["extra"] = (line + "\n" + ex).strip()
        if z.put_item(h["key"], d, it["version"]):
            ok += 1
        if ok % 25 == 0:
            print(f"  写回 {ok}/{len(hits)}", flush=True)
        time.sleep(0.3)
    print(f"\n已写回 {ok}/{len(hits)} 篇的 extra(Venue: 行)")
    print("接着跑 maintain.py --apply 就能据此打 CCF 标签")


if __name__ == "__main__":
    main()
