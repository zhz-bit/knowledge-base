#!/usr/bin/env python3
"""litpipe · 开源检测第四级:从 **PDF 正文** 挖代码仓库

前三级(摘要 / arXiv comment / GitHub 搜索)漏掉的,多半是作者把链接写在
正文脚注、"Code is available at"、项目页里 —— 这些只有读 PDF 才拿得到。

策略:
  · 只扫**首页 + 末页 + 含 "code/available/github/project page" 的页**,不全文扫
  · 链接常被 PDF 换行断开(github.com/OpenDriveLab/\\nUniAD),要先接回来
  · 项目主页(*.github.io)也算线索:顺着它找同名 GitHub 仓库
  · 拿到候选后仍要过**官方性验证**(README/描述提到本论文),同 detect_oss_gh

用法:
  python detect_oss_pdf.py            # 干运行
  python detect_oss_pdf.py --apply    # 合并进 state/oss_all.json
"""
import json, re, sqlite3, shutil, subprocess, sys, tempfile, time
from pathlib import Path

import fitz
# PDF 里的 Screen 注解会刷屏 "cannot create appearance stream",与我们要的文本无关
fitz.TOOLS.mupdf_display_errors(False)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import load_state
from detect_oss import find_repo, BAD_OWNER, BAD_REPO
from detect_oss_gh import gh, verify

APPLY = "--apply" in sys.argv
HINT_RE = re.compile(r"code\s+(?:is\s+)?(?:available|released|open)|"
                     r"github|project\s+page|open[- ]?source|our\s+code", re.I)


def local_pdfs(keys):
    """{itemKey: Path} —— 支持导入副本与链接文件两种存法。"""
    src = Path.home() / "Zotero/zotero.sqlite"
    if not src.exists():
        return {}
    tmp = Path(tempfile.mkdtemp()) / "z.sqlite"
    shutil.copy(src, tmp)
    cur = sqlite3.connect(tmp).cursor()
    q = ",".join("?" * len(keys))
    cur.execute(f"""SELECT i.key, ai.key, ia.path FROM items i
        JOIN itemAttachments ia ON ia.parentItemID = i.itemID
        JOIN items ai ON ai.itemID = ia.itemID
        WHERE i.key IN ({q}) AND ia.contentType = 'application/pdf'""", list(keys))
    out = {}
    for pkey, akey, path in cur.fetchall():
        if not path or pkey in out:
            continue
        f = (Path.home() / "Zotero/storage" / akey / path[len("storage:"):]
             if path.startswith("storage:") else Path(path))
        if f.exists():
            out[pkey] = f
    return out


def scan_pdf(path):
    """返回 (github 仓库 url, 项目主页 host)。只扫可能含链接的页,不全文扫。"""
    try:
        doc = fitz.open(path)
    except Exception:
        return "", ""
    n = doc.page_count
    pages = {0, 1, n - 1, n - 2}                      # 首尾各两页
    for i in range(min(n, 14)):                        # 正文前段里含线索词的也扫
        if HINT_RE.search(doc[i].get_text()[:6000]):
            pages.add(i)
    txt = []
    for i in sorted(p for p in pages if 0 <= p < n):
        txt.append(doc[i].get_text())
        # 超链接注释里也常藏 URL(文字上看不见)
        try:
            for l in doc[i].get_links():
                if l.get("uri"):
                    txt.append(" " + l["uri"] + " ")
        except Exception:
            pass
    doc.close()
    blob = "\n".join(txt)
    # PDF 换行会把 URL 断开:github.com/Open-\nDriveLab/UniAD → 接回去
    blob = re.sub(r"-\s*\n\s*", "", blob)
    blob = re.sub(r"\n\s*", " ", blob)
    repo = find_repo(blob)
    site = ""
    m = re.search(r"https?://([A-Za-z0-9._-]+)\.github\.io/([A-Za-z0-9._-]+)", blob)
    if m:
        site = f"{m.group(1)}/{m.group(2)}"
    return repo, site


