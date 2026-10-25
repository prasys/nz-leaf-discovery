import sys,re
f=open(sys.argv[1],'rb')
words=sys.argv[2].split(',')
encs=['utf-8','utf-16le','utf-16be','shift_jis','euc_jp']
for start,end in [(1,888833),(29925377,30949377)]:
    pos=start*512; endb=end*512; CH=32<<20
    while pos<endb:
        f.seek(pos); d=f.read(min(CH,endb-pos))
        for w in words:
            for e in encs:
                p=w.encode(e)
                for m in re.finditer(re.escape(p),d):
                    print('%010x %s %s'%(pos+m.start(),e,w))
        pos+=CH
