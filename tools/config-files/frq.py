import sys,struct,collections
def kana7(b):  # JIS X 0201 katakana with high bit stripped
    return bytes(x|0x80 for x in b).decode('cp932','replace')
def parse(fn):
    d=open(fn,'rb').read()
    W=lambda o: struct.unpack_from('>H',d,o)[0]
    rows=[struct.unpack_from('>I',d,4*i)[0] for i in range(10)]
    ncols=(rows[1]-rows[0])//1  # words per row
    recs={}
    grid=[]
    for r,base in enumerate(rows):
        row=[]
        for c in range(rows[1]-rows[0]):
            p=W(2*(base+c))
            if p==0: row.append([]); continue
            lo=2*(base+p); n=W(lo)
            ptrs=[W(lo+2+2*i) for i in range(n)]
            ids=[]
            for q in ptrs:
                o=2*(base+q); ids.append(o)
                if o not in recs:
                    x,y,pw,a,b=struct.unpack_from('>HHHHH',d,o)
                    o2=o+10; L=W(o2); z=d.index(b'\0',o2+2); name=d[o2+2:z]; o3=o2+2+((z-(o2+2)+1)&~1); L2=W(o3); rd=d[o3+2:o3+2+L2]
                    recs[o]=(x,y,pw,a,b,name.decode('iso2022_jp','replace'),kana7(rd),o3+2+L2)
            row.append(ids)
        grid.append(row)
    return d,rows,grid,recs
if __name__=='__main__':
    d,rows,grid,recs=parse(sys.argv[1])
    print('rows(word offs)',[hex(r) for r in rows],'cols',rows[1]-rows[0])
    print('records',len(recs),'first',hex(min(recs)),'end',hex(max(r[7] for r in recs.values())),'filelen',hex(len(d)))
    for o in sorted(recs)[:int(sys.argv[2]) if len(sys.argv)>2 else 9999]:
        x,y,pw,a,b,n,k,e=recs[o]; print(hex(o),hex(x),x,hex(y),y,pw,hex(a),hex(b),hex(L) if 0 else '',n,k)
    occ=['%2d'%sum(1 for c in row if c) for row in grid]; print('nonempty cells per row',occ)
