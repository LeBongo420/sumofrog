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
JFONT=ImageFont.truetype('/usr/share/fonts/truetype/sand-box/google/DotGothic16/DotGothic16-Regular.ttf',16)
def pagoda(d,px,cx,base,tiers=4):
    y=base; w=26
    d.rectangle([cx-10,base-6,cx+10,base],fill=PAL[BLK])
    for t in range(tiers):
        # flared roof
        d.polygon([(cx-w//2-3,y-6),(cx+w//2+3,y-6),(cx+w//2-1,y-9),(cx-w//2+1,y-9)],fill=PAL[BLK])
        px[cx-w//2-4,y-7]=PAL[BLK]; px[cx+w//2+4,y-7]=PAL[BLK]
        d.rectangle([cx-w//2+4,y-14,cx+w//2-4,y-9],fill=PAL[BLK])
        # glowing window (bright, reads in greyscale)
        d.rectangle([cx-1,y-13,cx+1,y-11],fill=PAL[YEL])
        y-=9; w-=4
    d.rectangle([cx,y-12,cx,y-6],fill=PAL[BLK])
    for k in range(3): d.line([(cx-1,y-8-k*2),(cx+1,y-8-k*2)],fill=PAL[BLK])
def torii(d,x,base,w,h,c):
    d.rectangle([x+3,base-h+4,x+4,base],fill=PAL[c]); d.rectangle([x+w-5,base-h+4,x+w-4,base],fill=PAL[c])
    d.rectangle([x,base-h,x+w,base-h+1],fill=PAL[c]); d.point([(x-1,base-h-1),(x+w+1,base-h-1)],fill=PAL[c])
    d.rectangle([x+1,base-h+4,x+w-1,base-h+4],fill=PAL[c]); d.rectangle([x+w//2,base-h+2,x+w//2,base-h+3],fill=PAL[c])
def lantern(d,px,cx,base):
    # toro: stone lantern, grey with lit yellow box
    d.rectangle([cx-4,base-2,cx+4,base],fill=PAL[GRY],outline=PAL[BLK])
    d.rectangle([cx-1,base-8,cx+1,base-2],fill=PAL[GRY])
    d.rectangle([cx-3,base-13,cx+3,base-8],fill=PAL[GRY],outline=PAL[BLK]); d.rectangle([cx-1,base-12,cx+1,base-9],fill=PAL[YEL])
    d.polygon([(cx-6,base-13),(cx+6,base-13),(cx+2,base-17),(cx-2,base-17)],fill=PAL[GRY],outline=PAL[BLK])
    px[cx,base-18]=PAL[GRY]
def sakura(d,px,cx,base,h,r,seed,lean=0):
    random.seed(seed)
    top=(cx+lean,base-h)
    # black trunk (tapered) + branches
    d.polygon([(cx-3,base),(cx+3,base),(top[0]+1,top[1]),(top[0]-1,top[1])],fill=PAL[BLK])
    for ang in (-160,-125,-55,-20):
        a=math.radians(ang); d.line([top,(top[0]+int(math.cos(a)*r),top[1]+int(math.sin(a)*r*0.5))],fill=PAL[BLK],width=2)
    # blossom clusters (pink, dithered magenta underside, white highlights)
    for _ in range(14):
        bx=top[0]+random.randint(-r,r); by=top[1]+random.randint(-r//2,r//5)
        rr=random.randint(3,6)
        for y in range(by-rr,by+rr+1):
            for x in range(bx-rr,bx+rr+1):
                if (x-bx)**2+(y-by)**2<=rr*rr and 0<=x<px_w[0] and 0<=y<px_w[1]:
                    px[x,y]=PAL[MAG] if (y>by+rr//2 and (x+y)%2) else PAL[PNK]
    for _ in range(22):
        x=top[0]+random.randint(-r,r); y=top[1]+random.randint(-r//2,0)
        if 0<=x<px_w[0] and 0<=y<px_w[1] and px[x,y]==PAL[PNK]: px[x,y]=PAL[WHT]
px_w=[256,224]
def petals(px,frame,n=14,area=(0,26,256,134),seed=9):
    random.seed(seed)
    for i in range(n):
        x0=random.randrange(area[0],area[2]); y0=random.randrange(area[1],area[3])
        x=(x0+frame*3)%(area[2]-area[0])+area[0]; y=(y0+frame*4-area[1])%(area[3]-area[1])+area[1]
        for dx,dy,c in ((0,0,PNK),(1,0,WHT),(0,1,MAG)):
            if area[0]<=x+dx<area[2] and area[1]<=y+dy<area[3]: px[x+dx,y+dy]=PAL[c]
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
    # castle-ish hill line + pagoda + neon kanji sign on right, torii on left
    d.polygon([(150,hz),(170,hz-6),(240,hz-8),(W,hz-4),(W,hz)],fill=PAL[BLK])
    pagoda(d,px,186,hz-2)
    d.rectangle([212,48,231,87],fill=PAL[BLK],outline=PAL[PNK]); d.rectangle([213,49,230,86],outline=PAL[MAG])
    d.text((214,46),'相',font=JFONT,fill=PAL[WHT]); d.text((214,65),'撲',font=JFONT,fill=PAL[WHT])
    d.rectangle([221,88,222,hz],fill=PAL[BLK])
    torii(d,52,hz-1,24,22,MAG)
    sakura(d,px,16,y1-1,36,18,1,lean=2); sakura(d,px,242,y1-1,36,18,2,lean=-2)
    lantern(d,px,46,y1-6); lantern(d,px,210,y1-6)
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
def screen(pose,status,guess,hs,found=False,fx=0,frame=0):
    im=Image.new('RGB',(W,H),PAL[BLK]); px=im.load(); d=ImageDraw.Draw(im); d.fontmode='1'
    lg=to_img(logotype()); im.paste(lg,(4,5),lg)
    text(d,(56,4),'FROG MINER',WHT); text(d,(W-4-tw('V0.4'),4),'V0.4',GRY)
    text(d,(56,15),'TEST COINS/TEST CHAIN',PNK)
    background(px,d); petals(px,frame); dohyo(px,d); rock(d,px,128,113)
    sp=SPR[pose]; im.paste(sp,(112,77),sp)
    if fx==1:
        burst(px,109,113,4,YEL); burst(px,147,113,4,YEL); burst(px,101,105,2,WHT); burst(px,155,105,2,WHT)
    elif fx==2:
        burst(px,110,106,2,YEL); burst(px,146,106,2,YEL); burst(px,102,98,1,WHT); burst(px,154,98,1,WHT)
    if found:
        coin(d,66,52); text(d,(75,48),'+20',WHT,BLK)
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
    rows=[('BLOCK','#004,218' if found else '#004,217'),('HASH/S',hs),('GUESS #',guess),
          ('DIFF','18 BITS'),('REWARD','20 SUMO/BLK'),('MINED','4 BLOCKS' if found else '3 BLOCKS'),
          ('BALANCE','80 SUMO' if found else '60 SUMO')]
    y=139
    for k,v in rows:
        text(d,(8,y),k,GRY); text(d,(W-8-tw(v),y),v,YEL if k in('REWARD','BALANCE') else WHT); y+=10
    s='EXAMPLE DATA-MOCKUP ONLY'; text(d,((W-tw(s))//2,H-12),s,PNK)
    return im
fr=[screen('up','MINING... GUESS #8,472,113','8,472,113','1.24 MH/S',frame=0),
    screen('down','MINING... GUESS #8,472,114','8,472,114','1.25 MH/S',fx=1,frame=1),
    screen('down','MINING... GUESS #8,472,115','8,472,115','1.23 MH/S',fx=2,frame=2)]
fd=screen('victory','BLOCK FOUND!','8,472,116','1.24 MH/S',found=True,frame=3)
Q=lambda im,s: quant(im).resize((im.width*s,im.height*s),Image.NEAREST)
Q(fr[1],4).save('mining_screen.png'); Q(fd,4).save('block_found.png')

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
px_w[0],px_w[1]=HW,HH
d.polygon([(190,40),(205,35),(300,33),(HW,36),(HW,40)],fill=PAL[BLK])
pagoda(d,px,226,39,3)
torii(d,190,39,18,16,MAG)
sakura(d,px,304,47,26,13,3,lean=-1)
d.line([(0,40),(HW,40)],fill=PAL[MAG]); d.rectangle([0,41,HW,47],fill=PAL[BLK])
d.line([(0,43),(HW,43)],fill=PAL[MAG])
for k in range(-12,13): d.line([(160+k*14,40),(160+k*30,48)],fill=PAL[MAG])
im.paste(logo,(8,8),logo)
lg=to_img(logotype()); im.paste(lg,(46,6),lg)
d.rectangle([45,23,46+tw('THE FROG YOU MINE')+1,32],fill=PAL[BLK]); text(d,(46,24),'THE FROG YOU MINE',WHT)
d.rectangle([0,48,HW-1,59],fill=PAL[NAV])
d.rectangle([HW-tw('TESTNET')-16,48,HW-4,59],fill=PAL[WHT]); text(d,(HW-tw('TESTNET')-10,50),'TESTNET',BLK)
x=8
for n in ('MINE','STATS','GUIDE','PAPER'):
    w=tw(n)+6; sel=n=='MINE'
    d.rectangle([x,49,x+w,58],fill=PAL[WHT] if sel else PAL[NAV],outline=PAL[WHT] if sel else PAL[GRY]); text(d,(x+4,50),n,BLK if sel else WHT); x+=w+6
d.rectangle([0,60,HW-1,HH-1],fill=PAL[BLK])
s='BLK #4,217*20 SUMO/BLK*EXAMPLE DATA'; text(d,((HW-tw(s))//2,62),s,WHT)
Q(im,3).save('site_header.png')
