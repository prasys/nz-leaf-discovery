import sys,glob,collections
fs=sorted(glob.glob(sys.argv[1]+'/clip*_02040102.bin'))[:300]
d=b''.join(open(f,'rb').read() for f in fs)
n=len(d); print('bytes',n)
res=[]
for lag in range(1,400):
    m=sum(1 for i in range(0,min(n-lag,400000)) if d[i]==d[i+lag])
    res.append((m/min(n-lag,400000),lag))
res.sort(reverse=True); print(res[:15])
# bit-level: duration estimate: sizes
import os
sz=[os.path.getsize(f) for f in glob.glob(sys.argv[1]+'/clip*_02040102.bin')]
print('n',len(sz),'total',sum(sz),'min',min(sz),'max',max(sz))
