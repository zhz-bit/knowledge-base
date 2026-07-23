#!/usr/bin/env python3
"""litlib ③ page · 把 lib_layout.json 渲染成 pages/zotero-library-atlas.html

自包含单文件(仓库约定):样式内联、不引外部 CSS/JS,含返回门户的回链。
数据以 `const L = {...};` 注入,与自驾页同一套做法 —— 重跑本脚本即刷新页面。
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zotero_io import load_state

PAGE = HERE.parent.parent / "pages" / "zotero-library-atlas.html"

HTML = r"""<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Zotero 全库文献地图</title>
<meta name="description" content="整个 Zotero 库 __N__ 篇文献的泳道地图：公用基石在第一层，自动驾驶/时空预测/计算机视觉/NLP/深度学习/数据集并列分道，纵轴为时间，点大小=库内被引，__E__ 条引用边。" />
<style>
:root{
  --bg:#0d1117; --panel:#141b25; --panel-2:#1b2430; --ink:#e8e3d8; --muted:#8b95a5; --line:#243040;
  --found:#b49bff; --ad:#46d7cc; --st:#6aa6ff; --cv:#f0806c; --nlp:#f0bf4c; --dl:#8fd67a; --ds:#e08fd0;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.7 "Noto Serif SC","Songti SC",Georgia,serif;}
code,.mono{font-family:"SF Mono",Menlo,Consolas,monospace;}
a{color:var(--ad);}
.wrap{max-width:1280px;margin:0 auto;padding:26px 20px 70px;}
.back{display:inline-block;margin-bottom:18px;color:var(--muted);text-decoration:none;font-size:13.5px;}
.back:hover{color:var(--ink);}
h1{font-size:30px;margin:0 0 8px;letter-spacing:.5px;}
.lede{color:var(--muted);max-width:78ch;margin:0 0 14px;font-size:15px;}
.lede b{color:var(--ink);font-weight:600;}
.pills{display:flex;flex-wrap:wrap;gap:7px;margin:0 0 22px;}
.pill{font-size:12px;color:var(--muted);background:var(--panel);border:1px solid var(--line);
  border-radius:999px;padding:3px 11px;}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 16px 12px;margin:0 0 20px;}
.card h2{font-size:17px;margin:0 0 4px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;}
.card h2 span{font-size:12px;color:var(--muted);font-weight:400;}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0 6px;
  background:var(--panel-2);border:1px solid var(--line);border-radius:10px;padding:8px 10px;}
.bar label{font-size:12.5px;color:var(--muted);}
.bar select,.bar button{background:var(--bg);color:var(--ink);border:1px solid var(--line);
  border-radius:7px;padding:4px 9px;font-size:12.5px;font-family:inherit;cursor:pointer;}
