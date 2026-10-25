import sys,struct,os
src,out=sys.argv[1],sys.argv[2]
os.makedirs(out,exist_ok=True)
f=open(src,'rb'); d=f.read(0x10000)
n=struct.unpack_from('<I',d,28)[0]
for i in range(n):
    o=32+24*i
    name=d[o:o+12].decode('ascii').strip('\0 ')
    off,s1,s2=struct.unpack_from('<3I',d,o+12)
    f.seek(off); open(os.path.join(out,name),'wb').write(f.read(s2))
