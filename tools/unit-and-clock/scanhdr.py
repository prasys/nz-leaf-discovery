import sys,re
img=sys.argv[1]
f=open(img,'rb')
for start,end in [(1,888833),(29925377,30949377)]:
    pos=start*512; endb=end*512; CH=64<<20
    while pos<endb:
        f.seek(pos); d=f.read(min(CH+64,endb-pos))
        for m in re.finditer(rb'SUM4|ECEC|NKOK|NCG2K2|CLARION ID|\.066\x00|470-\d{4}-\d\d',d):
            if m.start()<CH or pos+CH>=endb:
                a=pos+m.start(); ctx=d[max(0,m.start()-0x20):m.start()+0x30]
                print('%010x sec%d %s %s'%(a,a//512,m.group(),ctx.replace(b'\x00',b'.').replace(b'\xff',b'~')[:90]))
        pos+=CH
