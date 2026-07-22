#!/usr/bin/env python3
"""桑葚式统一布局(子泳道版):模块化按子类拆平行细流,每细流宽度∝时段论文数。
城区模块化→感知/建图/预测规划;越野模块化→感知可通行/融合/导航规划/其他 + 越野数据集单列。
越野子类取自 Zotero「非结构化场景」目录真值(node.col),城区按标题关键词。"""
import json, re, math, unicodedata
from collections import defaultdict
from pathlib import Path
import networkx as nx
SP = Path(__file__).resolve().parent / "state"
C = json.load(open(SP / "layout_corpus.json", encoding="utf-8"))
E = [tuple(e) for e in json.load(open(SP / "edges.json", encoding="utf-8"))]

def _nt(x): return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", x or "").lower().split(":")[0])
CUT = 2015*12          # 时间轴聚焦深度学习时代(2015+);少数古早理论根(最优传输1958/Isomap2000等)只作背景不进河流
_noise = {"cider","read","end to end object detection with transformers","exploring the limits of transfer learning","representing scenes as neural radiance fields for view synthesis","language models are unsupervised multitask learners","improving language understanding by generative pre training","the llama 3 herd of models","decoupled weight decay regularization"}
_bad = {k for k,n in C.items() if n.get("name","")==k or _nt(n["title"]) in _noise}
def _istop(n): return n["track"]=="shared" or n["para"]=="foundation" or (n["para"]=="dataset" and n["track"]!="offroad")
C = {k:n for k,n in C.items() if k not in _bad and (_istop(n) or n["month"]>=CUT)}
E = [(a,b) for a,b in E if a in C and b in C]

# ---------- 子类划分 ----------
COL2SUB = {
 "基于图像分割":"感知可通行","基于点云分割":"感知可通行","基于分割的方法":"感知可通行",
 "基于分类的方法":"感知可通行","可通行性分析":"感知可通行",
 "前融合":"融合","后融合":"融合",
 "车辆自主导航":"导航规划","机器人导航":"导航规划","轨迹预测":"导航规划",
 "数据集":"数据集",
 "综述":"其他","世界模型":"其他","最优传输理论":"其他","空天协同":"其他","零样本":"其他","非结构化场景":"其他",
}
def off_sub(n):
    col = n.get("col","")
    if col in COL2SUB: return COL2SUB[col]
    t = n["title"].lower()               # 无 col 的越野祖先按关键词
    if any(k in t for k in ("dataset","benchmark","rellis","orfd","rugd","goose")): return "数据集"
    if any(k in t for k in ("fusion","multimodal","multi-modal","multi modal")): return "融合"
    if any(k in t for k in ("navigat","planning","wayfast","badgr","goal","waypoint","path")): return "导航规划"
    if any(k in t for k in ("segment","terrain","traversab","road","detect","classif","perception","semantic")): return "感知可通行"
    return "其他"
def urban_mod_sub(n):
    t = n["title"].lower()
    if "map" in t or "vectormap" in t: return "建图"
    if any(k in t for k in ("predict","trajectory","multipath","vip3d","anchor","planning","safety","interpretable","interact")): return "预测规划"
    return "感知"                        # bev/detr/lift-splat/fusion/occupancy/raycast

def sub_of(n):
    if n["para"] == "e2e": return "端到端"
    if n["track"] == "offroad":
        return off_sub(n)                 # 含"数据集"
    if n["track"] == "urban" and n["para"] == "modular":
        return urban_mod_sub(n)
    return None
def para_eff(n, sub):
    return "dataset" if sub == "数据集" else n["para"]

def is_top(n):
    return n["track"] == "shared" or n["para"] == "foundation" or (n["para"] == "dataset" and n["track"] != "offroad")

