import sys,struct
d=open(sys.argv[1],'rb').read()
base=0x28000
assert d[base+4:base+8]==bytes.fromhex('3c030900')
hdr=d[base+8:base+12]; total=struct.unpack('>H',hdr[0:2])[0]; nyears=struct.unpack('>H',hdr[2:4])[0]
p=base+12; years=[]
for i in range(nyears):
    y,off,cnt=struct.unpack('>HHH',d[p:p+6]); years.append((y,off,cnt)); p+=6
rec0=p
print('header total_records=%d years=%d records_start=0x%x'%(total,nyears,rec0))
for y,off,cnt in years:
    out=[]
    for k in range(cnt):
        v=struct.unpack('>H',d[rec0+2*(off+k):rec0+2*(off+k)+2])[0]
        out.append('%02d-%02d/t%d'%(v>>12,(v>>7)&31,v&127))
    print(y,cnt,' '.join(out))
