import sys,re
img=sys.argv[1]; a=int(sys.argv[2],16); before=int(sys.argv[3]); after=int(sys.argv[4])
f=open(img,'rb'); f.seek(a-before); d=f.read(before+after)
base=a-before
for par in (0,1):
  pass
# find utf16 runs of printable (incl CJK) chars, aligned to a's parity
par=a%2
out=[]
i=(par-base)%2
cur=[];start=None
while i+1<len(d):
    c=d[i]|(d[i+1]<<8); ch=chr(c)
    ok = (0x20<=c<0x7f) or (0x3000<=c<0x9fff) or (0xff00<=c<0xffef) or c in (0xd7,0xb0,0x2192)
    if ok:
        if start is None: start=i
        cur.append(ch)
    else:
        if len(cur)>=2: out.append((base+start,''.join(cur)))
        cur=[];start=None
    i+=2
for o,s in out: print('%010x %s'%(o,s))
