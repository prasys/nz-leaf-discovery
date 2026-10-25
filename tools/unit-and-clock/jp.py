import sys,re
img=sys.argv[1]; f=open(img,'rb')
words=['時計','時刻','時差','サマータイム','標準時','日本時間','GPS時刻','時計合わせ','時計表示','時刻補正']
pats=[]
for w in words:
    pats.append((w,'u16',w.encode('utf-16le'))); pats.append((w,'sjis',w.encode('shift_jis')))
for start,end in [(1,888833),(29925377,30949377)]:
    pos=start*512; endb=end*512; CH=32<<20
    while pos<endb:
        f.seek(pos); d=f.read(min(CH,endb-pos))
        for w,enc,p in pats:
            for m in re.finditer(re.escape(p),d):
                a=pos+m.start()
                if enc=='u16':
                    # expand context in utf16
                    s=a-80; s-= (s-a)%2
                    ctx=d[max(0,m.start()-80):m.start()+120].decode('utf-16le','replace')
                else:
                    ctx=d[max(0,m.start()-60):m.start()+80].decode('shift_jis','replace')
                ctx=''.join(c if c.isprintable() else '·' for c in ctx)
                print('%010x sec%d %s %s | %s'%(a,a//512,enc,w,ctx))
        pos+=CH