# ---------- 子泳道定义(顺序=左→右;宽度 px) ----------
LANES_ORD = [
 ("urban","modular","感知",150,"感知"),
 ("urban","modular","建图",100,"建图"),
 ("urban","modular","预测规划",128,"预测·规划"),
 ("urban","e2e","端到端",188,"端到端"),
 ("offroad","modular","感知可通行",232,"感知·可通行"),
 ("offroad","modular","融合",150,"融合"),
 ("offroad","modular","导航规划",178,"导航·规划"),
 ("offroad","dataset","数据集",118,"数据集"),
 ("offroad","modular","其他",150,"其他"),
 ("offroad","e2e","端到端",188,"端到端"),
]
MARGIN, GAP, REGION_GAP = 26, 14, 56
# 累计算 x
lanes = {}   # (track,para,sub) -> {x0,x1,label,col,para}
PARA_COL = {"foundation":"#b49bff","modular":"#6aa6ff","e2e":"#46d7cc","dataset":"#f0bf4c"}
x = MARGIN; prev_track = None; split_x = None
for tr,pa,sub,w,lab in LANES_ORD:
    if prev_track is not None and tr != prev_track:
        split_x = x + REGION_GAP/2 - GAP/2; x += REGION_GAP
    lanes[(tr,pa,sub)] = {"x0":round(x,1),"x1":round(x+w,1),"label":lab,"col":PARA_COL[pa],"para":pa}
    x += w + GAP; prev_track = tr
W = round(x - GAP + 84)          # 右侧多留白,免得最右泳道标签顶出画布
SPLIT = round(split_x,1)

def lane_key(n):
    sub = sub_of(n)
    if sub is None: return None
    pe = para_eff(n, sub)
    key = (n["track"], pe, sub)
    return key if key in lanes else None

G = nx.DiGraph(); G.add_nodes_from(C); G.add_edges_from(E)
Gd = nx.DiGraph(); Gd.add_nodes_from(C); Gd.add_edges_from(E)
while not nx.is_directed_acyclic_graph(Gd):
    _c = nx.find_cycle(Gd); Gd.remove_edge(*_c[-1][:2])
_TR = nx.transitive_reduction(Gd)
indeg = {k: G.in_degree(k) for k in C}
pr = nx.pagerank(G) if G.number_of_edges() else {k:0 for k in C}
prmax = max(pr.values()) or 1

