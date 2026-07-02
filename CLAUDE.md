# 知识库仓库约定

纯静态 HTML 个人知识库:门户 `index.html` + `pages/` 下自包含知识页,经 GitHub Pages 公开发布。无构建系统、无框架。

## 目录职责

| 目录 | 职责 |
|---|---|
| `index.html` | 门户(唯一入口)。页面清单在其 `PAGES` 数组,分类在 `CATEGORIES` 对象 —— **数组即唯一真源**,不扫描文件系统 |
| `pages/` | 公开知识页,每页一个自包含 HTML 文件 |
| `templates/` | 新页模板(`knowledge-page.html` 暗色默认 / `-warm` 浅色备选)+ 设计令牌文档 `THEME.md` |
| `assets/<主题>/` | 共享素材,按主题建子目录,目录内放 README 说明来源与用途 |
| `tools/<主题>/` | 页面的生成脚本;中间产物(`.npy`/`.csv` 等)走 `.gitignore` |
| `private/` | **独立 git 仓库**(自带 `.git` 与远端),内部技术分享,浅色主题,已被本仓库 `.gitignore` 排除,**永不发布到 Pages**。本文件的约定不管辖它 |

## 命名规范

- 文件名一律 **kebab-case ASCII**(如 `rl-vs-dl-grpo.html`),不用下划线、中文、空格
- 中文标题放页面 `<title>` 和 `PAGES` 记录的 `title` 字段

## 新增知识页(三步,缺一不可)

1. 复制 `templates/knowledge-page.html` → `pages/<kebab-case 名>.html`,编辑内容
2. 在 `index.html` 的 `PAGES` 数组加一条记录,**全字段**:`file / title / sub / cat / tags / icon / date`;`cat` 取自 `CATEGORIES` 已有分类,新分类须同时在 `CATEGORIES` 里登记配色
3. 运行 `python3 tools/check.py` 确认全绿

只建文件不登记 = 孤儿页,门户永远不显示它。

## 页面要求

- **自包含**:不引外部 CSS/JS 文件(MathJax CDN 除外),样式全部内联,保证单文件可离线分享
- **结构令牌名保持标准**:`--bg / --panel / --panel-2 / --ink / --muted / --line`(名字不改;值以 `templates/THEME.md` 为基准)。强调色可按内容自定义,但变量名用连字符风格(`--panel-2`,不是 `--panel2`)
- **必须含回链**:页内要有指向 `../index.html` 的「← 返回知识库门户」链接
- 老页面的配色是内容定制(示波器风、对比图专用色等),**不回改**;以上约束只对新页生效

## 主题边界

`pages/` 是深色学术风家族(深底 + 米白字 + 彩色点缀,详见 `templates/THEME.md`);`private/` 是刻意独立的浅色体系,两者互不迁就。

## 提交约定

- 中文描述性提交消息,一句话讲清做了什么
- `auto: 定时同步 <时间>` 前缀保留给定时任务,手动提交不要用
- 提交前跑 `python3 tools/check.py`(死链 / 孤儿页 / 命名 / 回链校验)
