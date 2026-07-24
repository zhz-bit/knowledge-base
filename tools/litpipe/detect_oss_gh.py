#!/usr/bin/env python3
"""litpipe · 开源检测第三级:GitHub 搜索 + **官方性验证**

前两级(摘要链接 / arXiv comment)只覆盖到一部分。这一级用 gh CLI 搜仓库,
但**同名仓库不等于官方实现** —— 一个叫 UniAD 的随手复现不能算论文开源。
所以每个候选都要过验证:

  仓库的 description / README / homepage 里出现下列任一,才认:
    · 论文的 arXiv 号
    · 论文标题的主干(冒号前那截,归一化后)
    · 标题里 ≥60% 的实词

命中且 star 数最高的那个胜出。验证不过的记为「疑似」,不写 Zotero。

读 state/oss.json(前两级结果)与 state/lib_corpus.json,产出 state/oss_gh.json。

用法:
  python detect_oss_gh.py            # 干运行
  python detect_oss_gh.py --limit 40 # 只跑前 N 篇(按库内被引降序)
"""
import json, re, subprocess, sys, time, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import load_state

LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit":
        LIMIT = int(sys.argv[i + 1])

STOP = {"the", "a", "an", "of", "for", "with", "via", "and", "in", "on", "to",
        "from", "by", "using", "towards", "toward", "is", "are", "we", "our",
        "learning", "model", "models", "driving", "autonomous", "end", "end-to-end"}


def norm(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def words(t):
    return [w for w in norm(t).split() if len(w) > 2 and w not in STOP]


def gh(args, tries=3):
    for i in range(tries):
        r = subprocess.run(["gh", "api"] + args, capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout or "{}")
            except Exception:
                return {}
        if "rate limit" in (r.stderr or "").lower():
            time.sleep(20); continue
        return None
    return None


def model_name(title):
    """取论文的模型名:冒号前那截;没有冒号就用前 4 个实词。"""
    head = title.split(":")[0].strip()
    if 2 <= len(head) <= 30 and len(head.split()) <= 4:
        return head
    return " ".join(words(title)[:4])


def verify(repo, title, ax):
    """仓库是否是这篇论文的官方实现。返回 (是否通过, 理由)。"""
    blob = " ".join(str(repo.get(f) or "") for f in ("description", "homepage", "full_name"))
    # README 也看一眼(前 4KB 足够)
    rd = gh(["-H", "Accept: application/vnd.github.raw",
             f"/repos/{repo['full_name']}/readme"])
    if isinstance(rd, dict):
        rd = ""
    blob = norm(blob + " " + str(rd or "")[:4000])
    if ax and ax.replace(".", "") in blob.replace(" ", "").replace(".", ""):
        return True, f"README/描述含 arXiv {ax}"
    head = norm(title.split(":")[0])
    if len(head) > 10 and head in blob:
        return True, "含论文主标题"
    ws = words(title)
    if ws:
        hit = sum(1 for w in ws if w in blob) / len(ws)
        if hit >= 0.6:
            return True, f"标题实词命中 {hit:.0%}"
    return False, "描述/README 未提及该论文"


def main():
    C = load_state("lib_corpus.json", {})
    done = {r["key"] for r in load_state("oss.json", [])}
    pool = [(k, v) for k, v in C.items()
            if v["band"] == "5 自动驾驶综述"
            and ("端到端" in v["sub"] or v["sub"] in ("VLM-VLA", "模块化E2E", "RL后训练"))
            and k not in done]
    pool.sort(key=lambda kv: -kv[1]["indeg"])
    if LIMIT:
        pool = pool[:LIMIT]
    print(f"前两级未覆盖 {len(pool)} 篇,逐篇 GitHub 搜索 + 官方性验证\n")

    ok, susp, none = [], [], []
    for n, (k, v) in enumerate(pool, 1):
        name = model_name(v["title"])
        q = f"{name} autonomous driving" if len(name.split()) <= 3 else name
        res = gh(["-X", "GET", "search/repositories", "-f", f"q={q}", "-f", "per_page=5"])
        items = (res or {}).get("items") or []
        best = None
        for it in items[:5]:
            passed, why = verify(it, v["title"], v.get("arxiv", ""))
            if passed and (best is None or it["stargazers_count"] > best[0]["stargazers_count"]):
                best = (it, why)
            time.sleep(0.4)
        if best:
            it, why = best
            ok.append({"key": k, "title": v["title"], "year": v["year"], "indeg": v["indeg"],
                       "repo": f"https://github.com/{it['full_name']}",
                       "stars": it["stargazers_count"], "how": f"GitHub搜索·{why}"})
            print(f"{n:3}. ✓ ★{it['stargazers_count']:<6} {it['full_name'][:38]:38} {why[:22]}", flush=True)
        elif items:
            susp.append({"key": k, "title": v["title"],
                         "top": items[0]["full_name"], "stars": items[0]["stargazers_count"]})
            print(f"{n:3}. ? 疑似 {items[0]['full_name'][:38]:38} 未通过验证", flush=True)
        else:
            none.append(k)
            print(f"{n:3}. ✗ 搜不到  {v['title'][:46]}", flush=True)
        time.sleep(1.0)

    json.dump({"confirmed": ok, "suspect": susp}, open(HERE / "state" / "oss_gh.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"\n第三级确认 {len(ok)} | 疑似(未采信){len(susp)} | 搜不到 {len(none)}")
    print("结果写入 state/oss_gh.json")


if __name__ == "__main__":
    main()