.bar button:hover{border-color:var(--ad);}
.bar .grow{flex:1;}
.bar .cnt{font-size:12px;color:var(--muted);}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted);margin:2px 0 8px;}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle;}
.viewport{position:relative;overflow:auto;border:1px solid var(--line);border-radius:10px;
  background:#0a0e14;max-height:78vh;}
svg{display:block;}
.lanebox{fill:#ffffff06;stroke:#ffffff12;}
.lanelbl{font:11px/1.2 "SF Mono",Menlo,monospace;fill:var(--muted);}
.bandlbl{font:12px/1.2 "SF Mono",Menlo,monospace;fill:var(--ink);opacity:.85;}
.yearlbl{font:10.5px "SF Mono",Menlo,monospace;fill:#5c6675;}
.gridln{stroke:#ffffff0a;}
.edge{stroke:#ffffff10;fill:none;}
.node{cursor:pointer;}
.node.dim{opacity:.09;}
.node.hot{stroke:#fff;stroke-width:1.4;}
#tip{position:fixed;z-index:60;max-width:400px;background:var(--panel);border:1px solid var(--line);
  border-radius:10px;padding:11px 13px;font-size:13px;box-shadow:0 10px 30px #0009;display:none;line-height:1.55;}
#tip .tt{font-weight:600;margin-bottom:5px;}
#tip .mt{color:var(--muted);font-size:12px;font-family:"SF Mono",Menlo,monospace;}
#tip .zh{color:var(--ink);opacity:.8;font-size:12.5px;margin-top:4px;}
.tier{display:inline-block;font:11px/1 "SF Mono",Menlo,monospace;border-radius:4px;padding:2px 5px;margin-right:5px;}
.tS{background:#ffd76a22;color:#ffd76a;border:1px solid #ffd76a44;}
.tA{background:#46d7cc22;color:#46d7cc;border:1px solid #46d7cc44;}
.tB{background:#6aa6ff22;color:#6aa6ff;border:1px solid #6aa6ff44;}
.tC{background:#8b95a522;color:#8b95a5;border:1px solid #8b95a544;}
table.bands{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:6px;}
table.bands th,table.bands td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);}
table.bands th{color:var(--muted);font-weight:400;font-size:12px;}
table.bands td.n{font-family:"SF Mono",Menlo,monospace;color:var(--muted);text-align:right;}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;}
.note{color:var(--muted);font-size:12.5px;margin:10px 0 0;}
</style>

<div class="wrap">
<a class="back" href="../index.html">← 返回知识库门户</a>

<h1>Zotero 全库文献地图</h1>
<p class="lede">整个 Zotero 库的<b>一张图</b>。泳道不是我定的，是<b>从你的目录结构自动生成</b>的：
<b>公用基石</b>坐第一层横带，内部按 5 个子方向分并列细道；其余领域在下方并列成河，每个领域内部再按二级分类分道，
<b>纵轴是时间</b>，点的大小代表<b>库内被引次数</b>。在 Zotero 里新增一个二级分类，这里就自动多一条道。</p>
<div class="pills">
  <span class="pill mono">__DATE__</span>
  <span class="pill">__N__ 篇</span>
  <span class="pill">__E__ 条引用边</span>
  <span class="pill">__LANES__ 条泳道</span>
  <span class="pill">数据源 Zotero</span>
</div>

<div class="card">
  <h2>库的构成 <span>按顶层分类</span></h2>
  <table class="bands"><thead><tr><th>分类</th><th>说明</th><th style="text-align:right">篇数</th></tr></thead>
  <tbody id="bandtbl"></tbody></table>
  <p class="note">「公用基石」采用<b>优先归属</b>：一篇论文只要挂在基石目录下，就归第一层，不因为它在别处有更深的路径而被推走
  —— 全库有 122 篇跨桶多挂靠，若按最深路径优先，其中 33 篇基石论文会被推给「计算机视觉」。
  「学校事务」是事务性目录（基金申报 / 学位论文 / 公告等），不是文献，已排除。</p>
</div>

<div class="card">
  <h2>全库泳道图 <span>纵轴＝时间 · 点大小＝库内被引 · 颜色＝所属领域</span></h2>
  <div class="bar">
    <label>领域</label><select id="f-band"></select>
    <label>评级</label><select id="f-tier">
      <option value="">全部</option><option value="S">S</option><option value="A">A</option>
      <option value="B">B</option><option value="C">C</option><option value="_none">未评</option></select>
    <label>引用边</label><select id="f-edge">
      <option value="none">隐藏</option>
      <option value="30">仅骨干（指向被引≥30 的）</option>
      <option value="12">主干（≥12）</option>
      <option value="all">全部 8208 条</option>
    </select>
    <button id="f-reset">重置</button>
    <span class="grow"></span><span class="cnt" id="cnt"></span>
  </div>
  <div class="legend" id="legend"></div>
  <div class="viewport" id="vp"><svg id="svg"></svg></div>
  <p class="note">点一下节点看详情；有 arXiv 号的可直接跳原文。2015 年之前的论文压在顶部窄带里（否则 1958–2014 会拉出一大片空白）。</p>
</div>

</div>
<div id="tip"></div>

<script>
const L = __BLOB__;

const TIER_LBL = {S:"S",A:"A",B:"B",C:"C"};
const BAND_DESC = {
  "0 公用基石":"跨领域通用的骨干、语言模型、多模态基座、生成模型与学习范式",
  "5 自动驾驶综述":"城区结构化 / 非结构化越野 / 数据集与基准",
  "4 时空序列预测":"交通与城市流量、轨迹建模、数据填补、可信鲁棒",
  "2 计算机视觉":"二维识别、三维与神经渲染、生成编辑、低层视觉、域适应",
  "3 自然语言处理":"语言模型本体、推理后训练、多模态推理、领域落地、RAG",
  "1 深度学习":"架构与表示、生成模型、图网络、强化学习、大模型",
  "6 数据集":"通用基础 / 城区驾驶 / 越野 / 时空地理",
};

/* ── 构成表 ── */
document.getElementById("bandtbl").innerHTML = L.bands.filter(b=>b.n).map(b=>
  `<tr><td><span class="dot" style="background:${b.col}"></span>${b.name}</td>
   <td style="color:var(--muted);font-size:12.5px">${BAND_DESC[b.name]||""}</td>
   <td class="n">${b.n}</td></tr>`).join("");

/* ── 图例 + 领域下拉 ── */
document.getElementById("legend").innerHTML = L.bands.filter(b=>b.n).map(b=>
  `<span><i style="background:${b.col}"></i>${b.name}</span>`).join("")
  + `<span style="margin-left:6px">点越大＝库内被引越多</span>`;
const fb = document.getElementById("f-band");
fb.innerHTML = `<option value="">全部</option>` +
  L.bands.filter(b=>b.n).map(b=>`<option value="${b.name}">${b.name}（${b.n}）</option>`).join("");

/* ── 画图 ── */
const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("svg");
svg.setAttribute("width", L.W); svg.setAttribute("height", L.H);
svg.setAttribute("viewBox", `0 0 ${L.W} ${L.H}`);
function el(t, a){ const e=document.createElementNS(NS,t); for(const k in a) e.setAttribute(k,a[k]); return e; }

const gLane = el("g",{}), gEdge = el("g",{}), gNode = el("g",{}), gLbl = el("g",{});
svg.append(gLane, gEdge, gNode, gLbl);

/* 泳道底框 + 标题 */
const topLanes = Object.entries(L.lanes).filter(([k,v])=>v.band==="0 公用基石");
const mainLanes = Object.entries(L.lanes).filter(([k,v])=>v.band!=="0 公用基石");
gLane.append(el("rect",{x:8,y:44,width:L.W-16,height:L.topH-56,rx:10,
  fill:"#b49bff08",stroke:"#b49bff22"}));
const t1 = el("text",{x:16,y:32,class:"bandlbl"}); t1.textContent = `第一层 · 公用基石（${L.stats.found} 篇）`;
gLbl.append(t1);
for(const [k,v] of topLanes){
  gLane.append(el("rect",{x:v.x0,y:56,width:v.x1-v.x0,height:L.topH-70,rx:8,class:"lanebox"}));
  const t = el("text",{x:v.x0+7,y:70,class:"lanelbl"}); t.textContent = `${v.label}（${v.n}）`;
  gLbl.append(t);
}
let curBand = null;
let li = 0;
for(const [k,v] of mainLanes){
  gLane.append(el("rect",{x:v.x0,y:L.topH+30,width:v.x1-v.x0,height:L.H-L.topH-46,rx:8,class:"lanebox"}));
  // 相邻泳道标签交错两行高度,否则长分类名会互相压成一团
  const t = el("text",{x:v.x0+5,y:L.topH+(li++%2?24:11),class:"lanelbl"}); t.textContent = v.label;
  gLbl.append(t);
  if(v.band!==curBand){
    curBand=v.band;
    const b = el("text",{x:v.x0,y:L.topH+6,class:"bandlbl",fill:v.col}); b.textContent=v.band;
    gLbl.append(b);
  }
}
/* 年份刻度 */
const y0=Math.floor(L.m0/12), y1=Math.floor(L.m1/12), cutY=L.cut/12;
function yof(m){ return m<L.cut ? L.topH+70+(m-L.m0)/Math.max(1,L.cut-L.m0)*120
                                : L.topH+195+(m-L.cut)*15; }
for(let y=cutY; y<=y1; y++){
  const yy = yof(y*12);
  gLane.append(el("line",{x1:8,y1:yy,x2:L.W-8,y2:yy,class:"gridln"}));
  const t=el("text",{x:10,y:yy-3,class:"yearlbl"}); t.textContent=y; gLbl.append(t);
}
const tOld=el("text",{x:10,y:L.topH+66,class:"yearlbl"}); tOld.textContent=`${y0}–${cutY-1}（压缩）`;
gLbl.append(tOld);

/* 边 */
const edgeEls = L.edges.map(([a,b])=>{
  const A=L.nodes[a], B=L.nodes[b];
  const e = el("path",{d:`M${A.x},${A.y} C${A.x},${(A.y+B.y)/2} ${B.x},${(A.y+B.y)/2} ${B.x},${B.y}`,class:"edge"});
  e.__a=a; e.__b=b; gEdge.append(e); return e;
});

/* 节点 */
const nodeEls = {};
for(const k in L.nodes){
  const n = L.nodes[k];
  const c = el("circle",{cx:n.x,cy:n.y,r:n.r,fill:n.col,"fill-opacity":.62,
    stroke:n.col,"stroke-width":.9,class:"node"});
  c.__k = k;
  gNode.append(c); nodeEls[k]=c;
}

/* ── 交互 ── */
const tip = document.getElementById("tip");
function showTip(ev, k){
  const n = L.nodes[k];
  const ax = n.ax ? ` · <a href="https://arxiv.org/abs/${n.ax}" target="_blank" rel="noopener">arXiv ${n.ax} ↗</a>` : "";
  tip.innerHTML = `<div class="tt">${n.tier?`<span class="tier t${n.tier}">${n.tier}</span>`:""}${n.t}</div>`
    + (n.zh?`<div class="zh">${n.zh}</div>`:"")
    + `<div class="mt">${n.y4} · ${n.venue||"预印本"}${n.ccf?` · CCF-${n.ccf}`:""}</div>`
    + `<div class="mt">${n.band} / ${n.leaf} · 库内被引 ${n.indeg} · 全局被引 ${n.cc}${ax}</div>`;
  tip.style.display="block";
  const r = tip.getBoundingClientRect();
  tip.style.left = Math.min(ev.clientX+14, innerWidth-r.width-12)+"px";
  tip.style.top  = Math.min(ev.clientY+14, innerHeight-r.height-12)+"px";
}
gNode.addEventListener("click", e=>{
  if(e.target.__k){ showTip(e, e.target.__k); e.stopPropagation(); }
});
document.addEventListener("click", ()=>{ tip.style.display="none"; });

/* ── 筛选 ── */
function apply(){
  const band = fb.value, tier = document.getElementById("f-tier").value,
        emode = document.getElementById("f-edge").value;
  let vis = 0;
  const on = {};
  for(const k in L.nodes){
    const n = L.nodes[k];
    let ok = true;
    if(band && n.band!==band) ok=false;
    if(tier==="_none" && n.tier) ok=false;
    else if(tier && tier!=="_none" && n.tier!==tier) ok=false;
    on[k]=ok; if(ok) vis++;
    nodeEls[k].classList.toggle("dim", !ok);
  }
  for(const e of edgeEls){
    const show = emode!=="none" && on[e.__a] && on[e.__b]
      && (emode==="all" || L.nodes[e.__b].indeg >= +emode);
    e.style.display = show ? "" : "none";
  }
  document.getElementById("cnt").textContent = `${vis} / ${L.stats.n} 篇`;
}
["f-band","f-tier","f-edge"].forEach(id=>
  document.getElementById(id).addEventListener("change", apply));
document.getElementById("f-reset").addEventListener("click", ()=>{
  fb.value=""; document.getElementById("f-tier").value="";
  document.getElementById("f-edge").value="none"; apply();
});
apply();
</script>
"""


def main():
    L = load_state("lib_layout.json", {})
    if not L:
        raise SystemExit("先跑 lib_layout.py")
    import datetime
    html = (HTML
            .replace("__BLOB__", json.dumps(L, ensure_ascii=False, separators=(",", ":")))
            .replace("__N__", str(L["stats"]["n"]))
            .replace("__E__", str(L["stats"]["e"]))
            .replace("__LANES__", str(L["stats"]["lanes"]))
            .replace("__DATE__", datetime.date.today().isoformat()))
    PAGE.write_text(html, encoding="utf-8")
    kb = PAGE.stat().st_size // 1024
    print(f"已生成 {PAGE}({kb} KB) 节点 {L['stats']['n']} 边 {L['stats']['e']}")


if __name__ == "__main__":
    main()
