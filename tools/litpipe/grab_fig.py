#!/usr/bin/env python3
"""litpipe · 从论文 PDF 提取模型框图

思路(与 add-e2e-paper skill 里 34 篇焦点论文用的一致,这里做成可批量的工具):
  1) 枚举前 8 页所有「Figure N: ...」题注,取其**上方**绘图元素(矢量 drawings + 位图 images)
     的包围盒并集作为候选图区
  2) 题注里含 architecture/framework/overview 等词的直接采用(快路,零成本)
  3) 关键词全落空时(实测很常见:「Illustration of main training stages」这类题注),
     把前 4 个候选裁出来交给 Haiku 看图挑(--vlm)
  4) 裁剪该区域 2x 渲染成 PNG,存 assets/e2e-ad/<ZoteroKey>.png

题注定位本身不可靠(现有 34 篇里就裁失败过 4 篇),所以裁完必须质检:
  · --qc 用 Haiku 视觉判「是不是完整的模型结构图」,不合格的报出来人工处理
  · 页面对没有 fig 的条目会自动回退 CSS 示意流水线,所以宁缺毋滥

PDF 来源三级回退:本地 Zotero storage → zotkit(WebDAV) → arXiv。

用法:
  python grab_fig.py KEY1 KEY2 ...        # 抓这几篇
  python grab_fig.py --keys-file f.txt    # 从文件读 key(每行一个)
  python grab_fig.py KEY --vlm            # 题注关键词落空时,交给 Haiku 看图挑
  python grab_fig.py KEY --qc             # --vlm + 抓完再做一轮视觉质检
  python grab_fig.py KEY --dry            # 只报告能不能抓,不写文件
"""
import base64, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, urllib.request
from pathlib import Path

import fitz  # PyMuPDF

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import Zot

OUT_DIR = HERE.parent.parent / "assets" / "e2e-ad"
CLAUDE = os.path.expanduser("~/.local/bin/claude")
QC_MODEL = "claude-haiku-4-5"

# 题注里出现这些词 → 大概率是模型总架构图。顺序即优先级。
CAP_WORDS = [
    "overall architecture", "overall framework", "overall pipeline",
    "architecture of", "framework of", "overview of",
    "architecture", "framework", "overview", "pipeline",
]
# 反向词:题注里出现这些,说明是对比/可视化/消融图,即便含 framework 也不是总架构图。
# 实证:UniAD 的 Figure 1 是「Comparison on the various designs of autonomous driving
# framework」—— 关键词命中但选它就错了,真正的架构图是 Figure 2「Pipeline of UniAD」。
CAP_NEG = ["comparison", "compare", "visualization", "qualitative", "ablation",
           "examples of", "statistics", "distribution of", "failure case"]
CAP_RE = re.compile(r"(?:Fig(?:ure)?\.?|图)\s*\.?\s*(\d+)\s*[.:：]", re.I)
CAP_HEAD = 40      # 题注标记必须出现在文本块前 40 字符内,再往后就是正文引用了

DRY = "--dry" in sys.argv
QC = "--qc" in sys.argv
VLM = "--vlm" in sys.argv or QC


# ---------------- PDF 获取 ----------------
def local_pdf(key):
    src = Path.home() / "Zotero/zotero.sqlite"
    if not src.exists():
        return None
    tmp = Path(tempfile.mkdtemp()) / "z.sqlite"
    shutil.copy(src, tmp)
    cur = sqlite3.connect(tmp).cursor()
    cur.execute("""SELECT ai.key, ia.path FROM items i
        JOIN itemAttachments ia ON ia.parentItemID = i.itemID
        JOIN items ai ON ai.itemID = ia.itemID
        WHERE i.key = ? AND ia.contentType = 'application/pdf'""", (key,))
    for akey, path in cur.fetchall():
        if path and path.startswith("storage:"):
            p = Path.home() / "Zotero/storage" / akey / path[len("storage:"):]
            if p.exists():
                return p
    return None


def webdav_pdf(key):
    out = Path(tempfile.mkdtemp())
    try:
        subprocess.run(["zotkit", "fetch", "--key", key, "--out", str(out)],
                       capture_output=True, timeout=120)
    except Exception:
        return None
    pdfs = sorted(out.rglob("*.pdf"), key=lambda p: -p.stat().st_size)
    return pdfs[0] if pdfs else None


