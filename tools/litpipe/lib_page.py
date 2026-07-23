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
.viewport{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:10px;
  background:#0a0e14;height:78vh;}
.viewport:fullscreen{height:100vh;border-radius:0;}
svg{display:block;width:100%;height:100%;cursor:grab;}
.skedge{fill:none;stroke-width:1;}
.sknode{cursor:pointer;}
.skl{font:10px "SF Mono",Menlo,monospace;fill:var(--muted);pointer-events:none;}
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
      <option value="tr">主干（传递约简）</option>
      <option value="all">全部</option>
      <option value="none">隐藏</option>
    </select>
    <label><input type="checkbox" id="ck-rib" checked> 显示范式河流</label>
    <button id="ck-full">⛶ 全屏</button>
    <button id="f-reset">重置</button>
    <span class="grow"></span><span class="cnt" id="cnt"></span>
  </div>
  <div class="legend" id="legend"></div>
  <div class="viewport" id="vp"><svg id="svg"></svg></div>
  <p class="note"><b>悬停一个节点</b>会把它的全部上游（被它引用的思想来源，蓝）与下游（引用它的后续工作，绿）点亮，其余淡出——这是看清一条思想脉络的主要方式。
  滚轮朝光标缩放 / 拖拽平移 / 双击复位。红环粗细＝PageRank，河流宽度＝该时段该方向的产出强度。
  2015 年之前的论文压在顶部窄带里（否则 1958–2014 会拉出一大片空白）。</p>
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

/* ── 画图(沿用自驾页的视觉语言:河流色带 / PageRank 红环 / 悬停溯源 / 缩放平移)── */
const NS="http://www.w3.org/2000/svg";
const el=(t,a={})=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const svg=document.getElementById("svg");
svg.setAttribute("viewBox",`0 0 ${L.W} ${L.H}`);
svg.setAttribute("preserveAspectRatio","xMidYMin meet");

/* 河流用竖向渐变填充,顶部浓、底部淡 */
const defs=el("defs");
const RIBID={};
L.bands.forEach((b,i)=>{
  const id="grad"+i, c=b.col;
  const g=el("linearGradient",{id,x1:"0",y1:"0",x2:"0",y2:"1"});
  g.appendChild(el("stop",{offset:"0","stop-color":c,"stop-opacity":".20"}));
  g.appendChild(el("stop",{offset:"1","stop-color":c,"stop-opacity":".02"}));
  defs.appendChild(g); RIBID[b.name]="url(#"+id+")";
});
svg.appendChild(defs);

const vp=el("g"); svg.appendChild(vp);
const ribLayer=el("g"), laneLayer=el("g"), eLayer=el("g"), nLayer=el("g"), lblLayer=el("g");
vp.append(ribLayer,laneLayer,eLayer,nLayer,lblLayer);

/* ── 缩放 / 平移(朝光标缩放,双击复位)── */
let _tx=0,_ty=0,_k=1;
const _apply=()=>vp.setAttribute("transform",`translate(${_tx.toFixed(1)} ${_ty.toFixed(1)}) scale(${_k.toFixed(3)})`);
function _pt(e){const r=svg.getBoundingClientRect();return{x:(e.clientX-r.left)*L.W/r.width,y:(e.clientY-r.top)*L.H/r.height};}
svg.addEventListener("wheel",e=>{e.preventDefault();const p=_pt(e),f=e.deltaY<0?1.12:1/1.12;
  const nk=Math.min(9,Math.max(0.3,_k*f));_tx=p.x-(p.x-_tx)*(nk/_k);_ty=p.y-(p.y-_ty)*(nk/_k);_k=nk;_apply();},{passive:false});
let _drag=null;
svg.addEventListener("mousedown",e=>{if(e.target.closest(".sknode"))return;
  _drag={x:e.clientX,y:e.clientY,tx:_tx,ty:_ty};svg.style.cursor="grabbing";});
addEventListener("mousemove",e=>{if(!_drag)return;const r=svg.getBoundingClientRect();
  _tx=_drag.tx+(e.clientX-_drag.x)*L.W/r.width;_ty=_drag.ty+(e.clientY-_drag.y)*L.H/r.height;_apply();});
addEventListener("mouseup",()=>{if(_drag){_drag=null;svg.style.cursor="";}});
svg.addEventListener("dblclick",()=>{_tx=0;_ty=0;_k=1;_apply();});

/* ── 河流色带(平滑三次样条,宽度∝该时段产出)── */
function _sm(pts){let d="";for(let i=0;i<pts.length-1;i++){
  const p0=pts[i-1]||pts[i],p1=pts[i],p2=pts[i+1],p3=pts[i+2]||p2;
  d+=` C ${(p1.x+(p2.x-p0.x)/6).toFixed(1)} ${(p1.y+(p2.y-p0.y)/6).toFixed(1)}, `
   + `${(p2.x-(p3.x-p1.x)/6).toFixed(1)} ${(p2.y-(p3.y-p1.y)/6).toFixed(1)}, `
   + `${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;}return d;}
for(const lid in L.ribbons){
  const r=L.ribbons[lid], band=L.lanes[lid].band;
  const Lf=r.pts.map(q=>({x:r.cx-q.hw,y:q.y})), Rg=r.pts.map(q=>({x:r.cx+q.hw,y:q.y})).reverse();
  ribLayer.appendChild(el("path",{d:`M ${Lf[0].x} ${Lf[0].y}`+_sm(Lf)+` L ${Rg[0].x} ${Rg[0].y}`+_sm(Rg)+" Z",
    fill:RIBID[band]||"rgba(150,150,150,.05)",stroke:"none"}));
}

/* ── 第一层横带 + 泳道分隔虚线 + 标签 ── */
laneLayer.appendChild(el("rect",{x:0,y:0,width:L.W,height:L.topH-14,fill:"rgba(180,155,255,.05)"}));
const th=el("text",{x:16,y:26,fill:"#b49bff","font-family":"var(--mono)","font-size":"12.5","letter-spacing":"1.5"});
th.textContent=`第一层 · 公用基石（${L.stats.found} 篇，全库共用）`; lblLayer.appendChild(th);
for(const lid in L.lanes){
  const ln=L.lanes[lid], top=ln.band==="0 公用基石";
  const y0=top?56:L.topH+16, y1=top?L.topH-20:L.H-10;
  laneLayer.appendChild(el("line",{x1:ln.x0-5,y1:y0,x2:ln.x0-5,y2:y1,stroke:ln.col,
    "stroke-width":"1","stroke-dasharray":"2 8",opacity:".18"}));
  const t=el("text",{x:(ln.x0+ln.x1)/2,y:top?72:L.topH+30,"text-anchor":"middle",fill:ln.col,
    "font-family":"var(--mono)","font-size":"11.5"});
  t.textContent=`${ln.label}（${ln.n}）`; lblLayer.appendChild(t);
}
/* 领域大标题 */
let seen=new Set();
for(const lid in L.lanes){const ln=L.lanes[lid];
  if(ln.band==="0 公用基石"||seen.has(ln.band))continue; seen.add(ln.band);
  const t=el("text",{x:ln.x0,y:L.topH+8,fill:ln.col,"font-family":"var(--mono)","font-size":"13.5",
    "font-weight":"600","letter-spacing":"1"});
  t.textContent=ln.band; lblLayer.appendChild(t);}
/* 年份刻度 */
for(const t of L.ticks){
  laneLayer.appendChild(el("line",{x1:0,y1:t.y,x2:L.W,y2:t.y,stroke:"var(--line)",
    "stroke-width":"1","stroke-dasharray":"3 6",opacity:".45"}));
  const lb=el("text",{x:10,y:t.y-4,fill:"#5c6675","font-family":"var(--mono)","font-size":"11"});
  lb.textContent=t.year; lblLayer.appendChild(lb);}
const tOld=el("text",{x:10,y:L.topH+66,fill:"#5c6675","font-family":"var(--mono)","font-size":"11"});
tOld.textContent=`${Math.floor(L.m0/12)}–${L.cut/12-1}（压缩）`; lblLayer.appendChild(tOld);

/* ── 边 + 上下游邻接表 ── */
const up={},dn={}; for(const k in L.nodes){up[k]=[];dn[k]=[];}
const eEls=[];
for(const [a,b] of L.edges){
  const A=L.nodes[a],B=L.nodes[b]; if(!A||!B)continue;
  up[a].push(b); dn[b].push(a);
  const my=(A.y+B.y)/2;
  const p=el("path",{class:"skedge",d:`M${A.x} ${A.y} C ${A.x} ${my}, ${B.x} ${my}, ${B.x} ${B.y}`,
    stroke:"var(--line)",opacity:"0"});
  p.__a=a; p.__b=b; eLayer.appendChild(p); eEls.push(p);
}
const trSet=new Set((L.edges_tr||[]).map(e=>e[0]+">"+e[1]));
function reach(s,adj){const seen=new Set(),st=[s];
  while(st.length){const x=st.pop();for(const y of adj[x]||[])if(!seen.has(y)){seen.add(y);st.push(y);}}
  return seen;}

/* ── 节点:PageRank 红环 + 本体 + 高被引才挂标签 ── */
const nEls={};
for(const k in L.nodes){
  const n=L.nodes[k];
  const g=el("g",{class:"sknode"}); g.__k=k;
  if(n.pr>0.05) g.appendChild(el("circle",{cx:n.x,cy:n.y,r:n.r+2.6,fill:"none",stroke:"#d4694a",
    "stroke-width":(0.5+n.pr*5.5).toFixed(2),"stroke-opacity":(0.3+n.pr*0.7).toFixed(2)}));
  g.appendChild(el("circle",{class:"skc",cx:n.x,cy:n.y,r:n.r,fill:n.col,"fill-opacity":".78",
    stroke:"var(--bg)","stroke-width":"1.4"}));
  if(n.indeg>=22){   // 1183 个点全挂标签会糊成一片,只标真正的枢纽
    const t=el("text",{class:"skl",x:n.x,y:n.y-n.r-4,"text-anchor":"middle"});
    t.textContent=(n.zh||n.t).slice(0,16); g.appendChild(t);
  }
  nLayer.appendChild(g); nEls[k]=g;
}

/* ── 悬停溯源:上游染蓝、下游染绿,其余淡出 ── */
const tip=document.getElementById("tip");
let eMode="tr";
function edgeVis(){for(const p of eEls){
  const on=(eMode==="all")||(eMode==="tr"&&trSet.has(p.__a+">"+p.__b));
  p.setAttribute("opacity",on?"0.16":"0"); p.setAttribute("stroke","var(--line)");}}
function clr(){for(const k in nEls){nEls[k].style.opacity="";
  nEls[k].querySelector(".skc").setAttribute("stroke","var(--bg)");} edgeVis();}
for(const k in nEls){
  const g=nEls[k], n=L.nodes[k];
  g.addEventListener("mouseenter",()=>{
    const anc=reach(k,up),des=reach(k,dn),keep=new Set([k,...anc,...des]);
    for(const j in nEls) nEls[j].style.opacity=keep.has(j)?"1":"0.1";
    g.querySelector(".skc").setAttribute("stroke","var(--ink)");
    for(const p of eEls){
      const on=(p.__a===k&&keep.has(p.__b))||(p.__b===k&&keep.has(p.__a));
      p.setAttribute("opacity",on?"0.8":"0.02");
      p.setAttribute("stroke",p.__a===k?"#6aa6ff":p.__b===k?"#8fd67a":"var(--line)");}
    const ax=n.ax?` · <a href="https://arxiv.org/abs/${n.ax}" target="_blank" rel="noopener">arXiv ${n.ax} ↗</a>`:"";
    tip.innerHTML=`<div class="tt">${n.tier?`<span class="tier t${n.tier}">${n.tier}</span>`:""}${n.t}</div>`
      +(n.zh?`<div class="zh">${n.zh}</div>`:"")
      +`<div class="mt">${n.y4} · ${n.venue||"预印本"}${n.ccf?` · CCF-${n.ccf}`:""}</div>`
      +`<div class="mt">${n.band} / ${n.leaf}</div>`
      +`<div class="mt">库内被引 <b>${n.indeg}</b> · 全局 <b>${n.cc}</b> · PageRank <b>${n.pr}</b>`
      +` · 上游 ${anc.size} / 下游 ${des.size}${ax}</div>`;
    tip.style.display="block";});
  g.addEventListener("mousemove",e=>{
    tip.style.left=Math.min(e.clientX+14,innerWidth-420)+"px";
    tip.style.top=Math.min(e.clientY+14,innerHeight-tip.offsetHeight-12)+"px";});
  g.addEventListener("mouseleave",()=>{clr();tip.style.display="none";});
}

/* ── 筛选 ── */
function apply(){
  const band=fb.value, tier=document.getElementById("f-tier").value;
  eMode=document.getElementById("f-edge").value;
  let vis=0;
  for(const k in L.nodes){
    const n=L.nodes[k]; let ok=true;
    if(band&&n.band!==band) ok=false;
    if(tier==="_none"&&n.tier) ok=false;
    else if(tier&&tier!=="_none"&&n.tier!==tier) ok=false;
    if(ok)vis++;
    nEls[k].style.display=ok?"":"none";
  }
  edgeVis();
  document.getElementById("cnt").textContent=`${vis} / ${L.stats.n} 篇`;
}
["f-band","f-tier","f-edge"].forEach(id=>
  document.getElementById(id).addEventListener("change",apply));
document.getElementById("f-reset").addEventListener("click",()=>{
  fb.value="";document.getElementById("f-tier").value="";
  document.getElementById("f-edge").value="tr";_tx=0;_ty=0;_k=1;_apply();apply();});
document.getElementById("ck-rib").addEventListener("change",e=>{
  ribLayer.style.display=e.target.checked?"":"none";});
document.getElementById("ck-full").addEventListener("click",()=>{
  const vpEl=document.getElementById("vp");
  if(!document.fullscreenElement) vpEl.requestFullscreen&&vpEl.requestFullscreen();
  else document.exitFullscreen&&document.exitFullscreen();});
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
