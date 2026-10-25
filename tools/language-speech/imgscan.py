import sys,mmap
img=sys.argv[1]; ranges=[(1,888832),(29925377,30949376)]
kws=['時計設定','時計','言語','日本語','English','設定','時刻','夏時間','年','時差','タイムゾーン','時計表示','GPS','オフセット','自動調整']
pats=[]
for k in kws:
    for enc in ['shift_jis','utf-16le','utf-8']:
        try: pats.append((k,enc,k.encode(enc)))
        except: pass
f=open(img,'rb'); m=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
for a,b in ranges:
    s,e=a*512,(b+1)*512
    for k,enc,p in pats:
        i=m.find(p,s,e); c=0; first=i
        while i!=-1 and c<200: c+=1; i=m.find(p,i+1,e)
        if c: print(f'sectors {a}-{b} {k}/{enc}: {c} first@byte {first:#x} (sector {first//512})')
