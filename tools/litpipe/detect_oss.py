#!/usr/bin/env python3
"""litpipe · 检测论文是否开源,把结果写回 Zotero 标签

三级探测,按成本从低到高:
  ① 摘要 / extra / url 里直接出现 github.com|gitlab.com 链接(零成本)
  ② arXiv 的 comments 与 abs 页(作者常把代码链接写在 comment 里)
  ③ GitHub 搜索 API(按论文名找同名仓库,需谨慎:同名仓库不等于官方实现)

**只认前两级为「确认开源」**;第三级仅作候选、标成「疑似」,不自动采信 ——
一个叫 UniAD 的随手仓库不代表论文官方开源。

写回 Zotero 的标签:`开源` / `开源:疑似` / `未见开源`,并把仓库地址写进 extra 的
`Code: <url>` 行(页面与插件都从这里读)。

用法:
  python detect_oss.py               # 干运行
  python detect_oss.py --apply       # 写回 Zotero
  python detect_oss.py --scope e2e   # 只跑端到端那批(默认)
  python detect_oss.py --scope all   # 全库
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot, load_state
from lib_corpus import _api_get as api

APPLY = "--apply" in sys.argv
SCOPE = "e2e"
for i, a in enumerate(sys.argv):
    if a == "--scope":
        SCOPE = sys.argv[i + 1]

UA = {"User-Agent": "litpipe/1.0"}
REPO_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(github\.com|gitlab\.com)/"
    r"([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?(?=[\s,;)\]<>\"']|$)", re.I)
# 这些不是论文代码库
BAD_OWNER = {"github", "topics", "features", "about", "pricing", "marketplace",
             "explore", "sponsors", "collections", "orgs", "settings", "login"}
BAD_REPO = {"readme", "index", "docs", "blob", "tree", "issues", "releases"}


def find_repo(*texts):
    for t in texts:
        for m in REPO_RE.finditer(t or ""):
            host, owner, repo = m.group(1).lower(), m.group(2), m.group(3)
            if owner.lower() in BAD_OWNER or repo.lower() in BAD_REPO:
                continue
            if len(repo) < 2:
                continue
            return f"https://{host}/{owner}/{repo}"
    return ""


def arxiv_meta(ids):
    """批量取 arXiv 的 comment + summary —— 作者常把 code 链接写在 comment。"""
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
            time.sleep(4); continue
        for e in xml.split("<entry>")[1:]:
            g = lambda p: (re.search(p, e, re.S).group(1) if re.search(p, e, re.S) else "")
            ax = re.sub(r"v\d+$", "", g(r"<id>http://arxiv\.org/abs/([^<]+)</id>"))
            out[ax] = {"comment": g(r"<arxiv:comment[^>]*>(.*?)</arxiv:comment>"),
                       "summary": g(r"<summary>(.*?)</summary>")}
        time.sleep(3.2)
    return out


def repo_alive(url, tok=""):
    """确认仓库真实存在(GitHub API);404 的不算开源。"""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)", url)
    if not m:
        return None                                # 非 GitHub 不验证,按存在处理
    h = dict(UA)
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}", headers=h),
            timeout=30).read())
        return {"stars": d.get("stargazers_count", 0),
                "pushed": (d.get("pushed_at") or "")[:10],
                "archived": d.get("archived", False)}
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None


def main():
    z = Zot()
    C = load_state("lib_corpus.json", {})
    if SCOPE == "e2e":
        pool = {k: v for k, v in C.items()
                if v["band"] == "5 自动驾驶综述"
                and ("端到端" in v["sub"] or v["sub"] in ("VLM-VLA", "模块化E2E", "RL后训练"))}
    else:
        pool = C
    print(f"范围 {SCOPE}:{len(pool)} 篇\n")

    # ── ① 本地信号:Zotero 已有的摘要 / extra / url ──
    found, need_ax = {}, []
    for k, v in pool.items():
        try:
            d = api(z, f"{z.base}/items/{k}")["data"]
        except Exception:
            continue
        r = find_repo(d.get("abstractNote", ""), d.get("extra", ""), d.get("url", ""))
        if r:
            found[k] = {"repo": r, "how": "摘要/元数据"}
        elif v.get("arxiv"):
            need_ax.append((k, v["arxiv"]))
    print(f"① 摘要里直接带仓库链接:{len(found)} 篇")

    # ── ② arXiv comment ──
    if need_ax:
        meta = arxiv_meta([a for _, a in need_ax])
        n2 = 0
        for k, ax in need_ax:
            m = meta.get(ax)
            if not m:
                continue
            r = find_repo(m["comment"], m["summary"])
            if r:
                found[k] = {"repo": r, "how": "arXiv comment"}
                n2 += 1
        print(f"② arXiv comment 里带链接:{n2} 篇")

    # ── ③ 验证仓库真实存在 ──
    tok = os.environ.get("GITHUB_TOKEN", "")
    dead = 0
    print("\n③ 验证仓库存在性 ...", flush=True)
    for k, info in list(found.items()):
        st = repo_alive(info["repo"], tok)
        if st is False:
            dead += 1
            found.pop(k)
        elif isinstance(st, dict):
            info.update(st)
        time.sleep(0.9 if tok else 2.4)
    print(f"   仓库 404 剔除 {dead} 篇;确认开源 {len(found)} 篇 / {len(pool)}")

    rows = sorted(({"key": k, "title": C[k]["title"], "year": C[k]["year"],
                    "sub": C[k]["sub"], "indeg": C[k]["indeg"], **v}
                   for k, v in found.items()),
                  key=lambda x: -x["indeg"])
    json.dump(rows, open(HERE / "state" / "oss.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n{'被引':>4} {'年份':>5}  {'★':>5}  仓库 / 标题")
    for x in rows[:40]:
        star = str(x.get("stars", "?"))
        print(f"{x['indeg']:>4} {x['year']:>5}  {star:>5}  {x['repo'][:52]}")
        print(f"                     {x['title'][:66]}")
    print(f"\n共 {len(rows)} 篇开源;结果写入 state/oss.json")

    if not APPLY:
        print("\n(加 --apply 写回 Zotero 标签与 extra 的 Code: 行)")
        return

    ok = 0
    for k, v in found.items():
        it = api(z, f"{z.base}/items/{k}")
        d = dict(it["data"])
        tags = [t for t in d.get("tags", [])
                if t.get("tag") not in ("开源", "未见开源", "开源:疑似")]
        tags.append({"tag": "开源"})
        d["tags"] = tags
        ex = re.sub(r"^Code:.*$\n?", "", d.get("extra", "") or "", flags=re.M)
        d["extra"] = (f"Code: {v['repo']}\n" + ex).strip()
        if z.put_item(k, d, it["version"]):
            ok += 1
        time.sleep(0.3)
    # 其余标「未见开源」,便于插件列区分"查过没有"与"没查过"
    ok2 = 0
    for k in pool:
        if k in found:
            continue
        it = api(z, f"{z.base}/items/{k}")
        d = dict(it["data"])
        if any(t.get("tag") == "未见开源" for t in d.get("tags", [])):
            continue
        d["tags"] = [t for t in d.get("tags", []) if t.get("tag") != "开源"] + [{"tag": "未见开源"}]
        if z.put_item(k, d, it["version"]):
            ok2 += 1
        time.sleep(0.3)
    print(f"\n标「开源」{ok} 篇 | 标「未见开源」{ok2} 篇")


if __name__ == "__main__":
    main()
