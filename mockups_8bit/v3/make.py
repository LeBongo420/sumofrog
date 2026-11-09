from art import *
import random, math
logo=to_img(frog('victory',32))
for s in (32,64,512): logo.resize((s,s),Image.NEAREST).save(f'sumo_frog_{s}.png')
SPR={p:to_img(frog(p)) for p in ('up','down','victory')}
W,H=256,224

def sun(px,d,cx,cy,r):
    # yellow->orange->pink with ordered dither, navy stripe cuts in lower half
    for y in range(cy-r,cy+r+1):
        f=(y-(cy-r))/(2*r)
        for x in range(cx-r,cx+r+1):
            if (x-cx)**2+(y-cy)**2<=r*r:
                t=BAYER[y%4][x%4]/16
                if f<0.45: c=YEL if t>=(f/0.45)**2*0.6 else ORG
                elif f<0.7: c=ORG if t>=(f-0.45)/0.25 else MAG
                else: c=MAG if t>0.15 else PNK
                px[x,y]=PAL[c]
    k=0
    y=cy+2
    while y<cy+r:
        for x in range(cx-r,cx+r+1): 
            if px[x,y] in (PAL[YEL],PAL[ORG],PAL[MAG],PAL[PNK]): px[x,y]=PAL[NAV]
        k+=1; 
        for yy in range(y,y+k//2): 
            for x in range(cx-r,cx+r+1):
                if px[x,yy] in (PAL[YEL],PAL[ORG],PAL[MAG],PAL[PNK]): px[x,yy]=PAL[NAV]
        y+=7-min(k,4)
def palm(d,px,x,base,h,flip=1):
    # curved trunk
    for i in range(h):
        xx=x+int(flip*3*math.sin(i/h*1.6)); 
        d.line([(xx,base-i),(xx+2,base-i)],fill=PAL[ORG if i%3 else BG3])
        px[xx-1,base-i]=PAL[BLK]; px[xx+3,base-i]=PAL[BLK]
    tx=x+int(flip*3*math.sin(1.6)); ty=base-h
    for ang in (-160,-130,-100,-60,-30,-5,-80):
        a=math.radians(ang)
        for k in range(14):
            fx=tx+1+int(math.cos(a)*k); fy=ty+int(math.sin(a)*k*0.7+ (k*k)/30)
            for dy in (0,1):
                px[fx,fy+dy]=PAL[NEO if dy==0 else TEA]
            px[fx,fy+2]=PAL[BLK]
def background(px,d,y0=26,y1=134,hz=98):
    # navy sky with dithered band near horizon + stars
    for y in range(y0,hz):
        for x in range(W): px[x,y]=PAL[NAV]
    dgrad(px,0,hz-26,W,hz,NAV,PUR)
    random.seed(5)
    for _ in range(26):
        x,y=random.randrange(2,W-2),random.randrange(y0+2,hz-30); px[x,y]=PAL[WHT]
    for (x,y) in [(30,40),(220,36),(180,50)]:
        for dx,dy in((1,0),(-1,0),(0,1),(0,-1)): px[x+dx,y+dy]=PAL[GRY]
        px[x,y]=PAL[WHT]
    sun(px,d,128,66,26)
    # black city silhouette (right) and Mt Fuji silhouette (left), all black
    random.seed(11); x=150
    while x<W:
        w=random.randint(6,12); h=random.randint(10,34)
        d.rectangle([x,hz-h,x+w,hz],fill=PAL[BLK])
        if random.random()<.4: d.rectangle([x+w//2,hz-h-5,x+w//2,hz-h],fill=PAL[BLK])
        x+=w-1
    d.polygon([(0,hz),(0,hz-6),(46,64),(60,64),(118,hz)],fill=PAL[BLK])
    # snow line in grey dither so Fuji reads by brightness
    for y in range(64,72):
        for xx in range(30,80):
            if px[xx,y]==PAL[BLK] and (xx+y)%2==0 and y<70-abs(xx-53)//6: px[xx,y]=PAL[GRY]
    # neon horizon line
    d.line([(0,hz),(W,hz)],fill=PAL[MAG])
    # perspective grid floor on black
    d.rectangle([0,hz+1,W,y1-1],fill=PAL[BLK])
    vx=128
    for y in (hz+3,hz+7,hz+13,hz+21,hz+32):
        if y<y1: d.line([(0,y),(W,y)],fill=PAL[MAG])
    for k in range(-9,10):
        d.line([(vx+k*12,hz),(vx+k*60,y1+30)],fill=PAL[MAG])
    palm(d,px,14,y1-4,40,1); palm(d,px,236,y1-4,40,-1)
    palm(d,px,52,hz+6,20,1); palm(d,px,200,hz+6,20,-1)
def dohyo(px,d):
    d.polygon([(64,116),(192,116),(202,133),(54,133)],fill=PAL[BLK],outline=PAL[PNK])
    for x in range(64,189,8): d.line([(x,124),(x+4,124)],fill=PAL[PUR])
    d.ellipse([60,102,196,124],fill=PAL[PUR],outline=PAL[PNK])
    for y in range(104,123):
        for x in range(60,197):
            if px[x,y]==PAL[PUR] and (x+y)%2==0 and y>117: px[x,y]=PAL[NV2]
    d.ellipse([82,106,174,120],outline=PAL[WHT])
def rock(d,px,cx,y):
    d.polygon([(cx-7,y+6),(cx-5,y),(cx+4,y-1),(cx+7,y+6)],fill=PAL[GRY],outline=PAL[BLK])
    for p in [(cx-3,y+2),(cx+2,y+1),(cx,y+4)]: px[p]=PAL[YEL]
    px[cx-4,y+1]=PAL[WHT]
def burst(px,cx,cy,r,c):
    pts=set()
    for k in range(r+1): pts|={(k,0),(-k,0),(0,k),(0,-k)}
    for k in range(1,r-1): pts|={(k,-k),(-k,-k)}
    edge={(x+dx,y+dy) for x,y in pts for dx,dy in((1,0),(-1,0),(0,1),(0,-1))}-pts
    for x,y in edge: px[cx+x,cy+y]=PAL[BLK]
    for x,y in pts: px[cx+x,cy+y]=PAL[WHT] if abs(x)+abs(y)<=1 else PAL[c]
def coin(d,cx,cy):
    d.ellipse([cx-5,cy-5,cx+5,cy+5],fill=PAL[YEL],outline=PAL[BLK]); d.line([(cx+2,cy-3),(cx+2,cy+3)],fill=PAL[ORG])
    d.point([(cx-2,cy-2),(cx-3,cy-1)],fill=PAL[WHT])
# 7x7 icons: pickaxe (mining) and star (found)
PICK=["######.","######.","######.","..##...","..##...","..##...","..##..."]
STAR=["...#...","...#...","#######",".#####.","..###..",".##.##.","#.....#"]
def icon(px,x,y,pat,c):
    for j,row in enumerate(pat):
        for i,ch in enumerate(row):
            if ch=='#': px[x+i,y+j]=PAL[c]
def screen(pose,status,nonce,hs,found=False,fx=0):
    im=Image.new('RGB',(W,H),PAL[BLK]); px=im.load(); d=ImageDraw.Draw(im); d.fontmode='1'
    lg=to_img(logotype()); im.paste(lg,(4,5),lg)
    text(d,(56,4),'FROG MINER',WHT); text(d,(W-4-tw('V0.3'),4),'V0.3',GRY)
    text(d,(56,15),'TEST COINS/TEST CHAIN',PNK)
    background(px,d); dohyo(px,d); rock(d,px,128,113)
    sp=SPR[pose]; im.paste(sp,(112,77),sp)
    if fx==1:
        burst(px,109,113,4,YEL); burst(px,147,113,4,YEL); burst(px,101,105,2,WHT); burst(px,155,105,2,WHT)
    elif fx==2:
        burst(px,110,106,2,YEL); burst(px,146,106,2,YEL); burst(px,102,98,1,WHT); burst(px,154,98,1,WHT)
    if found:
        coin(d,176,52); text(d,(185,48),'+20',WHT,BLK)
        for p in [(98,70),(158,74),(92,90),(164,92)]: burst(px,p[0],p[1],2,YEL)
    # status box: different words, icon AND polarity
    if found:
        bw=tw(status)+28; bx=(W-bw)//2
        d.rectangle([bx-2,28,bx+bw+2,44],fill=PAL[BLK]); d.rectangle([bx,30,bx+bw,42],fill=PAL[WHT],outline=PAL[BLK])
        icon(px,bx+3,33,STAR,BLK); icon(px,bx+bw-9,33,STAR,BLK); text(d,(bx+14,33),status,BLK)
    else:
        bw=tw(status)+20; bx=(W-bw)//2
        d.rectangle([bx,30,bx+bw,42],fill=PAL[BLK],outline=PAL[WHT])
        icon(px,bx+4,33,PICK,WHT); text(d,(bx+14,33),status,WHT)
    # HUD: light text on deep navy
    d.rectangle([0,134,W-1,H-1],fill=PAL[NAV]); d.rectangle([1,135,W-2,H-2],outline=PAL[MAG])
    rows=[('BLOCK','#004,218' if found else '#004,217'),('HASH/S',hs),('NONCE',nonce),
          ('DIFF','18 BITS'),('REWARD','20 SUMO/BLK'),('MINED','4 BLOCKS' if found else '3 BLOCKS'),
          ('BALANCE','80 SUMO' if found else '60 SUMO')]
    y=139
    for k,v in rows:
        text(d,(8,y),k,GRY); text(d,(W-8-tw(v),y),v,YEL if k in('REWARD','BALANCE') else WHT); y+=10
    s='EXAMPLE DATA-MOCKUP ONLY'; text(d,((W-tw(s))//2,H-12),s,PNK)
    return im
# ---- CRT monitor frame (pixel exact) ----
MW,MH=304,312; SX,SY=24,20
def monitor(scr):
    im=Image.new('RGB',(MW,MH),PAL[NAV]); px=im.load(); d=ImageDraw.Draw(im)
    # desk
    d.rectangle([0,288,MW,MH],fill=PAL[PUR])
    # case body with bevel
    d.rectangle([2,2,MW-3,262],fill=PAL[BG1],outline=PAL[BLK])
    d.line([(3,3),(MW-4,3)],fill=PAL[WHT]); d.line([(3,3),(3,261)],fill=PAL[WHT])
    d.line([(4,261),(MW-4,261)],fill=PAL[BG3]); d.line([(MW-4,4),(MW-4,261)],fill=PAL[BG3])
    for y in range(250,261):
        for x in range(4,MW-4):
            if (x+y)%2==0: px[x,y]=PAL[BG2]
    # recessed screen surround
    d.rectangle([SX-8,SY-8,SX+W+7,SY+H+7],fill=PAL[BG2],outline=PAL[BG3])
    d.line([(SX-8,SY+H+7),(SX+W+7,SY+H+7)],fill=PAL[WHT]); d.line([(SX+W+7,SY-8),(SX+W+7,SY+H+7)],fill=PAL[WHT])
    d.rectangle([SX-3,SY-3,SX+W+2,SY+H+2],fill=PAL[BLK])
    # screen with stepped rounded corners (curved glass feel)
    im.paste(scr,(SX,SY))
    steps=[6,4,3,2,1,1]
    for i,s in enumerate(steps):
        for x in range(s):
            for (cx,cy) in ((SX+x,SY+i),(SX+W-1-x,SY+i),(SX+x,SY+H-1-i),(SX+W-1-x,SY+H-1-i)): px[cx,cy]=PAL[BLK]
    # dithered glint top-left
    for (gx,gy) in [(8,4),(10,4),(9,5),(7,5),(6,6),(8,6),(5,7)]: px[SX+gx+4,SY+gy]=PAL[WHT]
    # chin: badge, vents, power LED + label
    d.rectangle([20,250,98,258],fill=PAL[BG3]); 
    dd=ImageDraw.Draw(im); dd.fontmode='1'
    small=ImageFont.truetype(FONT.path,8)
    dd.text((22,251),'SUMOTRON',font=small,fill=PAL[BG1])
    for x in range(160,226,4): d.line([(x,251),(x,257)],fill=PAL[BG3])
    d.rectangle([258,251,264,257],fill=PAL[BLK]); d.rectangle([259,252,263,256],fill=PAL[NEO]); px[260,253]=PAL[WHT]
    d.rectangle([272,251,286,257],fill=PAL[BG3]); d.rectangle([273,252,285,256],fill=PAL[BG2])
    # stand + keyboard
    d.polygon([(118,263),(186,263),(196,272),(108,272)],fill=PAL[BG2],outline=PAL[BLK])
    d.rectangle([30,274,MW-31,300],fill=PAL[BG1],outline=PAL[BLK])
    d.line([(31,275),(MW-32,275)],fill=PAL[WHT])
    for row in range(3):
        for k in range(20):
            x=36+k*12+(row*3); y=278+row*7
            if x+9<MW-34: d.rectangle([x,y,x+9,y+5],fill=PAL[BG2],outline=PAL[BG3])
    d.rectangle([96,299-0,208,299],fill=PAL[BG3])
    return im
fr=[screen('up','MINING','8,472,113','1.24 MH/S'),
    screen('down','MINING.','8,472,114','1.25 MH/S',fx=1),
    screen('down','MINING..','8,472,115','1.23 MH/S',fx=2)]
fd=screen('victory','BLOCK FOUND!','8,472,116','1.24 MH/S',found=True)
Q=lambda im,s: quant(im).resize((im.width*s,im.height*s),Image.NEAREST)
Q(fr[1],4).save('mining_screen.png'); Q(fd,4).save('block_found.png')
mons=[Q(monitor(f),3) for f in fr]; mf=Q(monitor(fd),3)
mons[1].save('mining_screen_monitor.png'); mf.save('block_found_monitor.png')
seq=mons*3+[mf]
mons[0].save('miner_monitor.gif',save_all=True,append_images=seq[1:],duration=[300,140,260]*3+[1600],loop=0)

sc=[Q(f,4) for f in fr]; sd=Q(fd,4); sq=sc*3+[sd]
sc[0].save('miner.gif',save_all=True,append_images=sq[1:],duration=[300,140,260]*3+[1600],loop=0)
# ---- site header 320x72 ----
HW,HH=320,72
im=Image.new('RGB',(HW,HH),PAL[NAV]); px=im.load(); d=ImageDraw.Draw(im); d.fontmode='1'
dgrad(px,0,24,HW,40,NAV,PUR)
random.seed(2)
for _ in range(20): px[random.randrange(HW),random.randrange(1,30)]=PAL[WHT]
r=18; cx,cy=262,30
for y in range(cy-r,cy+r):
    for x in range(cx-r,cx+r):
        if (x-cx)**2+(y-cy)**2<=r*r: px[x,y]=PAL[YEL if y<cy-4 else (ORG if y<cy+4 else MAG)]
for y in (cy-2,cy+2,cy+5,cy+8): d.line([(cx-r,y),(cx+r,y)],fill=PAL[NAV])
random.seed(4); x=200
while x<HW:
    w=random.randint(5,10); h=random.randint(6,18); d.rectangle([x,40-h,x+w,40],fill=PAL[BLK]); x+=w-1
d.line([(0,40),(HW,40)],fill=PAL[MAG]); d.rectangle([0,41,HW,47],fill=PAL[BLK])
d.line([(0,43),(HW,43)],fill=PAL[MAG])
for k in range(-12,13): d.line([(160+k*14,40),(160+k*30,48)],fill=PAL[MAG])
im.paste(logo,(8,8),logo)
lg=to_img(logotype()); im.paste(lg,(46,6),lg)
d.rectangle([45,23,46+tw('THE FROG YOU MINE')+1,32],fill=PAL[BLK]); text(d,(46,24),'THE FROG YOU MINE',WHT)
d.rectangle([HW-146,5,HW-146+tw('TESTNET')+7,18],fill=PAL[WHT],outline=PAL[BLK]); text(d,(HW-142,9),'TESTNET',BLK)
d.rectangle([0,48,HW-1,59],fill=PAL[NAV])
x=8
for n in ('MINE','STATS','GUIDE','PAPER'):
    w=tw(n)+6; sel=n=='MINE'
    d.rectangle([x,49,x+w,58],fill=PAL[WHT] if sel else PAL[NAV],outline=PAL[WHT] if sel else PAL[GRY]); text(d,(x+4,50),n,BLK if sel else WHT); x+=w+6
d.rectangle([0,60,HW-1,HH-1],fill=PAL[BLK])
s='BLK #4,217*20 SUMO/BLK*EXAMPLE DATA'; text(d,((HW-tw(s))//2,62),s,WHT)
Q(im,3).save('site_header.png')
