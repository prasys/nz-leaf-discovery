import os,struct,sys
IMG=os.path.expanduser(os.environ.get("NISSAN_IMG", "~/nissan/sdcard/nissan-sd-485-1972-00.img")); P0=888833*512
f=open(IMG,'rb')
def rd(o,n): f.seek(o); return f.read(n)
bs=rd(P0,512)
bps,spc,rsv,nf=struct.unpack_from('<HBHB',bs,11); fatsz=struct.unpack_from('<I',bs,36)[0]; rootc=struct.unpack_from('<I',bs,44)[0]
fat0=P0+rsv*bps; data0=fat0+nf*fatsz*bps; csz=spc*bps
def chain(c):
    out=[]
    while 2<=c<0x0ffffff8:
        out.append(c); c=struct.unpack('<I',rd(fat0+4*c,4))[0]&0x0fffffff
    return out
def readdir(c):
    b=b''.join(rd(data0+(x-2)*csz,csz) for x in chain(c)); ents=[]; lfn=''
    for i in range(0,len(b),32):
        e=b[i:i+32]
        if e[0]==0: break
        if e[0]==0xe5: lfn=''; continue
        if e[11]==0x0f:
            part=(e[1:11]+e[14:26]+e[28:32]).decode('utf-16-le','ignore').split('\x00')[0]; lfn=part+lfn; continue
        name=e[:8].decode('ascii','replace').strip()+('.'+e[8:11].decode('ascii','replace').strip() if e[8:11].strip() else '')
        ct10,ctime,cdate,adate,hi,mtime,mdate,lo,size=struct.unpack_from('<BHHHHHHHI',e,13)
        ents.append(dict(name=lfn or name,attr=e[11],ctms=ct10,ctime=ctime,cdate=cdate,adate=adate,mtime=mtime,mdate=mdate,clus=(hi<<16)|lo,size=size)); lfn=''
    return ents
def fd(d): return '%04d-%02d-%02d'%(1980+(d>>9),(d>>5)&15,d&31)
def ft(t,ms=0): return '%02d:%02d:%02d.%02d'%(t>>11,(t>>5)&63,(t&31)*2+ms//100,ms%100)
def show(e): return '%-28s attr=%02x C=%s %s M=%s %s A=%s size=%d'%(e['name'],e['attr'],fd(e['cdate']),ft(e['ctime'],e['ctms']),fd(e['mdate']),ft(e['mtime']),fd(e['adate']),e['size'])
def walk(path):
    c=rootc; ents=readdir(c)
    for p in [x for x in path.split('/') if x]:
        e=[x for x in ents if x['name'].upper()==p.upper()][0]; ents=readdir(e['clus'])
    return ents
if __name__=='__main__':
    print('BPB bps',bps,'spc',spc,'rsv',rsv,'nfats',nf,'fatsz',fatsz,'rootclus',rootc,'label',bs[71:82],'volid',bs[67:71].hex())
    for p in sys.argv[1:]:
        print('==',p or '/')
        for e in walk(p): print('  ',show(e))
