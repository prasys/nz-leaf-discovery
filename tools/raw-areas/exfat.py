# read-only exFAT walker against a raw image; lists live + deleted entries, optional extraction
import sys,struct,os,datetime
img=sys.argv[1]; vstart=int(sys.argv[2]); outdir=sys.argv[3] if len(sys.argv)>3 else None
f=open(img,'rb')
def rd(off,n): f.seek(off); return f.read(n)
bs=rd(vstart*512,512); assert bs[3:11]==b'EXFAT   ',bs[3:11]
volofs,vollen,fatofs,fatlen,heapofs,ccount,rootc,serial=struct.unpack('<QQIIIIII',bs[0x40:0x68])
bps=1<<bs[0x6c]; spc=1<<bs[0x6d]; csz=bps*spc
print('exFAT volofs=%d len=%d fatofs=%d fatlen=%d heap=%d clusters=%d root=%d serial=%08X csz=%d flags=%#x inuse=%d%%'%(volofs,vollen,fatofs,fatlen,heapofs,ccount,rootc,serial,csz,struct.unpack('<H',bs[0x6a:0x6c])[0],bs[0x70]))
base=vstart*512
fat=rd(base+fatofs*bps,fatlen*bps)
def nxt(c): return struct.unpack('<I',fat[4*c:4*c+4])[0]
def coff(c): return base+heapofs*bps+(c-2)*csz
def chain(c,nofat,size):
    if nofat:
        n=max(1,(size+csz-1)//csz); return list(range(c,c+n))
    out=[]
    while 2<=c<0xFFFFFFF7 and len(out)<ccount: out.append(c); c=nxt(c)
    return out
def ts(t,ms=0,tz=0):
    if t==0: return '-'
    y=(t>>25)+1980; mo=(t>>21)&15; d=(t>>16)&31; h=(t>>11)&31; mi=(t>>5)&63; s=(t&31)*2
    tzs=''
    if tz&0x80:
        q=tz&0x7f; q=q-128 if q&0x40 else q; tzs=' UTC%+.2fh'%(q/4)
    return '%04d-%02d-%02d %02d:%02d:%02d%s'%(y,mo,d,h,mi,s,tzs)
def readdir(c,nofat,size,path,depth=0):
    cl=chain(c,nofat,size) if size else chain(c,False,0)
    data=b''.join(rd(coff(x),csz) for x in cl)
    i=0
    while i+32<=len(data):
        e=data[i:i+32]; t=e[0]
        if t==0: 
            # keep scanning for deleted remnants beyond end marker? stop.
            break
        if t in (0x85,0x05):
            sc=e[1]; attr=struct.unpack('<H',e[4:6])[0]
            ct,mt,at=struct.unpack('<III',e[8:20]); ctz,mtz=e[22],e[23]
            ents=[data[i+32*k:i+32*k+32] for k in range(1,sc+1)]
            name=''; fc=0; ln=0; nofat2=False
            for x in ents:
                if x[0] in (0xC0,0x40):
                    nofat2=bool(x[1]&2); fc,ln=struct.unpack('<IQ',x[20:32])
                elif x[0] in (0xC1,0x41): name+=x[2:32].decode('utf-16le',errors='replace')
            name=name.split('\0')[0]
            dele = t==0x05
            print('%s%s%s attr=%#x size=%d clus=%d nofat=%d C=%s M=%s A=%s'%('  '*depth,'[DEL] ' if dele else '',path+'/'+name,attr,ln,fc,nofat2,ts(ct,0,ctz),ts(mt,0,mtz),ts(at)))
            if attr&0x10 and not dele and fc:
                readdir(fc,nofat2,ln,path+'/'+name,depth+1)
            elif outdir and not attr&0x10 and fc and ln and ln<200*2**20:
                cl2=chain(fc,nofat2 or dele,ln); d=b''.join(rd(coff(x),csz) for x in cl2)[:ln]
                p=os.path.join(outdir,(path+'/'+('DEL_' if dele else '')+name).lstrip('/').replace('/','__'))
                open(p,'wb').write(d)
            i+=32*(sc+1); continue
        elif t==0x83 or t==0x03:
            print('%sVOLLABEL%s %r'%('  '*depth,' (deleted)' if t==3 else '',e[2:2+2*e[1]].decode('utf-16le')))
        elif t==0x81: print('%sBITMAP clus=%d len=%d'%('  '*depth,*struct.unpack('<IQ',e[20:32])))
        elif t==0x82: print('%sUPCASE clus=%d len=%d'%('  '*depth,*struct.unpack('<IQ',e[20:32])))
        elif t==0xA0: print('%sGUID entry'%('  '*depth))
        else: print('%s?type %#x'%('  '*depth,t))
        i+=32
readdir(rootc,False,0,'')
