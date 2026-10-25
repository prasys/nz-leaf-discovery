import sys,struct,os
# Parse Clarion speech container: 16-byte ascii hdr, u32 filesize, u32 dirend?, u32 ?, u32 count, then 24-byte entries
def parse(path):
    f=open(path,'rb'); d=f.read(0x10000)
    hdr=d[:16].decode('ascii','replace')
    a,b,c,n=struct.unpack_from('<4I',d,16)
    print(path, 'hdr',hdr,'fsize',a,'b',hex(b),'c',hex(c),'n',n, 'actual',os.path.getsize(path))
    ents=[]
    for i in range(n):
        o=32+24*i
        name=d[o:o+12].decode('ascii','replace')
        off,s1,s2=struct.unpack_from('<3I',d,o+12)
        f.seek(off); mg=f.read(16)
        print(f'{i:3} {name} off={off:#x} s1={s1} s2={s2} magic={mg.hex()} {mg[:16]!r}')
        ents.append((name,off,s1,s2))
    return ents
if __name__=='__main__':
    for p in sys.argv[1:]: parse(p)