# ---------- 顶部带 ----------
top = [k for k,n in C.items() if is_top(n)]
top.sort(key=lambda k:(C[k]["para"]!="foundation", -indeg[k]))
per = 9
TOP_H = 60 + ((len(top)+per-1)//per)*66 + 28
topPos = {}
for i,k in enumerate(top):
    r=i//per; c=i%per; nrow=min(per,len(top)-r*per)
    xx=W/2+(c-(nrow-1)/2)*((W-140)/per)
    topPos[k]={"x":round(xx,1),"y":round(52+r*66,1)}

# ---------- 时间轴 ----------
stream = [k for k in C if lane_key(C[k])]
m0 = min(C[k]["month"] for k in stream); m1 = max(C[k]["month"] for k in stream)
SCALE = 2280/(m1-m0)
def yof(m): return round(TOP_H+40+(m-m0)*SCALE,1)

# ---------- 节点坐标:先按当月密度放簇(列数随密度增长,不超泳道宽)----------
nodes={}
bylane=defaultdict(lambda:defaultdict(list))
for k in stream: bylane[lane_key(C[k])][C[k]["month"]].append(k)
def rad(k): return 5+(indeg[k]**0.5)*2.6
def emit(k,x,y,sub):
    n=C[k]; pe=para_eff(n,sub)
    nodes[k]={"x":round(x,1),"y":round(y,1),"r":round(rad(k),1),"name":n["name"],"title":n["title"],
        "para":pe,"track":n["track"],"sub":sub,"year":n.get("year",""),"indeg":indeg[k],
        "pr":round(pr[k]/prmax,3),"col":PARA_COL[pe],"src":n["src"]}
XG=46; YG=34
nodexy=defaultdict(list)                       # lanekey -> [(y,x,r)]
for key,ln in lanes.items():
    cx=(ln["x0"]+ln["x1"])/2; laneHW=(ln["x1"]-ln["x0"])/2-6
    maxcols=max(1,int((laneHW*2)//XG))
    for m,ks in bylane[key].items():
        ks.sort(key=lambda k:-indeg[k])
        n=len(ks); cols=min(maxcols,max(1,round((n*1.4)**0.5))); rows=math.ceil(n/cols)
        for i,k in enumerate(ks):
            row=i//cols; col=i%cols; ncol=min(cols,n-row*cols)
            xx=cx+(col-(ncol-1)/2)*XG
            yy=yof(m)+(row-(rows-1)/2)*YG
            emit(k,xx,yy,key[2]); r=nodes[k]["r"]
            nodexy[key].append((yy,xx,r))
            nodes[k]["ldy"]=-(r+5) if (col%2==0) else (r+14)
            nodes[k]["showl"]=(indeg[k]>=1 or n<=6)

# ---------- 河流:包络真实节点簇(保证节点落在河内、宽度随密度)----------
BINm=2                                          # 每 2 个月采样一次
WINpx=3.4*SCALE                                 # ±3.4 月窗口取包络
ribbons={}
for key,ln in lanes.items():
    cx=(ln["x0"]+ln["x1"])/2; halfmax=(ln["x1"]-ln["x0"])/2-4
    pn=nodexy[key]
    pts=[]
    for bm in range(m0, m1+BINm+1, BINm):
        ys=yof(bm)
        e=max((abs(xx-cx)+r for (yy,xx,r) in pn if abs(yy-ys)<=WINpx), default=0)
        hw=min(halfmax, e+7) if e>0 else 6
        pts.append({"y":round(ys,1),"hw":round(hw,1)})
    ribbons["|".join(key)]={"cx":round(cx,1),"pts":pts}
for k in top:
    n=C[k]
    nodes[k]={"x":topPos[k]["x"],"y":topPos[k]["y"],"r":round(rad(k),1),"name":n["name"],"title":n["title"],
        "para":n["para"],"track":"shared","sub":"基石","year":n.get("year",""),"indeg":indeg[k],
        "pr":round(pr[k]/prmax,3),"col":PARA_COL[n["para"]],"src":n["src"],"showl":True}

# 年份刻度
ticks=[]; seen=set()
for k in stream:
    yr=C[k]["month"]//12
    if yr not in seen: seen.add(yr); ticks.append({"year":yr,"y":yof(yr*12)})
ticks.sort(key=lambda t:t["y"])
H=yof(m1)+70
# 区间(城区/越野)范围,供画区标题
u=[ln for key,ln in lanes.items() if key[0]=="urban"]; o=[ln for key,ln in lanes.items() if key[0]=="offroad"]
regions=[{"label":"◀ 城区 / 结构化","x0":min(l["x0"] for l in u),"x1":max(l["x1"] for l in u),"col":"#6aa6ff","anchor":"start"},
         {"label":"非结构化 / 越野 ▶","x0":min(l["x0"] for l in o),"x1":max(l["x1"] for l in o),"col":"#9bce6b","anchor":"end"}]
out={"W":W,"H":round(H),"split":SPLIT,"top_h":TOP_H,
     "nodes":nodes,"edges":[[a,b] for a,b in E if a in nodes and b in nodes],
     "edges_tr":[[a,b] for a,b in _TR.edges() if a in nodes and b in nodes],
     "ribbons":ribbons,"ticks":ticks,"regions":regions,
     "lanes":{("|".join(k)):v for k,v in lanes.items()},
     "stats":{"n":len(nodes),"edges":len(E),
              "urban":sum(1 for n in C.values() if n["track"]=="urban"),
              "offroad":sum(1 for n in C.values() if n["track"]=="offroad"),
              "foundation":sum(1 for n in C.values() if n["para"]=="foundation"),
              "modular":sum(1 for k,n in C.items() if lane_key(n) and lane_key(n)[1]=="modular"),
              "e2e":sum(1 for n in C.values() if n["para"]=="e2e")}}
json.dump(out,open(SP/"layout.json","w",encoding="utf-8"),ensure_ascii=False,separators=(",",":"))
print(f"节点 {len(nodes)} 边 {len(out['edges'])}(主干 {len(out['edges_tr'])}) 画布 {W}x{int(H)} split={SPLIT}")
# 各子泳道节点数
from collections import Counter
lc=Counter("|".join(lane_key(C[k])) for k in stream)
for key in lanes: print(f"  {'|'.join(key):28} {lc.get('|'.join(key),0):3}")
print("入度Top:",[(nodes[k]['name'],indeg[k]) for k in sorted(nodes,key=lambda k:-indeg[k])[:6]])
