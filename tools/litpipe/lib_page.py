#!/usr/bin/env python3
"""litlib ③ page · 把 lib_layout.json 渲染成 pages/zotero-library-atlas.html

**与自驾综述页共用同一套设计语言**:设计令牌、三套字体的分工(serif 只给标题 /
sans 给正文与 SVG 文本 / mono 给一切元信息)、details.blk 折叠区块、
seg 按钮组做互斥模式、callout 提示块、tier 实心徽章、图谱的两级浮层与悬停溯源。
规格由对 pages/e2e-autonomous-driving-vla.html 的逐层提取得到。

自包含单文件(仓库约定):样式内联、不引外部 CSS/JS(字体 CDN 沿用自驾页的既有例外),含回链。
数据以 `const L = {...};` 注入 —— 重跑本脚本即刷新页面。
"""
import datetime, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import load_state

PAGE = HERE.parent.parent / "pages" / "zotero-library-atlas.html"

HTML = r"""<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Zotero 全库文献地图</title>
<meta name="description" content="整个 Zotero 库 __N__ 篇文献的一张泳道地图：分公用基石与细分方向两个横向独立的河区，各有各的时间轴，只靠引用边相连；纵轴为年份，点大小＝库内被引，红环＝PageRank，河宽＝产出强度，__E__ 条引用边（主干经传递约简）。" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Spectral:wght@400;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
<style>
:root{
  color-scheme:dark;
  --bg:#0e1320; --bg-soft:#121829; --panel:#161d2e; --panel-2:#1d2540;
  --ink:#e4ebf7; --muted:#9aa6bf; --dim:#6b768f; --line:#283248; --line-2:#36425e;
  --terra:#f0a361; --amber:#f0bf4c; --olive:#9bce6b; --teal:#46d7cc;
  --blue:#6aa6ff; --plum:#b49bff; --rust:#ff8a8a;
  --soft-terra:rgba(240,163,97,.14); --soft-amber:rgba(240,191,76,.14);
  --soft-olive:rgba(155,206,107,.13); --soft-teal:rgba(70,215,204,.13);
  --soft-blue:rgba(106,166,255,.14); --soft-plum:rgba(180,155,255,.14);
  --shadow:0 18px 46px rgba(0,0,0,.42); --shadow-sm:0 4px 16px rgba(0,0,0,.30);
  --radius:16px; --maxw:1080px;
  --serif:"Spectral",Georgia,"Songti SC","Noto Serif SC",serif;
  --sans:Inter,ui-sans-serif,system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  --mono:"JetBrains Mono","SF Mono",ui-monospace,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0; font-family:var(--sans); font-size:16.5px; line-height:1.72; color:var(--ink);
  background:radial-gradient(1200px 700px at 84% -12%,#16203a 0%,#111729 46%,var(--bg) 100%);
  background-attachment:fixed;}
a{color:var(--teal); text-decoration:none;}
a:hover{text-decoration:underline;}
h1,h2,h3{font-family:var(--serif); font-weight:600; line-height:1.25; margin:0;}
h1{font-size:clamp(30px,4.4vw,46px); letter-spacing:-.01em;}
h1 em{font-style:normal; color:var(--terra);}
.wrap{max-width:var(--maxw); margin:0 auto; padding:0 24px;}

#progress{position:fixed; left:0; top:0; height:3px; width:0;
  background:linear-gradient(90deg,var(--terra),var(--amber)); z-index:60; transition:width .12s;}
#floatnav{position:fixed; left:0; right:0; top:3px; z-index:50;
  background:rgba(14,19,32,.88); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line);}
#floatnav .fnin{max-width:var(--maxw); margin:0 auto; padding:0 24px;
  display:flex; align-items:center; gap:2px; overflow-x:auto; white-space:nowrap; scrollbar-width:none;}
#floatnav .fnin::-webkit-scrollbar{display:none;}
#floatnav a{font-family:var(--mono); font-size:12px; color:var(--muted);
  padding:9px 11px; border-bottom:2px solid transparent; flex:0 0 auto;}
#floatnav a:hover{color:var(--terra); text-decoration:none;}
#floatnav a.on{color:var(--terra); border-bottom-color:var(--terra);}
#floatnav a.home{color:var(--dim); margin-right:6px;}
#floatnav a.totop{margin-left:auto; color:var(--dim);}
.topnav{padding:26px 0 0;}
.back{font-family:var(--mono); font-size:13px; color:var(--muted);
  display:inline-flex; align-items:center; gap:7px; transition:color .15s;}
.back:hover{color:var(--terra); text-decoration:none;}

header.hero{padding:30px 0 26px; border-bottom:1px solid var(--line); margin-bottom:38px;}
.eyebrow{font-family:var(--mono); font-size:12.5px; letter-spacing:.26em; text-transform:uppercase;
  color:var(--terra); display:flex; align-items:center; gap:11px; margin-bottom:18px;}
.eyebrow::before{content:""; width:30px; height:1px; background:linear-gradient(90deg,var(--terra),transparent);}
.lede{font-size:clamp(16px,2vw,20px); color:var(--muted); margin:18px 0 0; line-height:1.6;}
.lede b{color:var(--ink); font-weight:600;}
.byline{display:flex; flex-wrap:wrap; gap:8px 18px; margin-top:22px;
  font-family:var(--mono); font-size:12.5px; color:var(--dim);}
.byline .pill{background:var(--panel); border:1px solid var(--line); padding:3px 11px; border-radius:999px;}

details.blk{border:1px solid var(--line); border-radius:14px; margin:0 0 16px;
  background:var(--panel); box-shadow:var(--shadow-sm);}
details.blk>summary{list-style:none; cursor:pointer; padding:15px 20px;
  display:flex; align-items:baseline; gap:12px; user-select:none;}
details.blk>summary::-webkit-details-marker{display:none;}
details.blk>summary::before{content:"＋"; font-family:var(--mono); color:var(--terra); font-size:15px; align-self:center;}
details.blk[open]>summary::before{content:"－";}
details.blk>summary .stt{font-family:var(--serif); font-weight:600; font-size:21px; color:var(--ink);}
details.blk>summary .scount{font-family:var(--mono); font-size:12px; color:var(--dim);}
details.blk>*:not(summary){margin-left:20px; margin-right:20px;}
details.blk>div:last-child{margin-bottom:16px;}

.controls{display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin:6px 0 12px;
  padding:12px 14px; background:var(--panel-2); border:1px solid var(--line); border-radius:12px;}
.controls .flbl{font-family:var(--mono); font-size:11.5px; letter-spacing:.12em;
  text-transform:uppercase; color:var(--terra);}
.controls .seg{display:inline-flex; border:1px solid var(--line-2); border-radius:9px; overflow:hidden;}
.controls .seg button{font-family:var(--mono); font-size:12px; color:var(--muted);
  background:transparent; border:0; padding:7px 12px; cursor:pointer;}
.controls .seg button.on{background:var(--panel); color:var(--terra);}
.controls select,.controls button.act{font-family:var(--mono); font-size:12px; color:var(--muted);
  background:var(--bg); border:1px solid var(--line-2); border-radius:9px; padding:6px 10px; cursor:pointer;}
.controls button.act:hover{color:var(--terra); border-color:var(--terra);}
.controls label.chk{font-family:var(--mono); font-size:12px; color:var(--muted);
  display:inline-flex; align-items:center; gap:6px; cursor:pointer;}
.controls .hint{font-family:var(--mono); font-size:11.5px; color:var(--dim); margin-left:auto;}
.controls .lockhint{font-family:var(--mono); font-size:11.5px; color:var(--terra);
  background:var(--soft-terra); border:1px solid rgba(240,163,97,.4); border-radius:999px;
  padding:3px 11px; display:none;}
.controls .lockhint.on{display:inline-block;}

.legend{display:flex; flex-wrap:wrap; gap:8px 16px; margin:0 0 14px;
  font-size:12.5px; color:var(--muted); align-items:center;}
.legend .it{display:inline-flex; align-items:center; gap:7px; user-select:none; padding:2px 6px; border-radius:6px;}
.legend .it.pf{cursor:pointer;}
.legend .it.pf.off{opacity:.32;}
.legend .sw{width:12px; height:12px; border-radius:50%;}
.legend .sep{width:1px; height:16px; background:var(--line-2); margin:0 2px;}
.legend svg{vertical-align:middle;}

.stage{position:relative; overflow:auto; border:1px solid var(--line); border-radius:var(--radius);
  background:linear-gradient(180deg,var(--bg-soft),var(--panel)); box-shadow:var(--shadow-sm); max-height:82vh;}
#gwrap:fullscreen{background:var(--bg); padding:12px;}
#gwrap:fullscreen .stage{max-height:calc(100vh - 140px);}
#graph{display:block; cursor:grab;}
#graph text{font-family:var(--sans); pointer-events:none;}
.skedge{fill:none;}
.sknode{cursor:pointer;}

#tip{position:fixed; z-index:40; max-width:330px; background:var(--panel); border:1px solid var(--line-2);
  border-radius:10px; padding:11px 13px; box-shadow:var(--shadow); font-size:13px;
  pointer-events:none; opacity:0; transition:opacity .1s;}
#tip .tt{font-family:var(--serif); font-weight:600; font-size:14.5px; color:var(--ink); margin-bottom:4px;}
#tip .tm{font-family:var(--mono); font-size:11.5px; color:var(--dim);}
#tip .tc{font-size:12.5px; color:var(--muted); margin-top:5px;}
#skcard{position:fixed; z-index:55; max-width:350px; background:var(--panel); border:1px solid var(--line-2);
  border-radius:12px; padding:14px 16px 12px; box-shadow:var(--shadow); display:none;}
#skcard .ct{font-family:var(--serif); font-weight:600; font-size:15px; color:var(--ink); margin:0 18px 4px 0;}
#skcard .cm{font-family:var(--mono); font-size:11.5px; color:var(--dim); margin-bottom:7px;}
#skcard .cb{font-size:13px; color:var(--muted); max-height:200px; overflow:auto; line-height:1.62;}
#skcard .cx{position:absolute; right:10px; top:8px; cursor:pointer; color:var(--dim);
  font-family:var(--mono); font-size:14px;}
#skcard .cx:hover{color:var(--terra);}

.tier{display:inline-flex; align-items:center; justify-content:center; min-width:17px; height:17px;
  padding:0 3px; border-radius:5px; font-family:var(--mono); font-size:11px; font-weight:700;
  color:#141414; flex:none; margin-right:6px;}
.tS{background:#e8c15a;} .tA{background:#6aa6ff;} .tB{background:#9aa6bf;}
.tC{background:#5c6577;color:#cfd6e4;}
.badge{display:inline-block; font-family:var(--mono); font-size:11.5px; padding:2px 10px;
  border-radius:999px; border:1px solid var(--line-2); color:var(--muted);}
.badge.ccf{color:var(--amber); background:var(--soft-amber); border-color:rgba(240,191,76,.4);}

.callout{display:flex; gap:13px; padding:16px 18px; margin:0 0 22px;
  border:1px solid var(--line); border-left-width:4px; border-radius:12px;
  background:var(--panel); box-shadow:var(--shadow-sm);}
.callout .ic{font-size:20px; line-height:1.5; flex:0 0 auto;}
.callout .ct{flex:1; font-size:14px; color:var(--muted);}
.callout .ct b{color:var(--ink);}
.callout .ct p{margin:0 0 6px;}
.callout .ct p:last-child{margin:0;}
.callout .ct .t{font-weight:700; color:var(--ink); display:block; margin-bottom:3px;}
.callout.note{border-left-color:var(--blue); background:var(--soft-blue);}
.callout.key{border-left-color:var(--amber); background:var(--soft-amber);}

.tablewrap{overflow-x:auto; margin:0 0 16px; border:1px solid var(--line);
  border-radius:var(--radius); box-shadow:var(--shadow-sm);}
table{width:100%; border-collapse:collapse; font-size:14px;}
thead th{font-family:var(--mono); font-size:11.5px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--terra); font-weight:500; text-align:left; padding:10px 14px;
  background:var(--panel-2); border-bottom:1px solid var(--line);}
tbody td{padding:9px 14px; border-bottom:1px solid var(--line); color:var(--muted);}
tbody tr:last-child td{border-bottom:0;}
tbody tr:hover td{background:var(--panel-2);}
tbody td.nm{color:var(--ink);}
tbody td.n{font-family:var(--mono); text-align:right; color:var(--dim);}
.dot{display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:8px;}

footer{border-top:1px solid var(--line); margin-top:46px; padding:24px 0 60px;
  font-size:13.5px; color:var(--dim); display:flex; justify-content:space-between; flex-wrap:wrap; gap:12px;}

@media(max-width:820px){ .controls .hint{margin-left:0; width:100%;} }
@media(max-width:760px){ body{font-size:15.5px;} .wrap{padding:0 16px;} }
</style>

<div id="progress"></div>
<nav id="floatnav"><div class="fnin">
  <a class="home" href="../index.html">⌂ 门户</a>
  <a href="#atlas" data-spy>全库地图</a>
  <a href="#bands" data-spy>库的构成</a>
  <a href="#hubs" data-spy>枢纽论文</a>
  <a href="#method" data-spy>数据口径</a>
  <a class="totop" href="#top">↑ 顶部</a>
</div></nav>

<div class="wrap" id="top" style="padding-top:38px;">
<nav class="topnav"><a class="back" href="../index.html">← 返回知识库门户</a>　·　<a class="back" href="#atlas">↓ 直达地图</a></nav>

<header class="hero">
  <div class="eyebrow">文献库 · A LIBRARY ATLAS</div>
  <h1>Zotero <em>全库文献地图</em></h1>
  <p class="lede">整个 Zotero 库的<b>一张图</b>，分成<b>两个横向独立的河区</b>：上面是<b>公用基石</b>（跨领域通用的骨干与范式），
  下面是<b>细分方向</b>。两区<b>各有各的时间轴</b>，只靠<b>引用边</b>发生关系——悬停任一节点就能看见思想是怎么从上游流下来的。
  泳道不是人为划的，而是<b>从 Zotero 目录结构自动长出来的</b>；<b>纵轴是年份</b>，点的大小是<b>库内被引次数</b>，
  红环是 <b>PageRank</b>，河的宽度就是<b>该时段该方向的产出强度</b>。在 Zotero 里新增一个二级分类，重跑一次这里就自动多一条道。</p>
  <div class="byline">
    <span class="pill">__DATE__</span><span class="pill">__N__ 篇</span>
    <span class="pill">__E__ 条引用边</span><span class="pill">主干 __ETR__ 条</span>
    <span class="pill">__LANES__ 条泳道</span><span class="pill">数据源 Zotero</span>
  </div>
</header>

<main>

<details class="blk" id="atlas" open>
  <summary><span class="stt">全库泳道图</span>
    <span class="scount">上下两区各有时间轴 · 大小＝库内被引 · 红环＝PageRank · 河宽＝产出强度</span></summary>
  <div id="gwrap">
    <div class="controls">
      <span class="flbl">引用边</span>
      <div class="seg" id="seg-edge">
        <button data-mode="tr" class="on">主干骨架</button>
        <button data-mode="all">全部引用</button>
        <button data-mode="off">隐藏</button>
      </div>
      <span class="flbl">筛选</span>
      <select id="f-band"></select>
      <select id="f-tier">
        <option value="">全部评级</option><option value="S">S</option><option value="A">A</option>
        <option value="B">B</option><option value="C">C</option><option value="_none">未评</option>
      </select>
      <label class="chk"><input type="checkbox" id="ck-rib" checked> 显示范式河流</label>
      <label class="chk"><input type="checkbox" id="ck-oss"> 只看开源</label>
      <button class="act" id="ck-full">⛶ 全屏</button>
      <button class="act" id="f-reset">重置</button>
      <span class="lockhint" id="lockhint"></span>
      <span class="hint" id="stat"></span>
    </div>
    <div class="legend" id="legend"></div>
    <div class="stage"><svg id="graph"></svg></div>
    <div id="tip"></div><div id="skcard"></div>
  </div>
  <div class="callout note"><div class="ic">🌊</div><div class="ct">
    <span class="t">怎么读这张图</span>
    <p><b>悬停</b>任一节点，它的全部<b>上游</b>（被它引用的思想来源，蓝）与<b>下游</b>（引用它的后续工作，橄榄）会一起亮起，其余淡出——这是看清一条脉络最快的方式。</p>
    <p><b>点击锁定</b>：点一个节点会把它的溯源<b>钉住</b>，移开鼠标也不消失，方便顺着边慢慢看；
    同时弹出可交互卡片（含 arXiv 链接与全局被引数）。再点该点、点空白处或按「重置」解锁。</p>
    <p>滚轮朝光标缩放 / 拖拽平移 / 双击复位 / ⛶ 全屏。图例可点，用来单独关掉某个领域。</p>
    <p><b>两区的时间尺度不同</b>（基石区更密），中间有虚线分界——不要把跨区的纵向距离读成时间差。
    各区早年论文都压在自己顶部的窄带里：基石区最早到 1958 年、细分方向最早到 __Y0__ 年，不压的话会拉出一大片空白。</p>
  </div></div>
</details>

<details class="blk" id="bands">
  <summary><span class="stt">库的构成</span><span class="scount">按顶层分类</span></summary>
  <div class="tablewrap"><table>
    <thead><tr><th>分类</th><th>包含什么</th><th style="text-align:right">篇数</th></tr></thead>
    <tbody id="bandtbl"></tbody></table></div>
  <div class="callout key"><div class="ic">📌</div><div class="ct">
    <span class="t">归属规则：基石优先，不是最深路径优先</span>
    <p>一篇论文只要挂在<b>公用基石</b>目录下，就归第一层，不因为它在别处有更深的路径而被推走。
    全库有 <b>122 篇跨桶多挂靠</b>；若改按最深路径优先，其中 <b>33 篇</b>基石论文会被推给「计算机视觉」，基石带会从 139 篇缩水到 55 篇。</p>
    <p>「学校事务」是事务性目录（基金申报 / 学位论文 / 公告），不是文献，已整体排除。</p>
  </div></div>
</details>

<details class="blk" id="hubs">
  <summary><span class="stt">枢纽论文</span><span class="scount">按 PageRank · 谁是这个库的源头</span></summary>
  <div class="tablewrap"><table>
    <thead><tr><th>论文</th><th>所属</th><th style="text-align:right">库内被引</th>
      <th style="text-align:right">全局被引</th><th style="text-align:right">PageRank</th></tr></thead>
    <tbody id="hubtbl"></tbody></table></div>
  <div class="callout note"><div class="ic">🔎</div><div class="ct">
    <p>PageRank 沿引用边流向<b>被引者</b>，衡量的是「有多少条思想链最终汇到这里」，和单纯的被引数并不等同：
    被引多但只在一个小圈子里循环的论文，PageRank 不会高。</p>
  </div></div>
</details>

<details class="blk" id="method">
  <summary><span class="stt">数据口径</span><span class="scount">来源 · 边的构造 · 已知局限</span></summary>
  <div class="callout note"><div class="ic">🧾</div><div class="ct">
    <p><b>节点</b>来自 Zotero 全库（__RAW__ 条顶层条目）。剔除事务性目录、无日期、无分类后入图 __N__ 篇。
    评级（⭐）、CCF、中文译名都直接读 Zotero，页面不另存一份。</p>
    <p><b>引用边</b>由 Semantic Scholar 的参考文献列表在库内两两匹配得到，__N__ 篇全部抓取完成，共 __E__ 条。
    <b>主干</b>是对其做<b>传递约简</b>的结果（__ETR__ 条）：若 A→B→C 且 A→C，则删掉 A→C 这条冗余捷径，只留骨架。</p>
    <p><b>已知局限</b>：构造 DAG 时只保留「新引旧」的边，因此<b>同月</b>的互引会被丢弃——这是为了避免
    元数据里偶发的年份颠倒导致成环。跨月的引用不受影响。</p>
  </div></div>
</details>

</main>

<footer>
  <span>知识库 · 全库文献地图 · 数据源 Zotero</span>
  <a class="back" href="../index.html">← 返回知识库门户</a>
</footer>
</div>

<script>
const L = __BLOB__;

const BAND_DESC = {
  "0 公用基石":"跨领域通用的骨干、语言模型、多模态基座、生成模型与学习范式",
  "5 自动驾驶综述":"城区结构化 / 非结构化越野 / 数据集与基准",
  "4 时空序列预测":"交通与城市流量、轨迹建模、数据填补、可信鲁棒",
  "2 计算机视觉":"二维识别、三维与神经渲染、生成编辑、低层视觉、域适应",
  "3 自然语言处理":"语言模型本体、推理后训练、多模态推理、领域落地、RAG",
  "1 深度学习":"架构与表示、生成模型、图网络、强化学习、大模型",
  "6 数据集":"通用基础 / 城区驾驶 / 越野 / 时空地理",
  "8 神经科学与类脑智能":"神经编码与环路、脑网络与模块化、类脑空间智能与具身、神经科学×LLM 表征对齐",
};
const TIERC = {S:"tS",A:"tA",B:"tB",C:"tC"};

/* ── 阅读进度 + 浮动导航高亮 ── */
addEventListener("scroll",()=>{
  const h=document.documentElement;
  document.getElementById("progress").style.width=
    (h.scrollTop/Math.max(1,h.scrollHeight-h.clientHeight)*100)+"%";
  let cur="";
  for(const a of document.querySelectorAll("#floatnav a[data-spy]")){
    const t=document.querySelector(a.getAttribute("href"));
    if(t&&t.getBoundingClientRect().top<160) cur=a.getAttribute("href");
  }
  for(const a of document.querySelectorAll("#floatnav a[data-spy]"))
    a.classList.toggle("on",a.getAttribute("href")===cur);
},{passive:true});

/* ── 构成表 ── */
document.getElementById("bandtbl").innerHTML=L.bands.filter(b=>b.n).map(b=>
  `<tr><td class="nm"><span class="dot" style="background:${b.col}"></span>${b.name}</td>
   <td>${BAND_DESC[b.name]||""}</td><td class="n">${b.n}</td></tr>`).join("");

/* ── 枢纽表(PageRank Top 20) ── */
document.getElementById("hubtbl").innerHTML=Object.entries(L.nodes)
  .sort((a,b)=>b[1].pr-a[1].pr).slice(0,20).map(([k,n])=>
  `<tr><td class="nm">${n.tier?`<span class="tier ${TIERC[n.tier]}">${n.tier}</span>`:""}${n.t}
     <span style="color:var(--dim);font-family:var(--mono);font-size:11.5px"> ${n.y4}</span></td>
   <td><span class="dot" style="background:${n.col}"></span>${n.leaf}</td>
   <td class="n">${n.indeg}</td><td class="n">${(n.cc||0).toLocaleString()}</td>
   <td class="n" style="color:var(--terra)">${n.pr.toFixed(3)}</td></tr>`).join("");

/* ── 图例:领域项可点(即筛选开关)+ 两个内联示意 ── */
const lg=document.getElementById("legend");
lg.innerHTML=L.bands.filter(b=>b.n).map(b=>
  `<span class="it pf" data-band="${b.name}"><span class="sw" style="background:${b.col}"></span>${b.name}</span>`).join("")
 +`<span class="sep"></span>`
 +`<span class="it"><svg width="34" height="16"><circle cx="6" cy="8" r="3" fill="#9aa6bf"/>`
 +`<circle cx="23" cy="8" r="7" fill="#9aa6bf"/></svg>大小＝库内被引</span>`
 +`<span class="it"><svg width="22" height="16"><circle cx="11" cy="8" r="4" fill="#46d7cc"/>`
 +`<circle cx="11" cy="8" r="6.6" fill="none" stroke="#ff8a8a" stroke-width="2"/></svg>红环＝PageRank</span>`
 +`<span class="it"><svg width="22" height="16"><circle cx="11" cy="8" r="4" fill="#6aa6ff"/>`
 +`<circle cx="11" cy="8" r="6" fill="none" stroke="#9bce6b" stroke-width="1.6"/></svg>绿环＝代码开源</span>`
 +`<span class="it" style="color:#6b768f">泳道＝最深一级分类，同一个二级分类下的道共用一个色系</span>`;
const offBands=new Set();

/* ── 领域下拉 ── */
const fb=document.getElementById("f-band");
fb.innerHTML=`<option value="">全部领域</option>`+
  L.bands.filter(b=>b.n).map(b=>`<option value="${b.name}">${b.name}（${b.n}）</option>`).join("");

/* ══════════ 画图 ══════════ */
const NS="http://www.w3.org/2000/svg";
const el=(t,a={})=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const svg=document.getElementById("graph");
svg.setAttribute("width",L.W); svg.setAttribute("height",L.H);
svg.setAttribute("viewBox",`0 0 ${L.W} ${L.H}`);

const defs=el("defs"); const RIB={};
L.bands.forEach((b,i)=>{
  const g=el("linearGradient",{id:"g"+i,x1:"0",y1:"0",x2:"0",y2:"1"});
  g.appendChild(el("stop",{offset:"0","stop-color":b.col,"stop-opacity":".20"}));
  g.appendChild(el("stop",{offset:"1","stop-color":b.col,"stop-opacity":".02"}));
  defs.appendChild(g); RIB[b.name]="url(#g"+i+")";
});
svg.appendChild(defs);
const vp=el("g"); svg.appendChild(vp);
/* 图层序:河流 → 轴/泳道/标签 → 边 → 节点。
   标签并入 axLayer 与节点 g,不另起盖在 nLayer 之上的层,否则会挡住节点热区。 */
const ribLayer=el("g"), axLayer=el("g"), eLayer=el("g"), nLayer=el("g");
vp.append(ribLayer,axLayer,eLayer,nLayer);
/* 浮层挂进 gwrap:全屏时只有 gwrap 子树可见,挂在 body 上会整体消失 */
const gwrap=document.getElementById("gwrap");
const tip=document.getElementById("tip"), card=document.getElementById("skcard");
gwrap.appendChild(tip); gwrap.appendChild(card);

/* ── 缩放 / 平移 ── */
let _tx=0,_ty=0,_k=1;
const _apply=()=>vp.setAttribute("transform",`translate(${_tx.toFixed(1)} ${_ty.toFixed(1)}) scale(${_k.toFixed(3)})`);
function _pt(e){const r=svg.getBoundingClientRect();return{x:(e.clientX-r.left)*L.W/r.width,y:(e.clientY-r.top)*L.H/r.height};}
svg.addEventListener("wheel",e=>{e.preventDefault();const p=_pt(e),f=e.deltaY<0?1.12:1/1.12;
  const nk=Math.min(7,Math.max(0.4,_k*f));_tx=p.x-(p.x-_tx)*(nk/_k);_ty=p.y-(p.y-_ty)*(nk/_k);_k=nk;_apply();},{passive:false});
let _drag=null;
/* 浏览器在 mouseup 之后还会补发一个 click —— 拖动结束那一下会被 document 的
   解锁逻辑当成「点了空白处」,把锁定态冲掉。用位移判据把两者分开:
   按下到松开位移超过 4px 就是拖动,吞掉紧随其后的那个 click。 */
let _suppressClick=false;
svg.addEventListener("mousedown",e=>{if(e.target.closest(".sknode"))return;
  _drag={x:e.clientX,y:e.clientY,tx:_tx,ty:_ty,moved:false};svg.style.cursor="grabbing";});
addEventListener("mousemove",e=>{if(!_drag)return;const r=svg.getBoundingClientRect();
  if(Math.abs(e.clientX-_drag.x)+Math.abs(e.clientY-_drag.y)>4) _drag.moved=true;
  _tx=_drag.tx+(e.clientX-_drag.x)*L.W/r.width;_ty=_drag.ty+(e.clientY-_drag.y)*L.H/r.height;_apply();});
addEventListener("mouseup",()=>{if(_drag){_suppressClick=_drag.moved;_drag=null;svg.style.cursor="";}});
svg.addEventListener("dblclick",()=>{_tx=0;_ty=0;_k=1;_apply();});

/* ── 河流色带(三次样条平滑) ── */
function _sm(p){let d="";for(let i=0;i<p.length-1;i++){
  const a=p[i-1]||p[i],b=p[i],c=p[i+1],e2=p[i+2]||c;
  d+=` C ${(b.x+(c.x-a.x)/6).toFixed(1)} ${(b.y+(c.y-a.y)/6).toFixed(1)}, `
   + `${(c.x-(e2.x-b.x)/6).toFixed(1)} ${(c.y-(e2.y-b.y)/6).toFixed(1)}, `
   + `${c.x.toFixed(1)} ${c.y.toFixed(1)}`;}return d;}
const ribEls=[];
for(const lid in L.ribbons){
  const r=L.ribbons[lid], band=L.lanes[lid].band;
  const A=r.pts.map(q=>({x:r.cx-q.hw,y:q.y})), B=r.pts.map(q=>({x:r.cx+q.hw,y:q.y})).reverse();
  const path=el("path",{d:`M ${A[0].x} ${A[0].y}`+_sm(A)+` L ${B[0].x} ${B[0].y}`+_sm(B)+" Z",
    fill:RIB[band]||"rgba(150,150,150,.05)",stroke:"none"});
  path.__band=band; ribLayer.appendChild(path); ribEls.push(path);
}

/* ── 两个横向独立的河区:上=公用基石、下=细分方向,各有各的时间刻度 ── */
axLayer.appendChild(el("rect",{x:0,y:0,width:L.W,height:L.topH-16,fill:"rgba(180,155,255,.045)"}));
/* 区间分界:两区时间尺度不同,必须画清楚,否则会被误读成一条连续时间轴 */
axLayer.appendChild(el("line",{x1:0,y1:L.topH-8,x2:L.W,y2:L.topH-8,
  stroke:"#36425e","stroke-width":"1.4","stroke-dasharray":"10 7"}));
function regionTitle(y,col,txt){
  const t=el("text",{x:16,y:y,fill:col,"font-family":"var(--mono)","font-size":"13","letter-spacing":"1.6"});
  t.textContent=txt; axLayer.appendChild(t);}
regionTitle(26,"#b49bff",`0 · 公用基石（${L.stats.found} 篇 · 全库共用 · 独立时间轴）`);
regionTitle(L.topH+26,"#f0a361",`细分方向（${L.stats.n-L.stats.found} 篇 · 独立时间轴 · 与上区仅靠引用边相连）`);

/* ── 分层表头:像表格的合并列 —— 桶跨其全部道、二级跨其全部叶、叶各占一格 ── */
/* 汉字横排(竖排太费眼),放不下就截断:等宽字体下 CJK 约占 1 个字宽、ASCII 约 0.55 */
const _cw=(c,fs)=>(/[　-鿿＀-￯]/.test(c)?fs:fs*0.55);
function _width(t,fs){let a=0;for(const c of t)a+=_cw(c,fs);return a;}
/* 三级降级:「名称（篇数）」放不下 → 只留名称 → 再放不下才截断加省略号 */
function fitText(label,n,px,fs){
  const full=`${label}（${n}）`;
  if(_width(full,fs)<=px-6) return full;
  if(_width(label,fs)<=px-6) return label;
  let acc=0,out="";
  for(const c of label){ if(acc+_cw(c,fs)+_cw("…",fs)>px-6) break; acc+=_cw(c,fs); out+=c; }
  return out.length?out+"…":"";
}
function headerRow(rows,y,fs,weight,tickH){
  for(const r of rows){
    const cx=(r.x0+r.x1)/2, wpx=r.x1-r.x0;
    const label=fitText(r.label,r.n,wpx,fs);
    if(label){
      const t=el("text",{x:cx,y:y,"text-anchor":"middle",fill:r.col,
        "font-family":"var(--mono)","font-size":fs,"font-weight":weight||"400"});
      t.textContent=label; axLayer.appendChild(t);
    }
    /* 合并列的边界竖线,让层级像表格一样读得出来 */
    if(tickH){
      for(const x of [r.x0-3,r.x1+3])
        axLayer.appendChild(el("line",{x1:x,y1:y-fs-1,x2:x,y2:y+tickH,
          stroke:r.col,"stroke-width":"1",opacity:".33"}));
      axLayer.appendChild(el("line",{x1:r.x0-3,y1:y+tickH,x2:r.x1+3,y2:y+tickH,
        stroke:r.col,"stroke-width":"1",opacity:".33"}));
    }
  }
}
/* 主河区表头三层 */
headerRow(L.header.bands, L.topH+52, 13.5, "600", 5);
headerRow(L.header.l2,    L.topH+82, 11.5, "500", 4);
headerRow(L.header.leaf,  L.topH+108, 10.5, "400", 0);
/* 基石区只有一层(叶=二级) */
headerRow(L.headerF.leaf, 62, 11.5, "500", 4);

/* 泳道分隔虚线 */
for(const lid in L.lanes){
  const ln=L.lanes[lid], top=ln.band==="0 公用基石";
  axLayer.appendChild(el("line",{x1:ln.x0-3.5,y1:top?72:L.topH+118,
    x2:ln.x0-3.5,y2:top?L.topH-18:L.H-10,
    stroke:ln.col,"stroke-width":"1","stroke-dasharray":"2 8",opacity:".16"}));
}
/* 年份刻度:两区各一套(横向独立 = 各有各的时间尺度) */
function drawTicks(list,m0,cut,ytop){
  for(const t of list){
    axLayer.appendChild(el("line",{x1:0,y1:t.y,x2:L.W,y2:t.y,stroke:"#283248",
      "stroke-width":"1","stroke-dasharray":"3 6",opacity:".4"}));
    const lb=el("text",{x:10,y:t.y-4,fill:"#6b768f","font-family":"var(--mono)","font-size":"11"});
    lb.textContent=t.year; axLayer.appendChild(lb);
  }
  const o=el("text",{x:10,y:ytop,fill:"#6b768f","font-family":"var(--mono)","font-size":"10.5"});
  o.textContent=`${Math.floor(m0/12)}–${cut/12-1}（压缩）`; axLayer.appendChild(o);
}
drawTicks(L.ticksF,L.fm0,L.cutF,90);
drawTicks(L.ticks,L.m0,L.cut,L.topH+124);

/* ── 边 + 上下游邻接 ── */
const up={},dn={}; for(const k in L.nodes){up[k]=[];dn[k]=[];}
const eEls=[];
for(const [a,b] of L.edges){
  const A=L.nodes[a],B=L.nodes[b]; if(!A||!B)continue;
  up[a].push(b); dn[b].push(a);
  const my=(A.y+B.y)/2;
  const p=el("path",{class:"skedge",d:`M${A.x} ${A.y} C ${A.x} ${my}, ${B.x} ${my}, ${B.x} ${B.y}`,
    stroke:"#36425e","stroke-width":"1",opacity:"0"});
  p.__a=a; p.__b=b; eLayer.appendChild(p); eEls.push(p);
}
const trSet=new Set((L.edges_tr||[]).map(e=>e[0]+">"+e[1]));
function reach(s,adj){const seen=new Set(),st=[s];
  while(st.length){const x=st.pop();for(const y of adj[x]||[])if(!seen.has(y)){seen.add(y);st.push(y);}}return seen;}

/* ── 节点:PageRank 红环 + 本体 + 标签(showl/ldy 由离线端算好) ── */
const nEls={};
for(const k in L.nodes){
  const n=L.nodes[k];
  const g=el("g",{class:"sknode"}); g.__k=k;
  if(n.pr>0.03) g.appendChild(el("circle",{cx:n.x,cy:n.y,r:n.r+2.4,fill:"none",stroke:"#ff8a8a",
    "stroke-width":(0.5+n.pr*5.5).toFixed(2),"stroke-opacity":(0.3+n.pr*0.7).toFixed(2)}));
  /* 有代码仓库的多一圈绿描边 —— 扫一眼就知道哪些能跑起来 */
  if(n.code) g.appendChild(el("circle",{cx:n.x,cy:n.y,r:n.r+1.6,fill:"none",
    stroke:"#9bce6b","stroke-width":"1.5","stroke-opacity":".85"}));
  g.appendChild(el("circle",{class:"skc",cx:n.x,cy:n.y,r:n.r,fill:n.col,
    stroke:"#0e1320","stroke-width":"1.6"}));
  if(n.showl){
    const atEdge=n.x>L.W-150;   // 右缘长名会出画,翻成右对齐
    const t=el("text",{class:"skl",x:atEdge?(n.x-n.r-4):n.x,y:n.y+(n.ldy||-(n.r+5)),
      "text-anchor":atEdge?"end":"middle","font-size":"10",fill:"#9aa6bf"});
    t.textContent=n.nm||n.t.slice(0,20); g.appendChild(t);
  }
  nLayer.appendChild(g); nEls[k]=g;
}

/* ── 可见性 / 悬停溯源 / 点击锁定 ── */
let eMode="tr";
let locked=null;          // 被锁定的节点 key;非空时悬停不再改变高亮
function vis(k){const n=L.nodes[k];
  const band=fb.value, tier=document.getElementById("f-tier").value;
  if(offBands.has(n.band)) return false;
  if(band&&n.band!==band) return false;
  if(tier==="_none"&&n.tier) return false;
  if(tier&&tier!=="_none"&&n.tier!==tier) return false;
  if(document.getElementById("ck-oss").checked && !n.code) return false;
  return true;}
function edgeVis(){for(const p of eEls){
  const on=(eMode==="all")||(eMode==="tr"&&trSet.has(p.__a+">"+p.__b));
  p.setAttribute("opacity",on&&vis(p.__a)&&vis(p.__b)?"0.2":"0");
  p.setAttribute("stroke","#36425e");}}
/* 被筛掉的点淡出而非 display:none —— 位置本身是坐标信息,消失会让河看起来漏了 */
/* 复位到"无高亮"态;若有锁定节点则复位成它的溯源态 */
function clr(){
  if(locked){ paint(locked); return; }
  for(const k in nEls){nEls[k].style.opacity=vis(k)?"1":"0.12";
    nEls[k].querySelector(".skc").setAttribute("stroke","#0e1320");}
  edgeVis();
}
/* 把某节点的上下游溯源画出来,返回 {anc,des} 供 tip/卡片用 */
function paint(k){
  const anc=reach(k,up),des=reach(k,dn),keep=new Set([k,...anc,...des]);
  for(const j in nEls) nEls[j].style.opacity=keep.has(j)?"1":"0.12";
  nEls[k].querySelector(".skc").setAttribute("stroke",locked===k?"#f0a361":"#e4ebf7");
  nEls[k].querySelector(".skc").setAttribute("stroke-width",locked===k?"2.6":"1.6");
  for(const p of eEls){
    const on=(p.__a===k&&keep.has(p.__b))||(p.__b===k&&keep.has(p.__a));
    p.setAttribute("opacity",on?"0.85":"0.02");
    p.setAttribute("stroke",p.__a===k?"#6aa6ff":p.__b===k?"#9bce6b":"#36425e");}
  return {anc,des};
}
function meta(n){
  /* 首发年 ≠ 发表年时并列显示 —— 图上的纵坐标用的是首发年,不标出来会让人以为图错了 */
  const yr = (n.pubyear && n.pubyear!==n.y4) ? `${n.y4} 首发 · ${n.pubyear} 发表` : n.y4;
  return `${yr} · ${n.venue||"预印本"}${n.ccf?` <span class="badge ccf">CCF-${n.ccf}</span>`:""}`;}
for(const k in nEls){
  const g=nEls[k], n=L.nodes[k];
  g.addEventListener("mouseenter",()=>{
    if(locked) return;                       // 已锁定:悬停不再抢走高亮
    const {anc,des}=paint(k);
    tip.innerHTML=`<div class="tt">${n.tier?`<span class="tier ${TIERC[n.tier]}">${n.tier}</span>`:""}${n.zh||n.t}</div>`
      +`<div class="tm">${meta(n)}</div>`
      +(n.zh?`<div class="tc">${n.t}</div>`:"")
      +`<div class="tc" style="color:#6b768f">${n.band} / ${n.leaf}<br>`
      +`库内被引 <b>${n.indeg}</b> · 全局被引 <b>${(n.cc||0).toLocaleString()}</b>`
      +` · PageRank <b>${n.pr}</b><br>上游 ${anc.size} / 下游 ${des.size} · 点击锁定</div>`;
    tip.style.opacity=1;});
  g.addEventListener("mousemove",e=>{
    tip.style.left=Math.min(e.clientX+14,innerWidth-346)+"px";
    tip.style.top=(e.clientY+14)+"px";});
  g.addEventListener("mouseleave",()=>{clr();tip.style.opacity=0;});
  g.addEventListener("click",ev=>{ev.stopPropagation();
    /* 再点同一个 = 解锁;点别的 = 改锁到它 */
    locked = (locked===k) ? null : k;
    tip.style.opacity=0;
    if(!locked){ card.style.display="none"; clr(); setLockHint(); return; }
    paint(k); setLockHint(k);
    const ax=n.ax?`<a href="https://arxiv.org/abs/${n.ax}" target="_blank" rel="noopener">arXiv ${n.ax} ↗</a>`:"（无 arXiv 号）";
    card.innerHTML=`<span class="cx">✕</span><div class="ct">${n.zh||n.t}</div>`
      +`<div class="cm">${meta(n)}</div>`
      +`<div class="cb">${n.zh?n.t+"<br><br>":""}${n.band} / ${n.leaf}<br>`
      +`库内被引 ${n.indeg} · 全局被引 ${(n.cc||0).toLocaleString()} · PageRank ${n.pr}<br>${ax}`
      +(n.code?`<br><a href="${n.code}" target="_blank" rel="noopener">⌥ 代码仓库 ${n.code.split("github.com/")[1]||""} ↗</a>`:"")
      +`</div>`;
    card.style.display="block";
    card.style.left=Math.min(ev.clientX+14,innerWidth-366)+"px";
    card.style.top=Math.min(ev.clientY+14,innerHeight-card.offsetHeight-12)+"px";
    card.querySelector(".cx").onclick=e2=>{e2.stopPropagation();
      card.style.display="none"; locked=null; clr(); setLockHint();};});
}
document.addEventListener("click",()=>{
  if(_suppressClick){ _suppressClick=false; return; }   // 刚拖完,不当作点击
  card.style.display="none";
  if(locked){ locked=null; clr(); setLockHint(); }
});

function setLockHint(k){
  const el2=document.getElementById("lockhint");
  if(!k){ el2.classList.remove("on"); el2.textContent=""; return; }
  const n=L.nodes[k];
  el2.textContent=`🔒 已锁定：${(n.nm||n.t).slice(0,26)} — 再点该点或点空白处解锁`;
  el2.classList.add("on");
}

/* ── 控件 ── */
function apply(){
  let n=0; for(const k in L.nodes) if(vis(k)) n++;
  for(const p of ribEls) p.style.display=offBands.has(p.__band)?"none":"";
  clr();
  const parts=L.bands.filter(b=>b.n).map(b=>`${b.name.replace(/^\d+\s*/,"")} ${b.n}`).join(" · ");
  document.getElementById("stat").textContent=`${n} / ${L.stats.n} 篇 · ${parts}`;
}
document.getElementById("seg-edge").addEventListener("click",e=>{
  const b=e.target.closest("button"); if(!b)return;
  eMode=b.dataset.mode==="off"?"none":b.dataset.mode;
  [...e.currentTarget.children].forEach(x=>x.classList.toggle("on",x===b)); edgeVis();});
["f-band","f-tier"].forEach(id=>document.getElementById(id).addEventListener("change",apply));
lg.addEventListener("click",e=>{
  const it=e.target.closest(".it.pf"); if(!it)return;
  const b=it.dataset.band;
  if(offBands.has(b)){offBands.delete(b);it.classList.remove("off");}
  else{offBands.add(b);it.classList.add("off");}
  apply();});
document.getElementById("ck-oss").addEventListener("change",apply);
document.getElementById("ck-rib").addEventListener("change",e=>{
  ribLayer.style.display=e.target.checked?"":"none";});
document.getElementById("f-reset").addEventListener("click",()=>{
  fb.value="";document.getElementById("f-tier").value="";
  offBands.clear();lg.querySelectorAll(".it.pf").forEach(x=>x.classList.remove("off"));
  document.getElementById("ck-oss").checked=false;
  locked=null;setLockHint();card.style.display="none";
  _tx=0;_ty=0;_k=1;_apply();apply();});
document.getElementById("ck-full").addEventListener("click",()=>{
  if(!document.fullscreenElement) gwrap.requestFullscreen&&gwrap.requestFullscreen();
  else document.exitFullscreen&&document.exitFullscreen();});
/* 全屏切换会改变视口尺寸,复位免得视图跑偏 */
document.addEventListener("fullscreenchange",()=>{_tx=0;_ty=0;_k=1;_apply();});
apply();
</script>
"""


def main():
    L = load_state("lib_layout.json", {})
    if not L:
        raise SystemExit("先跑 lib_layout.py")
    html = (HTML
            .replace("__BLOB__", json.dumps(L, ensure_ascii=False, separators=(",", ":")))
            .replace("__N__", str(L["stats"]["n"]))
            .replace("__E__", str(L["stats"]["e"]))
            .replace("__ETR__", str(len(L.get("edges_tr") or [])))
            .replace("__LANES__", str(L["stats"]["lanes"]))
            .replace("__Y0__", str(L["m0"] // 12))
            .replace("__RAW__", "1347")
            .replace("__DATE__", datetime.date.today().isoformat()))
    PAGE.write_text(html, encoding="utf-8")
    print(f"已生成 {PAGE}({PAGE.stat().st_size // 1024} KB) "
          f"节点 {L['stats']['n']} 边 {L['stats']['e']} 主干 {len(L.get('edges_tr') or [])}")


if __name__ == "__main__":
    main()
