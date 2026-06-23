# 设计规范 · Design System

知识库统一视觉：**默认柔和暗色**（深海军蓝底 + 柔和米白字 + 柔和强调色）。
新页面从默认模板 [`knowledge-page.html`](./knowledge-page.html) 复制起步；如需浅色场景另有暖米色备选 [`knowledge-page-warm.html`](./knowledge-page-warm.html)。
颜色只用下面这套令牌，不要随手写死十六进制。

## 默认：柔和暗色令牌（`:root`）

### 底色 / 文字 / 线条
| 变量 | 值 | 用途 |
|---|---|---|
| `--bg` | `#0e1320` | 页面底 · 柔和深海军蓝（非纯黑，护眼） |
| `--bg-soft` | `#121829` | 略亮底（渐变/分区） |
| `--panel` | `#161d2e` | 卡片 / 面板 |
| `--panel-2` | `#1d2540` | 次级面板 |
| `--ink` | `#e4ebf7` | 主文字 · 柔和米白（非纯白） |
| `--muted` | `#9aa6bf` | 次要文字 |
| `--dim` | `#6b768f` | 注释 / 弱化 |
| `--line` | `#283248` | 分隔线 |
| `--line-2` | `#36425e` | 较重分隔线 |

### 强调色（柔和、暗底上舒适）
| 变量 | 值 | 角色 | 高亮类 | 柔和底 |
|---|---|---|---|---|
| `--terra` | `#f0a361` | **主强调** · 暖橙 | `.hi` | `--soft-terra` |
| `--amber` | `#f0bf4c` | 金 | `.ha` | `--soft-amber` |
| `--olive` | `#9bce6b` | 柔绿 | `.hg` | `--soft-olive` |
| `--teal` | `#46d7cc` | 青 | `.ht` | `--soft-teal` |
| `--blue` | `#6aa6ff` | 蓝 | `.hb` | `--soft-blue` |
| `--plum` | `#b49bff` | 紫 | — | — |
| `--rust` | `#ff8a8a` | 柔红（警示） | — | — |

> 柔和底 `--soft-*` 用半透明叠加（如 `rgba(240,163,97,.14)`），在暗底上自然融入。
> 阴影用深色 `rgba(0,0,0,.30~.42)`；正文字不用纯白 `#fff`，用 `--ink` 减轻刺眼。

### 字体
- `--serif` Spectral —— 标题（h1/h2/h3）、引述
- `--sans` Inter —— 正文、UI
- `--mono` JetBrains Mono —— 代码、标签、kicker

## 备选：暖米色

浅色/印刷质感场景用 [`knowledge-page-warm.html`](./knowledge-page-warm.html)（暖米底 `#f3ead6` + 暖墨字 `#2d2820` + 大地色强调）。组件、类名与默认暗色版完全一致，只是 `:root` 取值不同——两套可直接替换。

## 组件速查（两套通用）

| 组件 | 写法 |
|---|---|
| 彩色关键词 | `<span class="hi">…</span>`（hi/hb/hg/ha/ht） |
| 高亮笔触 | `<span class="mark">…</span>` |
| 提示框 | `<div class="callout note\|tip\|warn\|key">…</div>` |
| 公式框 | `<div class="mathbox center">\[ … \]</div>` |
| 图示 | `<figure><div class="frame">…</div><figcaption>…</figcaption></figure>` |
| 表格 | `<div class="tablewrap"><table>…</table></div>` |
| 引述 | `<blockquote>…</blockquote>` |
| 卡片网格 | `<div class="cards"><a class="c">…</a></div>` |

模板自带：顶部阅读进度条、返回门户链接、MathJax（不用公式可删整段）。

## 新增一篇知识页（标准流程）

1. 复制 `templates/knowledge-page.html`（默认暗色；浅色用 `-warm` 版）→ `pages/你的文件名.html`。
2. 改 `<title>`、hero（eyebrow / h1 / lede / byline），按需删改各 `section`。
3. 公式用 `\( … \)` / `\[ … \]`；图片放 `assets/` 用 `../assets/xxx` 引用。
4. 在根目录 `index.html` 顶部的 `PAGES` 数组加一条记录（见根 README）。
5. 浏览器打开 `index.html` 验证卡片出现、链接可达。

> 想整体微调色调，只改 `:root` 里的令牌即可；改 `--bg` / `--terra` 全站联动。
