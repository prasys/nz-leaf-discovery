import sys,struct,zlib,os
src,ind,out=sys.argv[1:4]
I=open(ind,'rb').read(); raw,csz,n,chunk=struct.unpack_from('<4I',I,0)
offs=list(struct.unpack_from('<%dI'%n,I,16))+[csz]
d=open(src,'rb').read(); assert len(d)==csz,(len(d),csz)
with open(out,'wb') as f:
    tot=0
    for i in range(n):
        b=zlib.decompress(d[offs[i]:offs[i+1]]); f.write(b); tot+=len(b)
print(os.path.basename(src),'raw',raw,'got',tot,'chunks',n,'chunk',chunk, 'ind_len',len(I),'expected',16+4*n)
