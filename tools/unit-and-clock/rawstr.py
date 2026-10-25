import sys,re
img,outp=sys.argv[1],sys.argv[2]
f=open(img,'rb'); out=open(outp,'w')
a16=re.compile(rb'(?:[\x20-\x7e]\x00){5,}'); a8=re.compile(rb'[\x20-\x7e]{6,}')
for start,end in [(1,888833),(29925377,30949377)]:
    pos=start*512; endb=end*512; CH=32<<20
    while pos<endb:
        f.seek(pos); d=f.read(min(CH,endb-pos))
        for m in a16.finditer(d): out.write('%010x U %s\n'%(pos+m.start(),m.group().decode('utf-16le')))
        for m in a8.finditer(d): out.write('%010x A %s\n'%(pos+m.start(),m.group().decode()))
        pos+=CH