def arxiv_pdf(url, extra=""):
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([\d.]+)", (url or "") + " " + (extra or ""))
    if not m:
        return None
    p = Path(tempfile.mkdtemp()) / "a.pdf"
    try:
        req = urllib.request.Request(f"https://arxiv.org/pdf/{m.group(1)}",
                                     headers={"User-Agent": "litpipe/1.0"})
        p.write_bytes(urllib.request.urlopen(req, timeout=90).read())
    except Exception:
        return None
    return p if p.stat().st_size > 50000 else None


def get_pdf(key, data):
    for fn, tag in ((lambda: local_pdf(key), "本地storage"),
                    (lambda: webdav_pdf(key), "WebDAV"),
                    (lambda: arxiv_pdf(data.get("url", ""), data.get("extra", "")), "arXiv")):
        p = fn()
        if p:
            return p, tag
    return None, None


# ---------------- 框图定位 ----------------
def candidates(doc, max_pages=8):
    """枚举前 max_pages 页所有「题注 + 其上方图形区」的候选。

    不预设题注必须含 architecture 一类的词 —— 实测很多论文的架构图题注是
    「Illustration of main training stages」「We extend 3DGS to ...」,关键词法直接漏掉。
    关键词只作为**排序信号**,真拿不准时交给 VLM 看图挑。
    """
    out = []
    for pno in range(min(max_pages, doc.page_count)):
        page = doc[pno]
        for blk in page.get_text("blocks"):
            txt = " ".join(blk[4].split())
            m = CAP_RE.search(txt[:CAP_HEAD])
            if not m:
                continue
            rect = figure_rect(page, fitz.Rect(blk[:4]))
            if rect is None or rect.width < 150 or rect.height < 80:
                continue
            low = txt.lower()
            kw = next((w for w in CAP_WORDS if w in low), None)
            rank = CAP_WORDS.index(kw) if kw else 99
            if kw:
                # 关键词紧跟在「Figure N.」后面(如「Pipeline of UniAD」)最可信;
                # 埋在句子深处的多半只是顺带提到
                if low.index(kw) - m.end() > 24:
                    rank += 6
                if any(n in low for n in CAP_NEG):
                    rank += 40      # 对比/可视化图,直接压到关键词全落空之后
            out.append({"pno": pno, "num": int(m.group(1)), "rect": rect,
                        "cap": txt, "kw": kw, "rank": rank})
    # 关键词强的优先;同强度下页码靠前、图号靠前(总架构图几乎总在正文前几页)
    out.sort(key=lambda c: (c["rank"], c["pno"], c["num"]))
    return out


def ask_vision(workdir, prompt, pattern):
    """在 workdir 里跑一次 Haiku 看图问答。

    两个坑(都踩过):
      · 无头 claude -p 默认没有 Read 权限 → 必须显式 --allowedTools Read,
        否则它只会回一句"我需要权限来读这个文件"
      · 路径要相对 workdir(cwd),绝对路径在工作目录外同样会被拦
    """
    try:
        r = subprocess.run([CLAUDE, "-p", prompt, "--model", QC_MODEL,
                            "--allowedTools", "Read"],
                           cwd=str(workdir), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=300)
        m = re.search(pattern, r.stdout, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


def graphic_clusters(doc, max_pages=8, min_area=20000):
    """不依赖题注的兜底:直接找页面上成片的图形区域。

    有些 PDF 的题注会被数学符号/换行切碎到解析不出来。这时按纵向间隙把
    绘图元素聚成簇,取面积够大的当候选,一样交给 VLM 挑。
    """
    out = []
    for pno in range(min(max_pages, doc.page_count)):
        page = doc[pno]
        boxes = [d["rect"] for d in page.get_drawings()
                 if d["rect"].width > 3 and d["rect"].height > 3]
        for im in page.get_images(full=True):
            try:
                boxes += list(page.get_image_rects(im[0]))
            except Exception:
                pass
        if not boxes:
            continue
        boxes.sort(key=lambda r: r.y0)
        cluster = [boxes[0]]
        clusters = []
        for r in boxes[1:]:
            if r.y0 - max(x.y1 for x in cluster) > 40:
                clusters.append(cluster); cluster = [r]
            else:
                cluster.append(r)
        clusters.append(cluster)
        for cl in clusters:
            rect = cl[0]
            for r in cl[1:]:
                rect |= r
            if rect.width * rect.height < min_area or rect.width < 150 or rect.height < 60:
                continue
            rect = fitz.Rect(rect.x0 - 4, rect.y0 - 4, rect.x1 + 4, rect.y1 + 4) & page.rect
            out.append({"pno": pno, "num": 99, "rect": rect,
                        "cap": f"(无题注·p{pno+1} 图形区 {int(rect.width)}x{int(rect.height)})",
                        "kw": None, "rank": 99})
    out.sort(key=lambda c: (c["pno"], -c["rect"].width * c["rect"].height))
    return out


def render(page, rect, dest):
    page.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2)).save(dest)
    return dest


