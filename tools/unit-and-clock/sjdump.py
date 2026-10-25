import sys,re
img=sys.argv[1]; a=int(sys.argv[2],16); n=int(sys.argv[3],16)
f=open(img,'rb'); f.seek(a); d=f.read(n)
# split on NULs, decode each run as shift_jis
off=0
for part in re.split(rb'\x00+',d):
    i=d.find(part,off); off=i+len(part)
    if len(part)<3: continue
    try: s=part.decode('shift_jis')
    except: s=part.decode('shift_jis','replace')
    if sum(c.isprintable() for c in s)/max(1,len(s))<0.85: continue
    print('%010x %s'%(a+i,s.strip()))
