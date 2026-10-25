import sys,struct,datetime
d=open(sys.argv[1],'rb').read()
base=0x28000
h=struct.unpack_from('>6H',d,base+4)
print('hdr',[hex(x) for x in h])
ny=struct.unpack_from('>H',d,base+0xa)[0]
yrs=[struct.unpack_from('>3H',d,base+0xc+6*i) for i in range(ny)]
tab=base+0xc+6*ny
for y,off,cnt in yrs:
    out=[]
    for j in range(cnt):
        v=struct.unpack_from('>H',d,tab+2*(off+j))[0]
        m,dd,t=v>>12,(v>>7)&31,v&127
        wd=datetime.date(y,m,dd).strftime('%a')
        out.append(f'{m:02}/{dd:02}{wd[:2]}:{t}')
    print(y,cnt,' '.join(out))
