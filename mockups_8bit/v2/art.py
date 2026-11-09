from PIL import Image, ImageDraw, ImageFont
# PICO-8 16-colour palette (only these colours are ever used)
PAL=[(0,0,0),(29,43,83),(126,37,83),(0,135,81),(171,82,54),(95,87,79),(194,195,199),(255,241,232),
     (255,0,77),(255,163,0),(255,236,39),(0,228,54),(41,173,255),(131,118,156),(255,119,168),(255,204,170)]
BLK,DBL,DPU,DGR,BRN,DGY,LGY,WHT,RED,ORG,YEL,GRN,BLU,LAV,PNK,PCH=range(16)
FONT=ImageFont.truetype('/usr/share/fonts/truetype/sand-box/google/Press Start 2P/PressStart2P-Regular.ttf',8)
CH={'g':GRN,'d':DGR,'b':PCH,'r':RED,'p':DPU,'w':WHT,'k':BLK,'m':BRN,'h':PCH,'s':DGY}

BODY=[".wwww........wwww.",
      ".wwkkggggggggkkww.",
      "gwwkkggggggggkkwwg",
      "gggggggggggggggggg",
      "ggggggdggggdgggggg",
      "gkggggggggggggggkg",
      "ggkkkkkkkkkkkkkkgg",
      "gggkppppppppppkggg",
      "ggggkkkkkkkkkkgggg",
      "ggggggbbbbbbgggggg",
      "gggggbbbbbbbbbbggggg",
      "ggdggbbbbbbbbbbggdgg",
      "ggggbbbbbbbbbbbbgggg",
      "gdggbbbbbbbbbbbbggdg",
      "dgggbbbbbbbbbbbbgdgd",
      "gdgdgbbbbbbbbbbgdgdg",
      "rrrrrrrrrrrrrrrrrrrr",
      "pppppppprrrrpppppppp",
      "gggggggg.rrrr.gggggggg",
      "gdgggg...rrrr...ggggdg",
      "dgdgd....pppp....dgdgd",
      "gdgd................dgdg",
      "dddddd..............dddddd"]
def blank(w,h): return [[None]*w for _ in range(h)]
def outline(g):
    h=len(g); w=len(g[0]); o=[r[:] for r in g]
    for y in range(h):
        for x in range(w):
            if g[y][x] is None and any(0<=x+dx<w and 0<=y+dy<h and g[y+dy][x+dx] is not None for dx,dy in((1,0),(-1,0),(0,1),(0,-1))):
                o[y][x]=BLK
    return o
def put(g,x,y,c):
    if 0<=y<len(g) and 0<=x<len(g[0]): g[y][x]=c
def line(g,pts,c,w=2):
    for (x0,y0),(x1,y1) in zip(pts,pts[1:]):
        n=max(abs(x1-x0),abs(y1-y0))*2+1
        for i in range(n+1):
            t=i/n; x=round(x0+(x1-x0)*t); y=round(y0+(y1-y0)*t)
            for a in range(w):
                for b in range(w): put(g,x+a,y+b,c)
def comp(base,top):
    for y,row in enumerate(top):
        for x,c in enumerate(row):
            if c is not None: base[y][x]=c
    return base
def frog(pose,H=40):
    W=32; oy=H-25
    b=blank(W,H)
    for i,row in enumerate(BODY):
        sx=16-len(row)//2
        for j,c in enumerate(row):
            if c!='.': b[oy+i][sx+j]=CH[c]
    b=outline(b)
    a=blank(W,H); sy=oy+10  # shoulder row
    if pose=='victory':
        line(a,[(5,sy),(3,sy-6),(3,sy-12)],GRN); line(a,[(25,sy),(27,sy-6),(27,sy-12)],GRN)
        for x,y in [(2,sy-13),(5,sy-13),(3,sy-14)]: put(a,x,y,GRN)
        for x,y in [(29,sy-13),(26,sy-13),(28,sy-14)]: put(a,x,y,GRN)
    elif pose=='up':
        line(a,[(5,sy),(3,sy-7),(8,sy-14),(14,sy-16)],GRN); line(a,[(25,sy),(27,sy-7),(22,sy-14),(16,sy-16)],GRN)
        m=blank(W,H)
        for y in range(sy-20,sy-16): put(m,15,y,BRN); put(m,16,y,BRN)
        for y in range(sy-24,sy-20):
            for x in range(9,23): put(m,x,y,BRN if y>sy-24 else PCH)
        for y in range(sy-24,sy-20): put(m,11,y,DGY); put(m,20,y,DGY)
        a=comp(outline(m),a)
    elif pose=='down':
        line(a,[(5,sy),(8,sy+3),(14,sy+3)],GRN); line(a,[(25,sy),(22,sy+3),(16,sy+3)],GRN)
        m=blank(W,H)
        for y in range(sy+4,sy+9): put(m,15,y,BRN); put(m,16,y,BRN)
        for y in range(sy+9,sy+13):
            for x in range(9,23): put(m,x,y,BRN if y>sy+9 else PCH)
        for y in range(sy+9,sy+13): put(m,11,y,DGY); put(m,20,y,DGY)
        a=comp(outline(m),a)
    a=outline(a)
    return comp(b,a)
def to_img(g):
    im=Image.new('RGBA',(len(g[0]),len(g)),(0,0,0,0))
    for y,r in enumerate(g):
        for x,c in enumerate(r):
            if c is not None: im.putpixel((x,y),PAL[c]+(255,))
    return im
# chunky logotype letters (3px strokes)
LET={'S':[".#######.","#########","###...###","###......","########.",".########","......###","###...###","#########",".#######."],
'U':["###...###"]*8+["#########",".#######."],
'M':["##.....##","###...###","####.####","#########","###.#.###"]+["###...###"]*5,
'O':[".#######.","#########"]+["###...###"]*6+["#########",".#######."]}
def logotype(word='SUMO'):
    w=len(word)*11; g=blank(w+4,14)
    for i,ch in enumerate(word):
        for y,row in enumerate(LET[ch]):
            for x,c in enumerate(row):
                if c=='#': g[y+1][1+i*11+x]=YEL if y<5 else ORG
    g=outline(g)
    sh=blank(w+4,14)  # drop shadow
    for y in range(13):
        for x in range(w+3):
            if g[y][x] is not None: sh[y+1][x+1]=DPU
    return comp(sh,g)
BAYER=[[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]]
def dgrad(px,x0,y0,x1,y1,c1,c2):
    for y in range(y0,y1):
        f=(y-y0)/max(1,(y1-y0))
        for x in range(x0,x1):
            px[x,y]=PAL[c2] if BAYER[y%4][x%4]/16<f else PAL[c1]
def text(d,xy,s,c,shadow=None):
    if shadow is not None: d.text((xy[0]+1,xy[1]+1),s,font=FONT,fill=PAL[shadow])
    d.text(xy,s,font=FONT,fill=PAL[c])
def tw(s): return int(FONT.getlength(s))
def quant(im):
    p=Image.new('P',(1,1)); p.putpalette(sum(PAL,())+(0,)*(768-48))
    return im.convert('RGB').quantize(palette=p,dither=Image.Dither.NONE)
