#!/usr/bin/env python3
# 生成「两朵乌云」(梯度消失 vs 梯度爆炸) 动画 GIF
from PIL import Image, ImageDraw, ImageFont

W, H = 760, 390
FRAMES = 44
DUR_MS = 86            # 每帧时长 → 总时长 ≈ 3.8s
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

def font(sz): return ImageFont.truetype(FONT, sz)
f_title = font(21); f_sub = font(15); f_res = font(14); f_badge = font(14)

# 颜色
C_DIV=(43,79,144); C_RUNG=(34,52,104)
L_TITLE=(111,182,255); L_SUB=(127,192,255); L_RES=(156,203,255)
R_TITLE=(255,142,126); R_SUB=(255,155,139); R_RES=(255,171,157)
ORB_V=((227,242,255),(80,150,255))   # vanishing: core, glow
ORB_E=((255,231,219),(255,110,80))   # exploding
BADGE_BG=(12,24,52); BADGE_LN=(43,79,144); BADGE_TX=(220,233,255); GOLD=(255,207,106)

LX, RX, DIV = 190, 570, 380          # 左/右半中心、分隔线 x
PT, PB = 70, 360                     # orb 垂直区间

# ---- 背景：竖直渐变（近似面板的径向深蓝） ----
def lerp(a,b,t): return tuple(int(a[i]+(b[i]-a[i])*t) for i in range(3))
top,mid,bot=(22,48,106),(12,26,60),(8,18,37)
bg = Image.new("RGB",(W,H))
bd = ImageDraw.Draw(bg)
for y in range(H):
    t=y/(H-1)
    c = lerp(top,mid,t*2) if t<0.5 else lerp(mid,bot,(t-0.5)*2)
    bd.line([(0,y),(W,y)], fill=c)

def make_orb(d, core, glow, ascale):
    d=max(2,int(round(d)))
    im=Image.new("RGBA",(d,d),(0,0,0,0)); dr=ImageDraw.Draw(im); R=d/2
    r=int(R)
    while r>0:
        t=r/R
        alpha=int(255*((1-t)**1.8)*ascale)
        col=lerp(core,glow,t)
        dr.ellipse([R-r,R-r,R+r,R+r], fill=col+(alpha,))
        r-=1
    return im

def interp(stops,p):
    if p<=stops[0][0]: return stops[0][1]
    if p>=stops[-1][0]: return stops[-1][1]
    for i in range(1,len(stops)):
        if p<=stops[i][0]:
            p0,v0=stops[i-1]; p1,v1=stops[i]; f=(p-p0)/(p1-p0)
            return v0+(v1-v0)*f
    return stops[-1][1]

VAN_TOP=[(0,.20),(.86,.80),(1,.84)]; VAN_SZ=[(0,70),(.86,5),(1,3)]; VAN_OP=[(0,0),(.12,1),(.86,.55),(1,0)]
EXP_TOP=[(0,.20),(.72,.72),(1,.82)]; EXP_SZ=[(0,14),(.72,120),(1,250)]; EXP_OP=[(0,0),(.12,1),(.72,1),(1,0)]

def ctext(d,xy,s,fnt,fill): d.text(xy,s,font=fnt,fill=fill,anchor="mm")

frames=[]
for k in range(FRAMES):
    p=k/FRAMES
    fr=bg.copy(); d=ImageDraw.Draw(fr,"RGBA")
    # 分隔线
    d.line([(DIV,46),(DIV,344)], fill=C_DIV, width=1)
    # 阶梯（每半 6 根，示意"层"）
    for cx in (LX,RX):
        for yy in (118,156,194,232,270,308):
            d.rounded_rectangle([cx-44,yy-3,cx+44,yy+3], radius=3, fill=C_RUNG)
    # 标题/因子
    ctext(d,(LX,28),"第一朵乌云 · 梯度消失",f_title,L_TITLE)
    ctext(d,(LX,56),"每经一层  × 0.7",f_sub,L_SUB)
    ctext(d,(RX,28),"第二朵乌云 · 梯度爆炸",f_title,R_TITLE)
    ctext(d,(RX,56),"每经一层  × 1.5",f_sub,R_SUB)
    # orbs
    vcy=PT+interp(VAN_TOP,p)*(PB-PT); vsz=interp(VAN_SZ,p); vop=interp(VAN_OP,p)
    if vop>0.01:
        orb=make_orb(vsz,*ORB_V,vop); fr.paste(orb,(int(LX-orb.width/2),int(vcy-orb.height/2)),orb)
    ecy=PT+interp(EXP_TOP,p)*(PB-PT); esz=interp(EXP_SZ,p); eop=interp(EXP_OP,p)
    if eop>0.01:
        orb=make_orb(esz,*ORB_E,eop); fr.paste(orb,(int(RX-orb.width/2),int(ecy-orb.height/2)),orb)
    d=ImageDraw.Draw(fr,"RGBA")
    # 结果文字
    ctext(d,(LX,332),"逐层相乘 → 0 · 浅层学不动",f_res,L_RES)
    ctext(d,(RX,332),"逐层相乘 → ∞ · 数值溢出 NaN",f_res,R_RES)
    # 底部 badge
    s1="同源：梯度 = 逐层因子的 "; s2="连乘 ∏"; s3=" — <1 消失，>1 爆炸，唯 ≈1 才稳"
    w1=d.textlength(s1,font=f_badge); w2=d.textlength(s2,font=f_badge); w3=d.textlength(s3,font=f_badge)
    tot=w1+w2+w3; bx=W/2-tot/2; by=370
    d.rounded_rectangle([W/2-tot/2-14, by-13, W/2+tot/2+14, by+13], radius=13, fill=BADGE_BG, outline=BADGE_LN, width=1)
    d.text((bx,by),s1,font=f_badge,fill=BADGE_TX,anchor="lm")
    d.text((bx+w1,by),s2,font=f_badge,fill=GOLD,anchor="lm")
    d.text((bx+w1+w2,by),s3,font=f_badge,fill=BADGE_TX,anchor="lm")
    frames.append(fr.convert("P",palette=Image.ADAPTIVE,colors=256))

out="/Users/zhaozhihua/Desktop/colab/Technology/two-clouds.gif"
frames[0].save(out,save_all=True,append_images=frames[1:],duration=DUR_MS,loop=0,optimize=True,disposal=2)
print("saved",out,"frames",len(frames))
