#!/usr/bin/env python3
"""litpipe · Zotero 读写共用层

所有管线脚本(maintain / build_edges / enrich / generate)共用这一层,
避免每个脚本重复写 env 加载、session、重试、树扫描。

前置:~/.config/zotkit/env 里有 ZOTERO_LIBRARY_ID / ZOTERO_API_KEY。
"""
import json, os, re, time, unicodedata
from pathlib import Path
import requests

ENV_PATH = os.path.expanduser("~/.config/zotkit/env")
ROOT_COLLECTION = "I7T4VTBG"          # 「自动驾驶综述」根分类
HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
STATE.mkdir(exist_ok=True)


def norm_title(s: str) -> str:
    """归一化标题用于匹配。取冒号前主标题,只留小写字母数字。"""
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", s or "").lower().split(":")[0])


def arxiv_of(data: dict) -> str:
    """只在 arxiv 语境提取,避免把 DOI 里的 `年.数字` 误当 arxiv。"""
    a = data.get("archiveID", "") or ""
    m = re.search(r"arxiv[:\s]*(\d{4}\.\d{4,5})", a, re.I) or re.match(r"^\s*(\d{4}\.\d{4,5})\s*$", a)
    if m: return m.group(1)
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", data.get("url", "") or "", re.I)
    if m: return m.group(1)
    m = re.search(r"10\.48550/arXiv\.(\d{4}\.\d{4,5})", data.get("DOI", "") or "", re.I)
    if m: return m.group(1)
    return ""


def load_state(name: str, default):
    p = STATE / name
    if p.exists():
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: return default
    return default


def save_state(name: str, obj):
    json.dump(obj, open(STATE / name, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


class Zot:
    """Zotero Web API 薄封装(带重试/限流退避)。"""

    def __init__(self):
        env = {}
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        self.base = f"https://api.zotero.org/users/{env['ZOTERO_LIBRARY_ID']}"
        self.hdr = {"Zotero-API-Key": env["ZOTERO_API_KEY"], "Zotero-API-Version": "3"}
        self.s = requests.Session()
        self.s.headers.update(self.hdr)

    # ---------- 读 ----------
    def _get(self, path, tries=5):
        for i in range(tries):
            try:
                r = self.s.get(f"{self.base}{path}", timeout=45)
                if r.status_code == 429:
                    time.sleep(5 + 3 * i); continue
                r.raise_for_status()
                return r.json()
            except Exception:
                time.sleep(2 + 2 * i)
        return []

    def subcollections(self, root_key=ROOT_COLLECTION) -> dict:
        """递归取 root 下所有子分类 {key: 名称}(自发现,不依赖过期清单)。"""
        out = {}

        def walk(k, prefix=""):
            for c in self._get(f"/collections/{k}/collections?limit=100") or []:
                name = c["data"]["name"]
                out[c["key"]] = name
                walk(c["key"], name)
        walk(root_key)
        return out

    def items_in_collection(self, coll_key) -> list:
        out, start = [], 0
        while True:
            batch = self._get(f"/collections/{coll_key}/items?limit=100&start={start}")
            if not batch: break
            out += batch
            if len(batch) < 100: break
            start += 100
        return out

    def scan_tree(self, root_key=ROOT_COLLECTION) -> dict:
        """扫整棵树,返回 {itemKey: {"data":..., "version":..., "leaf": 所属叶子名}}。
        自发现子分类,因此树长大了也不用改代码。"""
        cols = self.subcollections(root_key)
        cols[root_key] = "(根)"
        items = {}
        for ck, name in cols.items():
            for it in self.items_in_collection(ck):
                d = it["data"]
                if d.get("itemType") in ("attachment", "note"):
                    continue
                if it["key"] not in items:
                    items[it["key"]] = {"data": d, "version": it["version"], "leaf": name}
        return items

    def get_item(self, key):
        return self._get(f"/items/{key}")

    # ---------- 写 ----------
    def put_item(self, key, data, version) -> bool:
        """全量 PUT。注意:Zotero 要求 relations/tags/collections 必须在(空也要给)。"""
        data.setdefault("relations", {})
        data.setdefault("tags", [])
        data.setdefault("collections", [])
        for i in range(4):
            try:
                r = self.s.put(f"{self.base}/items/{key}",
                               headers={**self.hdr, "If-Unmodified-Since-Version": str(version)},
                               json=data, timeout=45)
                if r.status_code in (200, 204):
                    return True
                if r.status_code == 412:      # 版本冲突:别人改过,跳过让下轮再来
                    return False
                if r.status_code == 429:
                    time.sleep(5 + 3 * i); continue
                return False
            except Exception:
                time.sleep(2 + 2 * i)
        return False


def build_match_index(corpus: dict):
    """corpus: {key: {...,'arxiv','doi','title'}} → 三套匹配索引。
    标题索引要求归一化后 >=12 字符,避免短串误匹配(踩过的坑)。"""
    by_ax, by_doi, by_title = {}, {}, {}
    for k, n in corpus.items():
        if n.get("arxiv"): by_ax[n["arxiv"]] = k
        doi = (n.get("doi") or "").lower()
        if doi and not doi.startswith("10.48550"): by_doi[doi] = k
        t = norm_title(n.get("title", ""))
        if len(t) >= 12: by_title.setdefault(t, k)
    return by_ax, by_doi, by_title


def match_ref(ref: dict, idx) -> str:
    """把一条参考文献匹配到语料里的某篇,返回 key 或 ''。"""
    by_ax, by_doi, by_title = idx
    ax = (ref.get("ax") or "").strip()
    if ax and ax in by_ax: return by_ax[ax]
    doi = (ref.get("doi") or "").lower().strip()
    if doi and doi in by_doi: return by_doi[doi]
    t = norm_title(ref.get("title", ""))
    if len(t) >= 12 and t in by_title: return by_title[t]
    return ""
