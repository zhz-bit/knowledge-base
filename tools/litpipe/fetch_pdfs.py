#!/usr/bin/env python3
"""litpipe · 给指定标签的条目抓 PDF 并作为附件挂上

来源:arXiv(有号的直接下)→ Unpaywall / OpenAlex 的开放获取链接。
付费墙的**不绕**,只报告。

Zotero 附件走 imported_url(linkMode=1):先 POST 建 attachment 条目,
再 PUT 到 /items/<key>/file 上传二进制(需先 POST 授权拿 upload url)。
这里用更省事的方式:zotkit attach --key <parent> --pdf <file>。

用法: python fetch_pdfs.py --tag "2026-07批次" [--apply]
"""
import json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot
from lib_corpus import _api_get as api

TAG = "2026-07批次"
for i, a in enumerate(sys.argv):
    if a == "--tag":
        TAG = sys.argv[i + 1]
APPLY = "--apply" in sys.argv
OUT = HERE / "state" / "pdfs"
UA = {"User-Agent": "litpipe/1.0 (mailto:h.geo.ai@gmail.com)"}


def dl(url, dest, timeout=120):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        b = r.read()
        if len(b) < 40000 or not b[:5].startswith(b"%PDF"):
            return 0
        dest.write_bytes(b)
        return len(b)
    except Exception:
        return 0


def oa_pdf(doi, title):
    """OpenAlex 的 best_oa_location.pdf_url"""
    q = (f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}"
         if doi else
         f"https://api.openalex.org/works?per-page=1&filter=title.search:"
         f"{urllib.parse.quote(re.sub(r'[^\w\s]', ' ', title)[:180])}")
    try:
        d = json.loads(urllib.request.urlopen(
            urllib.request.Request(q, headers=UA), timeout=45).read())
        w = d if doi else (d.get("results") or [None])[0]
        if not w:
            return ""
        for loc in [w.get("best_oa_location"), w.get("primary_location")]:
            if loc and loc.get("pdf_url"):
                return loc["pdf_url"]
    except Exception:
        pass
    return ""


def main():
    z = Zot()
    OUT.mkdir(parents=True, exist_ok=True)
    items = api(z, f"{z.base}/items?tag={urllib.parse.quote(TAG)}&limit=100")
    items = [x for x in items if x["data"].get("itemType") not in ("attachment", "note")]
    print(f"标签「{TAG}」条目 {len(items)} 篇\n")

    got, miss = [], []
    for it in items:
        d = it["data"]
        key, title = it["key"], d.get("title", "")
        dest = OUT / f"{key}.pdf"
        if dest.exists() and dest.stat().st_size > 40000:
            got.append((key, title, dest, "已下载")); continue
        ax = ""
        m = re.search(r"arxiv\.org/abs/([\d.]+)", d.get("url", "") or "")
        if m:
            ax = m.group(1)
        elif (d.get("archiveID") or "").startswith("arXiv:"):
            ax = d["archiveID"][6:]
        n = 0
        src = ""
        if ax:
            n = dl(f"https://arxiv.org/pdf/{ax}", dest); src = "arXiv"
            time.sleep(1.2)
        if not n:
            u = oa_pdf((d.get("DOI") or "").strip(), title)
            if u:
                n = dl(u, dest); src = "开放获取"
            time.sleep(1.1)
        if n:
            got.append((key, title, dest, f"{src} {n // 1024}KB"))
            print(f"  ✓ [{src:6}] {n // 1024:5}KB  {title[:56]}", flush=True)
        else:
            miss.append((key, title))
            print(f"  ✗ 拿不到      {title[:56]}", flush=True)

    print(f"\n下到 {len(got)}/{len(items)};拿不到 {len(miss)}")
    if miss:
        print("拿不到的(付费墙或无开放版,**不绕**):")
        for k, t in miss:
            print(f"   {k}  {t[:62]}")
    if not APPLY:
        print("\n(加 --apply 挂进 Zotero)")
        return

    ok = 0
    for key, title, dest, _ in got:
        ch = api(z, f"{z.base}/items/{key}/children")
        if any(c["data"].get("contentType") == "application/pdf" for c in ch):
            continue                                   # 已有 PDF 附件,跳过
        r = subprocess.run(["zotkit", "attach", "--key", key, "--pdf", str(dest)],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            ok += 1
            print(f"  ✓ 挂载 {title[:54]}", flush=True)
        else:
            print(f"  ✗ 挂载失败 {title[:44]}: {(r.stderr or r.stdout)[:120]}")
        time.sleep(0.5)
    print(f"\n挂载 {ok} 篇")


if __name__ == "__main__":
    main()
