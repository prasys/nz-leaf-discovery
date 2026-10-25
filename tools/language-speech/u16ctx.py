import sys,re
img=sys.argv[1]; offs=[int(x,0) for x in sys.argv[2:]]
f=open(img,'rb')
for o in offs:
    o&=~1
    f.seek(o-768); b=f.read(1536)
    s=b.decode('utf-16le','replace')
    parts=[p for p in re.split(r'[\x00-\x1f�]+',s) if len(p)>=1]
    print(f'== {o:#x} (sector {o//512}):', ' | '.join(parts)[:1500]); print()
