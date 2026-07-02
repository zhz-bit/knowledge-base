#!/usr/bin/env python3
"""知识库一致性校验:死链 / 孤儿页 / 命名 / 回链。

用法:python3 tools/check.py   (在仓库任意位置运行均可)
错误(❌)使退出码非 0;警告(⚠️)不影响退出码。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.html$")

errors, warnings = [], []


def main():
    index = ROOT / "index.html"
    text = index.read_text(encoding="utf-8")

    # 1. PAGES 数组里的 file 字段 → 文件必须存在(死链)
    #    先剔除 /* … */ 块注释,示例记录不算登记
    code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    registered = re.findall(r'file:\s*"(pages/[^"]+)"', code)
    for rel in registered:
        if not (ROOT / rel).is_file():
            errors.append(f"死链:index.html 登记了 {rel},但文件不存在")

    # 2. pages/*.html 都必须已登记(孤儿页)
    on_disk = sorted(p.name for p in (ROOT / "pages").glob("*.html"))
    registered_names = {Path(r).name for r in registered}
    for name in on_disk:
        if name not in registered_names:
            errors.append(f"孤儿页:pages/{name} 未登记进 index.html 的 PAGES 数组")

    # 3. 命名:kebab-case ASCII、无空格
    for name in on_disk:
        if not KEBAB.match(name):
            errors.append(f"命名不合规(应为 kebab-case ASCII):pages/{name}")

    # 4. 每页有 <title>,且有回链到 index.html
    for name in on_disk:
        page = (ROOT / "pages" / name).read_text(encoding="utf-8")
        if not re.search(r"<title>[^<]+</title>", page):
            errors.append(f"缺 <title>:pages/{name}")
        if "index.html" not in page:
            warnings.append(f"缺「返回门户」回链:pages/{name}")

    # 5. 仓库内不应存在 .DS_Store 或带空格的文件名(不检查 private/ 与 .git/)
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if rel.parts and rel.parts[0] in (".git", "private"):
            continue
        if p.name == ".DS_Store":
            errors.append(f"垃圾文件:{rel}")
        elif p.is_file() and " " in p.name:
            errors.append(f"文件名含空格:{rel}")

    for msg in errors:
        print(f"❌ {msg}")
    for msg in warnings:
        print(f"⚠️  {msg}")
    n_pages = len(on_disk)
    if not errors and not warnings:
        print(f"✅ 全部通过:{n_pages} 个页面,{len(registered)} 条登记,无死链/孤儿/命名/回链问题")
    elif not errors:
        print(f"✅ 无错误({len(warnings)} 条警告):{n_pages} 个页面,{len(registered)} 条登记")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
