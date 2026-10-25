import struct,sys
f=open(sys.argv[1],'rb')
def rd(lba,n=1): f.seek(lba*512); return f.read(512*n)
def parts(sec):
    out=[]
    for i in range(4):
        e=sec[446+16*i:462+16*i]
        st,typ,lba,cnt=e[0],e[4],*struct.unpack('<II',e[8:16])
        out.append((st,typ,lba,cnt,e.hex()))
    return out
m=rd(0); print('sig',m[510:512].hex(),'disksig',m[440:446].hex())
for p in parts(m): print('MBR',p)
ext=[p for p in parts(m) if p[1] in (5,0xf,0x85)]
if ext:
    base=ext[0][2]; cur=base
    while True:
        s=rd(cur); print('EBR@',cur,'sig',s[510:].hex())
        ps=parts(s)
        for p in ps: print('  ',p)
        if ps[0][1]: print('  -> logical start abs',cur+ps[0][2],'end',cur+ps[0][2]+ps[0][3]-1)
        if ps[1][1]==0: break
        cur=base+ps[1][2]
