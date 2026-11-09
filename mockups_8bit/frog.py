from PIL import Image
import math
# Sweetie-16 inspired limited palette
P = {
 'K':(26,28,44),    # outline near-black
 'D':(37,113,121),  # dark green / shade
 'G':(56,183,100),  # frog green
 'L':(167,240,112), # highlight
 'C':(255,205,117), # belly (warm cream/gold)
 'R':(177,62,83),   # mawashi red
 'r':(93,39,93),    # dark red/purple shade
 'W':(244,244,244), # white
 'Y':(255,205,117),
}
N=32
g=[['.' for _ in range(N)] for _ in range(N)]
def put(x,y,c):
    x=int(round(x)); y=int(round(y))
    if 0<=x<N and 0<=y<N: g[y][x]=c
def ell(cx,cy,rx,ry,c):
    for y in range(N):
        for x in range(N):
            if ((x-cx)/rx)**2+((y-cy)/ry)**2<=1.0: g[y][x]=c
def line(x0,y0,x1,y1,c,w=1):
    n=int(max(abs(x1-x0),abs(y1-y0))*2)+1
    for i in range(n+1):
        t=i/n; x=x0+(x1-x0)*t; y=y0+(y1-y0)*t
        for dx in range(w):
            for dy in range(w):
                put(x+dx,y+dy,c)
# arms (raised, triumphant like the scroll frog)
line(9,15,5,11,'G',2); line(5,11,4,6,'G',2)
line(22,15,26,11,'G',2); line(26,11,27,6,'G',2)
# hands: splayed fingers
for (x,y) in [(3,4),(5,4),(2,5),(4,3),(6,5)]: put(x,y,'G')
for (x,y) in [(28,4),(26,4),(29,5),(27,3),(25,5)]: put(x,y,'G')
# legs (wide shiko squat)
line(11,24,7,27,'G',3); line(7,27,6,29,'G',2)
line(20,24,24,27,'G',3); line(24,27,24,29,'G',2)
# body + head
ell(15.5,18.5,8.6,7.2,'G')
ell(15.5,9.5,8.2,4.6,'G')
# eyes bumps
ell(11,5.5,2.6,2.6,'G'); ell(20,5.5,2.6,2.6,'G')
# feet
for x in range(3,10): put(x,30,'G')
for x in range(22,29): put(x,30,'G')
# belly
ell(15.5,19.5,5.2,4.6,'C')
# mawashi belt
for y in (23,24):
    for x in range(N):
        if g[y][x] in 'GC': g[y][x]='R'
for y in (25,26,27):
    for x in (14,15,16,17): g[y][x]='R'
for x in (14,15,16,17): g[28][x]='r'
for x in range(N):
    if g[24][x]=='R': g[24][x]='r'
for x in (15,16): g[24][x]='R'
# outline pass
import copy
o=copy.deepcopy(g)
for y in range(N):
    for x in range(N):
        if g[y][x]=='.':
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                xx,yy=x+dx,y+dy
                if 0<=xx<N and 0<=yy<N and g[yy][xx] not in '.':
                    o[y][x]='K'; break
g=o
# shading: lowest green pixel in each column of body region -> dark
for y in range(N-1):
    for x in range(N):
        if g[y][x]=='G' and g[y+1][x]=='K' and y>8: g[y][x]='D'
# eyes (explicit sprite, pupils looking slightly up/in = triumphant)
EYE=[".KKKKK.","KWWWWWK","KWWKKWK","KWWKKWK","KGWWWGK"]
for ox,flip in ((7,False),(18,True)):
    for dy,row in enumerate(EYE):
        r=row[::-1] if flip else row
        for dx,c in enumerate(r):
            if c!='.': put(ox+dx,1+dy,c)
# mouth: big grin open
for x in range(10,22): put(x,11,'K')
put(9,10,'K'); put(22,10,'K')
for x in range(12,20): put(x,12,'r')
for x in range(12,20): put(x,13,'K')
put(11,12,'K'); put(20,12,'K')
# nostrils
put(14,8,'D'); put(17,8,'D')
# head highlight
for x in (12,13,14): put(x,7,'L')
put(8,16,'L'); put(9,15,'L')
# spots
for (x,y) in [(9,19),(10,22),(21,18),(22,21),(20,15),(10,16),(6,9),(25,9),(8,27),(23,27)]:
    if g[y][x] in 'G': g[y][x]='D'
img=Image.new('RGBA',(N,N),(0,0,0,0))
for y in range(N):
    for x in range(N):
        c=g[y][x]
        if c!='.': img.putpixel((x,y),P[c]+(255,))
img.save('sumo_frog_32.png')
img.resize((64,64),Image.NEAREST).save('sumo_frog_64.png')
img.resize((512,512),Image.NEAREST).save('sumo_frog_512.png')
print('\n'.join(''.join(r) for r in g))
