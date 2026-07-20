# e2e-ad 素材

「端到端自动驾驶 × VLA 方法全景」页（`pages/e2e-autonomous-driving-vla.html`）的配图。

- `<ZoteroItemKey>.png`：各论文的模型框图 / 核心图，由脚本从论文 PDF 中按题注（architecture / overview / framework 等）定位并裁剪渲染而来。**版权归各论文原作者所有**，页面内每张图均标注图源并链接原文，仅作个人学习笔记引用。
- 生成与更新流程见 `~/.claude/skills/add-e2e-paper/`（`paper_info.py` 同目录的提取思路），新增论文时以 Zotero itemKey 命名新图放入本目录，并在页面 `PAPERS` 条目加 `fig` 字段。
