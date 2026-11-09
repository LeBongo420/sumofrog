from art import *
import random
# ---- logo ----
logo=to_img(frog('victory',32))
for s in (32,64,512): quant(logo).convert('RGBA').resize((s,s),Image.NEAREST) and None
def save_logo():
    a=logo; alpha=a.split()[3]
    for s in (32,64,512):
        a.resize((s,s),Image.NEAREST).save(f'sumo_frog_{s}.png')
save_logo()
SPR={p:to_img(frog(p)) for p in ('up','down','victory')}
W,H=256,224; S=4
def background(px,d):
    # sunset sky, ordered-dither bands
    dgrad(px,0,26,W,50,DBL,DPU); dgrad(px,0,50,W,74,DPU,PNK); dgrad(px,0,74,W,98,PNK,ORG)
    # striped sun
    d.ellipse([174,58,214,98],fill=PAL[YEL])
    for i,y in enumerate((82,87,91,94,97)): 
        for x in range(170,219):
            if px[x,y]==PAL[YEL]: px[x,y]=PAL[ORG] if i<2 else PAL[PNK]
    random.seed(3)
    for _ in range(18):
        x,y=random.randrange(W),random.randrange(27,46); px[x,y]=PAL[WHT]
    # mt fuji
    d.polygon([(30,100),(78,60),(92,60),(140,100)],fill=PAL[LAV])
    d.polygon([(70,67),(78,60),(92,60),(100,67),(94,70),(88,66),(82,71),(76,66)],fill=PAL[WHT])
    # far hills (dark purple), near hills dark green w/ dither
    for x in range(W):
        import math
        h1=int(96+6*math.sin(x/19)+3*math.sin(x/7))
        for y in range(h1,104): px[x,y]=PAL[DBL]
        h2=int(100+4*math.sin(x/23+1))
        for y in range(h2,112): px[x,y]=PAL[DGR] if (y>h2+1 or (x+y)%2) else PAL[GRN]
    # torii gate on left hill
    for x,y0 in ((20,84),(32,84)): d.rectangle([x,y0,x+1,99],fill=PAL[RED])
    d.rectangle([16,82,37,83],fill=PAL[RED]); d.rectangle([18,87,35,87],fill=PAL[RED]); d.point([(15,81),(38,81)],fill=PAL[RED])
    # pine trees right
    for tx in (232,242):
        d.polygon([(tx,88),(tx-5,100),(tx+5,100)],fill=PAL[DGR]); d.rectangle([tx,100,tx,103],fill=PAL[BRN])
    # ground
    dgrad(px,0,110,W,134,BRN,DGY)
    # dohyo: front face + clay top + rope ring
    d.polygon([(64,116),(192,116),(202,133),(54,133)],fill=PAL[BRN])
    for x in range(64,189,8): d.line([(x,121),(x+4,121)],fill=PAL[PCH])
    d.line([(58,126),(198,126)],fill=PAL[DPU])
    d.ellipse([60,102,196,124],fill=PAL[PCH],outline=PAL[BLK])
    for y in range(104,123):
        for x in range(60,197):
            if px[x,y]==PAL[PCH] and (x+y)%2==0 and y>117: px[x,y]=PAL[ORG]
    d.ellipse([82,106,174,120],outline=PAL[WHT]); d.ellipse([83,107,173,119],outline=PAL[LGY])
def rock(d,px,cx,y):
    d.polygon([(cx-7,y+6),(cx-5,y),(cx+4,y-1),(cx+7,y+6)],fill=PAL[DGY],outline=PAL[BLK])
    for p in [(cx-3,y+2),(cx+2,y+1),(cx,y+4)]: px[p]=PAL[YEL]
    px[cx-4,y+1]=PAL[LGY]
def coin(d,cx,cy):
    d.ellipse([cx-4,cy-4,cx+4,cy+4],fill=PAL[YEL],outline=PAL[BLK]); d.line([(cx+2,cy-2),(cx+2,cy+2)],fill=PAL[ORG])
    d.point([(cx-2,cy-2)],fill=PAL[WHT])
def spark(px,cx,cy,r,c):
    for dx,dy in [(1,0),(-1,0),(0,-1),(1,-1),(-1,-1),(1,1),(-1,1)]:
        for k in range(r,r+3):
            px[cx+dx*k,cy+dy*k]=PAL[c]
def burst(px,cx,cy,r,c):
    pts=set()
    for k in range(r+1):
        pts|={(k,0),(-k,0),(0,k),(0,-k)}
    for k in range(1,r):
        pts|={(k,-k),(-k,-k)} if k<r-1 else set()
    edge={(x+dx,y+dy) for x,y in pts for dx,dy in((1,0),(-1,0),(0,1),(0,-1))}-pts
    for x,y in edge: px[cx+x,cy+y]=PAL[BLK]
    for x,y in pts: px[cx+x,cy+y]=PAL[WHT] if abs(x)+abs(y)<=1 else PAL[c]
def star(px,cx,cy,c):
    for dx,dy in [(0,0),(1,0),(-1,0),(0,1),(0,-1),(2,0),(-2,0),(0,2),(0,-2)]:
        px[cx+dx,cy+dy]=PAL[WHT] if (dx,dy)==(0,0) else PAL[c]
