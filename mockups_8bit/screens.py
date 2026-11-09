from PIL import Image, ImageDraw, ImageFont
FONT='/usr/share/fonts/truetype/sand-box/google/Press Start 2P/PressStart2P-Regular.ttf'
def F(s): return ImageFont.truetype(FONT,s)
K=(26,28,44); NAVY=(41,54,111); BLUE=(59,93,201); CYAN=(115,239,247)
G=(56,183,100); LG=(167,240,112); Y=(255,205,117); OR=(239,125,87)
R=(177,62,83); W=(244,244,244); GR=(148,176,194); DG=(86,108,134); PUR=(93,39,93)
frog=Image.open('sumo_frog_32.png')

def txt(d,xy,s,c,size=8,shadow=K):
    f=F(size)
    if shadow: d.text((xy[0]+1,xy[1]+1),s,font=f,fill=shadow)
    d.text(xy,s,font=f,fill=c)
def tw(s,size=8): return int(F(size).getlength(s))

def scanlines(img,scale):
    px=img.load(); w,h=img.size
    for y in range(0,h,scale):
        yy=y+scale-1
        for x in range(w):
            r,g,b=px[x,yy][:3]; px[x,yy]=(int(r*.78),int(g*.78),int(b*.78))
    return img

def mining(status, found, out):
    Wd,Ht=320,240
    im=Image.new('RGB',(Wd,Ht),K); d=ImageDraw.Draw(im); d.fontmode='1'
    # stars
    import random; random.seed(7)
    for _ in range(40): d.point((random.randrange(Wd),random.randrange(Ht)),fill=DG)
    # outer frame
    d.rectangle([2,2,Wd-3,Ht-3],outline=BLUE,width=2); d.rectangle([5,5,Wd-6,Ht-6],outline=NAVY)
    # title
    t='SUMO'; x=(Wd-tw(t,24))//2
    txt(d,(x+2,12+2),t,PUR,24,None); txt(d,(x,12),t,Y,24,OR)
    s='~ FROG MINER v0.1 ~'; txt(d,((Wd-tw(s))//2,42),s,CYAN)
    # test chain banner
    d.rectangle([10,54,Wd-11,66],fill=R)
    s='TEST COINS * TEST CHAIN * NO VALUE'; txt(d,((Wd-tw(s))//2,57),s,W)
    # frog on dohyo
    d.rectangle([12,72,108,170],fill=NAVY,outline=BLUE)
    d.ellipse([18,146,102,164],fill=(120,84,60),outline=Y)
    im.paste(frog.resize((64,64),Image.NEAREST),(28,82),frog.resize((64,64),Image.NEAREST))
    if found:
        for (sx,sy) in [(22,80),(96,84),(18,120),(100,124),(60,74)]:
            d.line([sx-2,sy,sx+2,sy],fill=Y); d.line([sx,sy-2,sx,sy+2],fill=Y)
    # stats panel
    d.rectangle([116,72,Wd-12,170],fill=NAVY,outline=BLUE)
    rows=[('BLOCK','#004,218' if found else '#004,217',W),
          ('HASH/S','1.24 MH/S',CYAN),
          ('DIFF','18 BITS',W),
          ('REWARD','50 SUMO/BLK',Y),
          ('MINED','4 BLOCKS' if found else '3 BLOCKS',LG),
          ('BALANCE','200 SUMO' if found else '150 SUMO',Y),
          ('HALVING','205,783 BLKS',GR)]
    y=80
    for k,v,c in rows:
        txt(d,(124,y),k,GR); txt(d,(Wd-20-tw(v),y),v,c); y+=12
    # hash progress bar
    d.rectangle([12,180,Wd-13,192],outline=BLUE,fill=K)
    fill=Wd-15 if found else 12+int((Wd-26)*0.62)
    for xx in range(14,fill,4): d.rectangle([xx,182,xx+2,190],fill=Y if found else G)
    # status line
    d.rectangle([12,198,Wd-13,214],fill=(Y if found else K),outline=(OR if found else LG))
    txt(d,((Wd-tw(status))//2,203),status,(K if found else LG),8,(OR if found else None))
    # footer
    s='EXAMPLE DATA - MOCKUP ONLY'; txt(d,((Wd-tw(s))//2,220),s,OR)
    big=im.resize((Wd*4,Ht*4),Image.NEAREST)
    scanlines(big,4).save(out)

mining('> MINING... TRY #8,472,113','',None) if False else None
mining('MINING...  NONCE 8,472,113',False,'mining_screen_mining.png')
mining('*** BLOCK FOUND! +50 SUMO ***',True,'mining_screen_block_found.png')

# website / stats header
Wd,Ht=480,96
im=Image.new('RGB',(Wd,Ht),K); d=ImageDraw.Draw(im); d.fontmode='1'
d.rectangle([0,0,Wd-1,Ht-1],outline=BLUE,width=2)
im.paste(frog.resize((64,64),Image.NEAREST),(10,8),frog.resize((64,64),Image.NEAREST))
txt(d,(84+2,14+2),'SUMO',PUR,24,None); txt(d,(84,14),'SUMO',Y,24,OR)
txt(d,(84,44),'THE FROG YOU MINE',CYAN)
nav=['MINE','STATS','GUIDE','PAPER']; x=Wd-12
for n in reversed(nav):
    w=tw(n)+10; x-=w
    d.rectangle([x,14,x+w-4,28],fill=NAVY,outline=BLUE); txt(d,(x+3,18),n,W); x-=4
d.rectangle([2,76,Wd-3,Ht-3],fill=NAVY)
s='BLOCK #4,217 * 50 SUMO/BLK * TEST CHAIN * EXAMPLE DATA'
txt(d,((Wd-tw(s))//2,82),s,LG)
d.rectangle([Wd-118,44,Wd-12,60],fill=R); txt(d,(Wd-112,49),'TESTNET',W); d.ellipse([Wd-26,48,Wd-18,56],fill=LG)
big=im.resize((Wd*3,Ht*3),Image.NEAREST); scanlines(big,3).save('site_header.png')
