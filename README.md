# 知识库 · 数学与机器学习可视化

一组自包含的知识可视化页面,以及把它们收拢起来的门户首页。直接用浏览器打开 [`index.html`](./index.html) 即可浏览/搜索/筛选。

> 本仓库为**公开**部分,可安全发布到 GitHub Pages。私有的内部技术分享放在 `private/`(独立 git 仓库,已被 `.gitignore` 排除,不随本仓库发布)。

仓库约定(命名、登记流程、页面要求、提交规范)见 [`CLAUDE.md`](./CLAUDE.md);设计令牌与组件速查见 [`templates/THEME.md`](./templates/THEME.md)。

## 目录结构

```
knowledge-base/
├─ index.html          # 知识库门户(入口)—— 搜索 / 分类筛选 / 卡片网格
├─ README.md           # 本文件
├─ CLAUDE.md           # 仓库约定(命名 / 登记 / 页面要求 / 提交规范)
├─ templates/          # 知识页模板与设计规范(新页面从这里起步)
│  ├─ knowledge-page.html        默认 · 柔和暗色自包含模板(含全部组件示例)
│  ├─ knowledge-page-warm.html   备选 · 暖米色版(同结构,仅配色不同)
│  └─ THEME.md                   设计令牌与组件速查
├─ pages/              # 知识页面(每个都自包含,可单独打开/分享)
│                      # 完整清单以 index.html 的 PAGES 数组为准,不在此重复罗列
├─ assets/             # 共享素材,按主题分子目录,各目录内有 README 说明
│  └─ slides-2025/     演讲幻灯片照片(Sutton OaK / Design for Learning / RL 基础)
├─ tools/              # 生成脚本与中间产物(不参与页面渲染)
│  ├─ check.py         一致性校验:死链 / 孤儿页 / 命名 / 回链
│  ├─ two-clouds/      点云 GIF 生成脚本 + 产物
│  └─ apple/           "矩阵运算"页面用到的图像处理脚本与中间数据
└─ private/            # 【私有】独立 git 仓库,.gitignore 排除,不公开(见 private/README.md)
```

## 视觉规范

`pages/` 默认采用**柔和暗色**学术主题(深海军蓝底 + 柔和米白字 + 柔和强调色,护眼);另备**暖米色**模板用于浅色场景。设计令牌与组件见 [`templates/THEME.md`](./templates/THEME.md)。结构令牌(`--bg/--panel/--ink` 等)名字保持标准,强调色可按页面内容定制。`private/` 是刻意独立的浅色体系,不适用本规范。

## 新增一篇知识页面

1. **复制模板** [`templates/knowledge-page.html`](./templates/knowledge-page.html)(浅色场景用 [`-warm`](./templates/knowledge-page-warm.html) 版)→ `pages/<kebab-case 文件名>.html`,改标题与内容。共享图片放 `assets/<主题>/`,用 `../assets/…` 引用。
2. 在 `index.html` 顶部的 `PAGES` 数组里加一条记录:

   ```js
   {
     file:  "pages/your-page-name.html",
     title: "标题",
     sub:   "一句话描述",
     cat:   "分类",          // 复用已有分类,或新建(会自动生成色卡)
     tags:  ["标签1","标签2"],
     icon:  "🔣",            // 封面 emoji
     date:  "2026-07-02"
   }
   ```
3. 运行 `python3 tools/check.py` 校验(死链 / 孤儿页 / 命名 / 回链),全绿后刷新 `index.html` 即可看到新卡片。

## 分类

`数学基础` · `神经网络` · `大模型` · `强化学习` · `机器人 / SLAM` · `科研方法`

> 分类配色在 `index.html` 的 `CATEGORIES` 对象里定义,可按需调整;新分类会自动出现在筛选栏。

## 发布到 GitHub Pages

本仓库(不含 `private/`)可直接发布为公开站点:仓库 → Settings → Pages → 选 `main` 分支根目录即可。
根目录的空 `.nojekyll` 文件用于跳过 Jekyll 处理、确保所有文件原样输出,请保留。

⚠️ **注意**:GitHub Pages 在免费/Pro/Team 套餐下发布的站点都是**公开**的(即使源仓库私有)。因此私有内容务必留在 `private/`,不要进入本仓库。