def main():
    C = load_state("lib_corpus.json", {})
    done = {r["key"] for r in load_state("oss_all.json", [])}
    pool = {k: v for k, v in C.items()
            if v["band"] == "5 自动驾驶综述"
            and ("端到端" in v["sub"] or v["sub"] in ("VLM-VLA", "模块化E2E", "RL后训练"))
            and k not in done}
    pdfs = local_pdfs(list(pool))
    print(f"前三级未覆盖 {len(pool)} 篇,其中有本地 PDF 的 {len(pdfs)} 篇\n")

    found, site_only = [], []
    for k, f in pdfs.items():
        v = pool[k]
        repo, site = scan_pdf(f)
        cand = repo
        if not cand and site:                          # 项目页 → 猜同名仓库
            cand = f"https://github.com/{site}"
        if not cand:
            continue
        m = re.match(r"https://github\.com/([^/]+)/([^/]+?)/?$", cand.rstrip("./"))
        if not m:
            continue
        info = gh([f"/repos/{m.group(1)}/{m.group(2)}"])
        if not info or "full_name" not in info:
            site_only.append((k, cand, "仓库不存在"))
            print(f"  ? {v['title'][:40]:40} {cand[:44]} 仓库不存在", flush=True)
            time.sleep(0.4); continue
        passed, why = verify(info, v["title"], v.get("arxiv", ""))
        # **PDF 正文里印着的链接,作者身份本身就是证据** —— 不像 GitHub 搜索
        # 那样是我猜的候选。所以只要仓库真实存在就采信,verify 仅用于加注理由。
        # (BEV-Planner / OmniDrive 的 description 是空的,过不了 verify 却确是官方仓库)
        if repo and not passed:
            # 但**综述/survey 的正文里印的多半是别人的仓库**(它在罗列相关工作),
            # 不能算它自己开源 —— Apollo 与 UniAD 就是这样被两篇综述抢走的。
            if re.search(r"survey|review|benchmark(?:ing)?\s+of|challenges\s+and",
                         v["title"], re.I):
                site_only.append((k, cand, "综述正文里的他人仓库,不采信"))
                print(f"  ? {info['full_name'][:34]:34} 综述引用他人仓库 ← {v['title'][:30]}",
                      flush=True)
                time.sleep(0.4)
                continue
            passed, why = True, "PDF 正文印有该链接"
        if passed:
            found.append({"key": k, "title": v["title"], "year": v["year"],
                          "indeg": v["indeg"], "sub": v["sub"],
                          "repo": f"https://github.com/{info['full_name']}",
                          "stars": info.get("stargazers_count", 0),
                          "pushed": (info.get("pushed_at") or "")[:10],
                          "archived": info.get("archived", False),
                          "how": f"PDF正文·{why}"})
            print(f"  ✓ ★{info.get('stargazers_count',0):<6} {info['full_name'][:34]:34} "
                  f"{why[:18]:18} ← {v['title'][:30]}", flush=True)
        else:
            site_only.append((k, cand, why))
            print(f"  ? {info['full_name'][:34]:34} 未通过验证 ← {v['title'][:30]}", flush=True)
        time.sleep(0.5)

    print(f"\nPDF 正文新增确认 {len(found)} 篇;候选未通过验证 {len(site_only)} 篇")
    json.dump(found, open(HERE / "state" / "oss_pdf.json", "w"), ensure_ascii=False, indent=1)
    if not APPLY:
        print("(加 --apply 合并进 oss_all.json)")
        return
    allr = load_state("oss_all.json", [])
    have = {r["key"] for r in allr}
    allr += [r for r in found if r["key"] not in have]
    json.dump(allr, open(HERE / "state" / "oss_all.json", "w"), ensure_ascii=False, indent=1)
    print(f"合并后共 {len(allr)} 篇开源(再跑 write_oss.py --apply 写回 Zotero)")


if __name__ == "__main__":
    main()