def vlm_pick(doc, cands, name, topk=4):
    """裁出前 topk 个候选交给 Haiku 看图挑总架构图。返回选中的候选或 None。"""
    tmp = Path(tempfile.mkdtemp())
    shots = []
    for i, c in enumerate(cands[:topk]):
        f = tmp / f"cand{i+1}.png"
        render(doc[c["pno"]], c["rect"], f)
        shots.append((i, c, f))
    listing = "\n".join(
        f'{i+1}. {f.name} —— 题注:{c["cap"][:110]}' for i, c, f in shots)
    prompt = (f"论文《{name}》里裁出了 {len(shots)} 张候选图,请**逐张 Read 看图**后,"
              "挑出最能代表**整篇论文模型总体结构/框架**的那一张。\n\n"
              f"{listing}\n\n"
              "判据:总架构图应能看到成体系的模块方框与数据流箭头,覆盖从输入到输出的主干;"
              "不要选定性结果对比图、数据集示例图、单个子模块细节图、曲线图表。"
              "若裁剪明显不完整(被切断/混进大段正文/空白)则不要选它。\n"
              '只输出 JSON:{"pick":序号或0表示都不合格,"reason":"不超过25字中文理由"}')
    o = ask_vision(tmp, prompt, r'\{[^{}]*"pick"[^{}]*\}')
    if not o:
        return None
    try:
        idx = int(o.get("pick", 0))
    except (TypeError, ValueError):
        return None
    if 1 <= idx <= len(shots):
        c = shots[idx - 1][1]
        c["vlm"] = o.get("reason", "")
        return c
    return None


def figure_rect(page, cap_rect):
    """题注上方的绘图元素包围盒并集(矢量 drawings + 位图 images)。"""
    boxes = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.y1 <= cap_rect.y0 + 2 and r.width > 3 and r.height > 3:
            boxes.append(r)
    for im in page.get_images(full=True):
        try:
            for r in page.get_image_rects(im[0]):
                if r.y1 <= cap_rect.y0 + 2:
                    boxes.append(r)
        except Exception:
            pass
    if not boxes:
        return None
    # 只保留题注上方"连续"的那一坨:从题注往上,遇到 > 40pt 的垂直空白就断开
    boxes.sort(key=lambda r: -r.y1)
    keep, cursor = [], cap_rect.y0
    for r in boxes:
        if cursor - r.y1 > 40:
            break
        keep.append(r)
        cursor = min(cursor, r.y0)
    if not keep:
        return None
    rect = keep[0]
    for r in keep[1:]:
        rect |= r
    # 略微外扩避免切到描边;但**下边不能越过题注顶边**,否则会把
    # 「Figure 2. Framework of ...」那行文字裁进图里(页面自己会另配题注)
    bottom = min(rect.y1 + 4, cap_rect.y0 - 2)
    rect = fitz.Rect(rect.x0 - 4, rect.y0 - 4, rect.x1 + 4, bottom) & page.rect
    return rect


