# read-only signature scanner over a sector range of the image; validates compressed streams by trial decompress
import sys,re,zlib,lzma,gzip,struct,collections
img,a,b=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
f=open(img,'rb')
SIGS={b'\x1f\x8b\x08':'gzip',b'\xfd7zXZ\x00':'xz',b'\x5d\x00\x00\x80\x00':'lzma',b'BZh9':'bzip2',b'\x7fELF':'ELF',
b'\x27\x05\x19\x56':'uImage',b'PK\x03\x04':'zip',b'\xff\xd8\xff':'jpeg',b'\x89PNG':'png',b'-----BEGIN':'pem',
b'SQLite format 3':'sqlite',b'MSCF\0\0\0\0':'cab',b'7z\xbc\xaf':'7z',b'Rar!':'rar',b'B000FF\n':'ce-bin',b'ECEC':'ECEC',
b'MZ\x90\x00':'pe-mz',b'hsqs':'squashfs',b'UBI#':'ubi',b'\x85\x19\x03\x20':'jffs2?',b'GIF8':'gif',b'RIFF':'riff',
b'\x30\x82':'der?',b'\x78\x9c':'zlib',b'\x78\xda':'zlib',b'OggS':'ogg',b'ID3':'id3',b'fLaC':'flac'}
pat=re.compile(b'|'.join(re.escape(k) for k in SIGS))
CH=64*2**20; pos=a*512; end=(b+1)*512; cnt=collections.Counter(); out=[]
while pos<end:
    f.seek(pos); d=f.read(min(CH+4096,end-pos))
    for m in pat.finditer(d):
        o=m.start()
        if o>=CH: break
        k=SIGS[m.group()]; ab=pos+o; ok=True; extra=''
        if k=='zlib':
            try: zo=zlib.decompressobj(); r=zo.decompress(d[o:o+65536],4096); ok=len(r)>=64; extra='out>=%d'%len(r)
            except Exception: ok=False
        elif k=='gzip':
            try: zo=zlib.decompressobj(31); r=zo.decompress(d[o:o+65536],4096); ok=len(r)>0
            except Exception: ok=False
        elif k=='der?':
            L=struct.unpack('>H',d[o+2:o+4])[0]; ok=d[o+4:o+6] in (b'\x30\x82',b'\x30\x81') and 100<L<20000; extra='len=%d'%L
        elif k=='riff': extra=d[o+8:o+12].decode('latin1')
        elif k=='id3': ok=d[o+3]<5 and d[o+4]==0
        elif k=='pe-mz':
            pe=struct.unpack('<I',d[o+0x3c:o+0x40])[0]; ok=pe<0x1000 and d[o+pe:o+pe+4]==b'PE\0\0'
        if ok:
            cnt[k]+=1
            if cnt[k]<=40: out.append('%s sector=%d off=%#x %s %s'%(k,ab//512,ab%512,extra,d[o:o+16].hex()))
    pos+=CH
print(dict(cnt)); print('\n'.join(out))
