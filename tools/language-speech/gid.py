import sys,struct,math,collections
d=open(sys.argv[1],'rb').read()
print('len',len(d))
print('hdr u32',struct.unpack_from('<16I',d,0))
def ent(b):
    c=collections.Counter(b);n=len(b)
    return -sum(v/n*math.log2(v/n) for v in c.values())
for o in [0,0x1000,0xe1a0,0x20000,0x100000,0x1000000,0x2000000]:
    print(hex(o), round(ent(d[o:o+65536]),3))
# offset table starting at 0x78?
tab=struct.unpack_from('<64I',d,0x78)
print([hex(x) for x in tab[:64]])