def grab(key, data):
    name = (data.get("title") or key)[:44]
    pdf, src = get_pdf(key, data)
    if not pdf:
        return {"key": key, "name": name, "ok": False, "why": "拿不到 PDF"}
    doc = fitz.open(pdf)
    cands = candidates(doc)
    fallback = ""
    if not cands:                            # 题注解析不出来 → 退回图形聚类
        cands = graphic_clusters(doc)
        fallback = "(无题注,按图形区)"
    if not cands:
        doc.close()
        return {"key": key, "name": name, "ok": False, "why": f"({src})页面上找不到图形区"}

    pick, how = None, ""
    if cands[0]["kw"]:                       # 快路:题注里直接有 architecture/framework 一类的词
        pick, how = cands[0], "题注命中「%s」" % cands[0]["kw"]
    elif VLM:                                # 慢路:交给 Haiku 看图挑
        pick = vlm_pick(doc, cands, name)
        how = fallback + "VLM 挑选:" + (pick.get("vlm", "") if pick else "")
    if pick is None:
        doc.close()
        n = len(cands)
        return {"key": key, "name": name, "ok": False,
                "why": f"({src}){n} 个候选无一命中关键词" + ("" if VLM else",加 --vlm 交给 Haiku 挑")}

    out = OUT_DIR / f"{key}.png"
    rect = pick["rect"]
    if not DRY:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        render(doc[pick["pno"]], rect, out)
    doc.close()
    return {"key": key, "name": name, "ok": True, "src": src, "page": pick["pno"] + 1,
            "word": how, "cap": pick["cap"][:90],
            "size": f"{int(rect.width*2)}x{int(rect.height*2)}",
            "path": str(out), "bytes": out.stat().st_size if out.exists() else 0}


# ---------------- Haiku 视觉质检 ----------------
def qc(path, name):
    """让 Haiku 看图判断:是不是完整的模型结构图。返回 (verdict, reason)。"""
    path = Path(path)
    prompt = (f"Read 图片 {path.name},它是从论文《{name}》PDF 里裁出来的。"
              "判断它是否是一张**完整的模型结构/框架图**:\n"
              "- 完整 = 能看到成体系的模块方框与数据流箭头,没有被边缘切断,没有混入正文段落或表格\n"
              "- 不合格 = 空白/纯文字/表格/只有半张图/裁进了大段正文/只是某个子模块的细节图\n"
              '只输出 JSON:{"verdict":"pass"或"fail","reason":"不超过25字的中文理由"}')
    o = ask_vision(path.parent, prompt, r'\{[^{}]*"verdict"[^{}]*\}')
    return (o.get("verdict", "?"), o.get("reason", "")) if o else ("?", "未解析出结论")


def main():
    keys = [a for a in sys.argv[1:] if re.fullmatch(r"[A-Z0-9]{8}", a)]
    for i, a in enumerate(sys.argv):
        if a == "--keys-file":
            keys += [l.strip() for l in open(sys.argv[i + 1]) if l.strip()]
    if not keys:
        print(__doc__); return

    z = Zot()
    print(f"待抓 {len(keys)} 篇" + ("(干运行,不写文件)" if DRY else ""))
    results = []
    for k in keys:
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(
                f"{z.base}/items/{k}", headers=z.hdr), timeout=30).read())["data"]
        except Exception as e:
            print(f"  ✗ {k} 取元数据失败 {e}"); continue
        r = grab(k, d)
        results.append(r)
        if r["ok"]:
            print(f'  ✓ {r["name"]:44} p{r["page"]} 「{r["word"]}」 {r["size"]} '
                  f'{r["bytes"]//1024}KB  [{r["src"]}]')
        else:
            print(f'  ✗ {r["name"]:44} {r["why"]}')

    ok = [r for r in results if r["ok"]]
    print(f"\n抓到 {len(ok)}/{len(results)}")
    if QC and ok and not DRY:
        print("\nHaiku 视觉质检:")
        for r in ok:
            v, why = qc(r["path"], r["name"])
            mark = {"pass": "✓", "fail": "✗"}.get(v, "?")
            print(f'  {mark} {r["name"]:44} {why}')
            r["qc"] = v
        bad = [r for r in ok if r.get("qc") != "pass"]
        print(f"\n质检通过 {len(ok)-len(bad)}/{len(ok)}"
              + (f";不合格需人工:{', '.join(r['key'] for r in bad)}" if bad else ""))


if __name__ == "__main__":
    main()