def screen(pose,status,nonce,hs,found=False,fx=0):
    im=Image.new('RGB',(W,H),PAL[BLK]); px=im.load(); d=ImageDraw.Draw(im); d.fontmode='1'
    # top bar
    lg=to_img(logotype()); im.paste(lg,(4,5),lg)
    text(d,(56,4),'FROG MINER',WHT); text(d,(W-4-tw('V0.2'),4),'V0.2',LAV)
    text(d,(56,15),'TEST COINS/TEST CHAIN',PNK)
    background(px,d)
    rock(d,px,128,113)
    sp=SPR[pose]; im.paste(sp,(112,77),sp)
    if pose=='down' and fx:
        (burst(px,109,113,4,YEL),burst(px,147,113,4,YEL),burst(px,101,105,2,ORG),burst(px,155,105,2,ORG)) if fx==1 else (burst(px,110,106,2,YEL),burst(px,146,106,2,YEL),burst(px,102,98,1,WHT),burst(px,154,98,1,WHT))
    if found:
        coin(d,128,64); text(d,(146,58),'+20',YEL,BLK)
        for p in [(100,70),(156,74),(96,92),(160,94)]: star(px,p[0],p[1],YEL)
    # status box
    bw=tw(status)+8; bx=(W-bw)//2
    d.rectangle([bx,30,bx+bw,42],fill=PAL[YEL if found else BLK],outline=PAL[ORG if found else WHT])
    text(d,(bx+5,33),status,BLK if found else WHT)
    # HUD panel
    d.rectangle([0,134,W-1,H-1],fill=PAL[DBL]); d.rectangle([1,135,W-2,H-2],outline=PAL[BLU])
    rows=[('BLOCK','#004,218' if found else '#004,217',WHT),('HASH/S',hs,BLU),('NONCE',nonce,LGY),
          ('DIFF','18 BITS',WHT),('REWARD','20 SUMO/BLK',YEL),('MINED','4 BLOCKS' if found else '3 BLOCKS',GRN),
          ('BALANCE','80 SUMO' if found else '60 SUMO',YEL)]
    y=139
    for k,v,c in rows:
        text(d,(8,y),k,LAV); text(d,(W-8-tw(v),y),v,c); y+=10
    s='EXAMPLE DATA-MOCKUP ONLY'; text(d,((W-tw(s))//2,H-12),s,ORG)
    return quant(im)
fr=[screen('up','MINING.','8,472,113','1.24 MH/S'),
    screen('down','MINING..','8,472,114','1.25 MH/S',fx=1),
    screen('down','MINING...','8,472,115','1.23 MH/S',fx=2)]
big=[f.resize((W*S,H*S),Image.NEAREST) for f in fr]
big[1].save('mining_screen.png')
big[0].save('mining_loop.gif',save_all=True,append_images=big[1:],duration=[300,140,260],loop=0)
fd=screen('victory','BLOCK FOUND!','8,472,116','1.24 MH/S',found=True)
fdb=fd.resize((W*S,H*S),Image.NEAREST); fdb.save('mining_screen_block_found.png')
big[0].save('mining_with_found.gif',save_all=True,append_images=big[1:]+big+[fdb],duration=[300,140,260,300,140,260,1400],loop=0)
# ---- site header 320x72 ----
HW,HH=320,72
im=Image.new('RGB',(HW,HH),PAL[BLK]); px=im.load(); d=ImageDraw.Draw(im); d.fontmode='1'
dgrad(px,0,0,HW,24,DBL,DPU); dgrad(px,0,24,HW,48,DPU,PNK)
d.ellipse([250,22,282,54],fill=PAL[YEL])
import math
for x in range(HW):
    h=int(40+3*math.sin(x/17)+2*math.sin(x/6))
    for y in range(h,48): px[x,y]=PAL[DGR] if (y>h+1 or (x+y)%2) else PAL[GRN]
im.paste(logo,(8,8),logo)
lg=to_img(logotype()); im.paste(lg,(46,6),lg)
text(d,(46,24),'THE FROG YOU MINE',WHT,BLK)
d.rectangle([HW-66,6,HW-6,18],fill=PAL[RED],outline=PAL[BLK]); text(d,(HW-62,9),'TESTNET',WHT)
d.rectangle([0,48,HW-1,59],fill=PAL[DBL])
x=8
for n in ('MINE','STATS','GUIDE','PAPER'):
    w=tw(n)+6; d.rectangle([x,49,x+w,58],fill=PAL[BLU] if n=='MINE' else PAL[DBL],outline=PAL[BLU]); text(d,(x+4,50),n,WHT if n=='MINE' else LGY); x+=w+6
d.rectangle([0,60,HW-1,HH-1],fill=PAL[BLK])
s='BLK #4,217*20 SUMO/BLK*EXAMPLE DATA'; text(d,((HW-tw(s))//2,62),s,GRN)
quant(im).resize((HW*3,HH*3),Image.NEAREST).save('site_header.png')
