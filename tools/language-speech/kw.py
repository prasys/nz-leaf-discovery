import sys,os,mmap
kws=['時刻','時計','年月日','午前','午後','時差','夏時間','祝日','日本語','英語','中国語','韓国語','曜日','時間帯','現在時刻','時報']
asc=[b'JST',b'GMT',b'UTC',b'English',b'ENGLISH',b'Japanese',b'TIMEZONE',b'TimeZone',b'clock',b'CLOCK',b'GPSTIME',b'yyyy',b'%Y',b'ENG',b'JPN',b'Chinese',b'Korean']
pats=[]
for k in kws:
    for enc in ['shift_jis','utf-16le','utf-16be','utf-8','euc_jp']:
        pats.append((k+'/'+enc,k.encode(enc)))
for a in asc:
    pats.append((a.decode()+'/ascii',a)); pats.append((a.decode()+'/u16',a.decode().encode('utf-16le')))
root=sys.argv[1]
for dp,dn,fn in os.walk(root):
    if 'Spotlight' in dp or 'fseventsd' in dp: continue
    for f in fn:
        p=os.path.join(dp,f)
        try:
            sz=os.path.getsize(p)
            if sz==0: continue
            fh=open(p,'rb'); m=mmap.mmap(fh.fileno(),0,access=mmap.ACCESS_READ)
        except Exception as e: print('ERR',p,e); continue
        hits=[]
        for name,b in pats:
            i=m.find(b); c=0; first=i
            while i!=-1 and c<1000:
                c+=1; i=m.find(b,i+1)
            if c: hits.append(f'{name}:{c}@{first:#x}')
        if hits: print(p.replace(root,''),sz,' '.join(hits),flush=True)
        m.close(); fh.close()
