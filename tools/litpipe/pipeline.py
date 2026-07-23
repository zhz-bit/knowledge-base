#!/usr/bin/env python3
"""litpipe · 一条龙编排 —— 加完论文跑这一条命令即可

顺序(不可调换):
  ① maintain     venue 规范 + CCF 标签(确定性,离线)
  ② build_edges  增量抓新论文的完整参考列表 → 全量重算引用边 + indeg + 收割 cc
  ③ enrich       Haiku 评级⭐ + 标题翻译(**必须在 ② 之后**,评级要用 indeg/cc 当锚)
  ④ classify     收件箱待分类条目 → Haiku 建议叶子(高置信自动归档,其余打建议标签)
  ⑤ generate     从 Zotero 重建页面数据并注入(纯渲染;收件箱条目不进图)
  ⑤ publish      check.py → git commit → push(GitHub Pages)

并发保护:全程持 state/.pipeline.lock。**同一时刻只允许一个写库流程**——
两股写入会让 Zotero 客户端同步时报 "Collection ... not found"(踩过)。

用法:
  python pipeline.py                      # 干运行:每步只报告,不写库不改页面
  python pipeline.py --apply              # 全流程执行(不含 push)
  python pipeline.py --apply --publish    # 全流程 + git push
  python pipeline.py --apply --steps edges,enrich,generate
"""
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LOCK = HERE / "state" / ".pipeline.lock"
STEPS_ALL = ["maintain", "edges", "enrich", "classify", "generate"]

APPLY = "--apply" in sys.argv
PUBLISH = "--publish" in sys.argv
steps = STEPS_ALL
for i, a in enumerate(sys.argv):
    if a == "--steps": steps = [s.strip() for s in sys.argv[i + 1].split(",")]

SCRIPT = {"maintain": "maintain.py", "edges": "build_edges.py",
          "enrich": "enrich.py", "classify": "classify.py", "generate": "generate.py"}


def acquire_lock():
    if LOCK.exists():
        try:
            info = json.loads(LOCK.read_text())
            pid = info.get("pid")
            # macOS 没有 /proc,用 kill(pid,0) 探活:
            #   ProcessLookupError = 进程不存在;PermissionError = 进程存在但无权限(仍算存活)
            alive = False
            if pid:
                try:
                    os.kill(int(pid), 0); alive = True
                except ProcessLookupError: alive = False
                except PermissionError: alive = True
                except Exception: alive = False
            if alive:
                print(f"⛔ 已有 pipeline 在跑(pid={pid}, 起于 {info.get('at')}),本次退出。", flush=True)
                print("   同一时刻只允许一个写库流程,避免 Zotero 同步撞车。")
                sys.exit(1)
            print(f"⚠ 发现残留锁(pid={pid} 已不存在),接管。", flush=True)
        except Exception:
            pass
    LOCK.parent.mkdir(exist_ok=True)
    LOCK.write_text(json.dumps({"pid": os.getpid(), "at": datetime.now().isoformat(timespec="seconds")}))


def release_lock():
    try: LOCK.unlink()
    except Exception: pass


def run(name):
    script = SCRIPT[name]
    args = [sys.executable, str(HERE / script)] + (["--apply"] if APPLY else [])
    print(f"\n{'='*66}\n▶ {name}  ({script} {'--apply' if APPLY else '干运行'})\n{'='*66}", flush=True)
    t0 = time.time()
    r = subprocess.run(args, cwd=str(HERE))
    dt = time.time() - t0
    if r.returncode != 0:
        print(f"✗ {name} 失败(exit {r.returncode}),中止后续步骤。", flush=True)
        return False
    print(f"✓ {name} 完成,用时 {dt/60:.1f} 分钟", flush=True)
    return True


def publish():
    print(f"\n{'='*66}\n▶ publish\n{'='*66}", flush=True)
    chk = subprocess.run([sys.executable, str(REPO / "tools" / "check.py")], cwd=str(REPO))
    if chk.returncode != 0:
        print("✗ check.py 未通过,不提交。"); return
    if not APPLY:
        print("(干运行:跳过 commit/push)"); return
    subprocess.run(["git", "add", "pages/", "tools/litpipe/"], cwd=str(REPO))
    msg = f"auto: litpipe 增量更新 {datetime.now():%Y-%m-%d %H:%M}"
    c = subprocess.run(["git", "commit", "-q", "-m", msg], cwd=str(REPO))
    if c.returncode != 0:
        print("(无改动可提交)"); return
    if PUBLISH:
        subprocess.run(["git", "push", "origin", "main"], cwd=str(REPO))
        print("✓ 已 push", flush=True)
    else:
        print("✓ 已 commit(未 push;加 --publish 推送)", flush=True)


def main():
    acquire_lock()
    t0 = time.time()
    # 方案甲:每趟运行开头清掉分类结构缓存 → 本趟第一个步骤取一次新鲜的,
    # 后续步骤复用(结构不会被任何步骤修改,所以等价);条目数据仍每步实时取。
    try:
        (HERE / "state" / "collections_cache.json").unlink()
        print("已清分类结构缓存(本趟将重新取一次)", flush=True)
    except FileNotFoundError:
        pass
    print(f"litpipe 一条龙 · {'执行' if APPLY else '干运行'} · 步骤 {steps}", flush=True)
    try:
        for s in steps:
            if s not in SCRIPT:
                print(f"跳过未知步骤 {s}"); continue
            if not run(s): break
        else:
            publish()
    finally:
        release_lock()
    print(f"\n总用时 {(time.time()-t0)/60:.1f} 分钟", flush=True)


if __name__ == "__main__":
    main()
