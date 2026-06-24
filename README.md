# 知识库 · 数学与机器学习可视化

一组自包含的知识可视化页面，以及把它们收拢起来的门户首页。直接用浏览器打开 [`index.html`](./index.html) 即可浏览/搜索/筛选。

> 本仓库为**公开**部分，可安全发布到 GitHub Pages。私有的内部技术分享放在 `private/`（已被 `.gitignore` 排除，不随本仓库发布）。

## 目录结构

```
Technology/
├─ index.html          # 知识库门户（入口）—— 搜索 / 分类筛选 / 卡片网格
├─ README.md
├─ templates/          # 知识页模板与设计规范（新页面从这里起步）
│  ├─ knowledge-page.html        默认 · 柔和暗色自包含模板（含全部组件示例）
│  ├─ knowledge-page-warm.html   备选 · 暖米色版（同结构，仅配色不同）
│  └─ THEME.md                   设计令牌与组件速查
├─ pages/              # 知识页面（每个都自包含，可单独打开/分享）
│  ├─ transformer_math_share.html      大模型      Transformer 的数学原理
│  ├─ neural_net_matrix_ops.html       神经网络    神经网络中的矩阵运算
│  ├─ relu-vs-sigmoid.html             神经网络    ReLU vs Sigmoid
│  ├─ 强化学习_GRPO_可视化讲解.html      强化学习    强化学习与 GRPO
│  ├─ lie-groups-slam.html             机器人/SLAM 流形与李群李代数
│  ├─ robotics-autonomous-driving-stack.html 机器人/SLAM ROS·Simulink·CarSim·CARLA 与路径规划全景
│  └─ fourier-series.html              数学基础    傅里叶级数
├─ tools/              # 生成脚本与中间产物（不参与页面渲染）
│  ├─ two-clouds/      点云 GIF 生成脚本 + 产物
│  └─ apple/           “矩阵运算”页面用到的图像处理脚本与中间数据
└─ private/            # 【私有】内部技术分享，.gitignore 排除，不公开（见 private/README.md）
```

## 视觉规范

默认采用**柔和暗色**主题（深海军蓝底 + 柔和米白字 + 柔和强调色，护眼）；另备**暖米色**版用于浅色场景。设计令牌与组件见 [`templates/THEME.md`](./templates/THEME.md)，颜色只用那套变量、不要随手写死十六进制。

## 新增一篇知识页面

1. **复制模板** [`templates/knowledge-page.html`](./templates/knowledge-page.html)（默认暗色；浅色场景用 [`-warm`](./templates/knowledge-page-warm.html) 版）→ `pages/你的文件名.html`，改标题与各小节内容（模板已自带配色、公式、图示、表格、卡片等组件）。如需共享图片，放 `assets/` 并用 `../assets/xxx` 引用。
2. 在 `index.html` 顶部的 `PAGES` 数组里加一条记录：

   ```js
   {
     file:  "pages/你的文件名.html",
     title: "标题",
     sub:   "一句话描述",
     cat:   "分类",          // 复用已有分类，或新建（会自动生成色卡）
     tags:  ["标签1","标签2"],
     icon:  "🔣",            // 封面 emoji
     date:  "2026-06-23"
   }
   ```
3. 刷新 `index.html` 即可看到新卡片。新分类会自动出现在筛选栏。

## 分类

`数学基础` · `神经网络` · `大模型` · `强化学习` · `机器人 / SLAM`

> 分类配色在 `index.html` 的 `CATEGORIES` 对象里定义，可按需调整。

## 发布到 GitHub Pages

本仓库（不含 `private/`）可直接发布为公开站点：仓库 → Settings → Pages → 选 `main` 分支根目录即可。
建议在根目录放一个空的 `.nojekyll` 文件，避免 Jekyll 处理、确保所有文件原样输出。

⚠️ **注意**：GitHub Pages 在免费/Pro/Team 套餐下发布的站点都是**公开**的（即使源仓库私有）。因此私有内容务必留在 `private/`，不要进入本仓库。
