import sys,struct,zlib,binascii
# try common checksum candidates against given header/trailer values
def cands(b):
    r={}
    r['sum8']=sum(b)&0xff; r['sum16b']=sum(b)&0xffff; r['sum32b']=sum(b)&0xffffffff
    if len(b)%2==0:
        w=struct.unpack('>%dH'%(len(b)//2),b); r['sumBEw16']=sum(w)&0xffff
        w=struct.unpack('<%dH'%(len(b)//2),b); r['sumLEw16']=sum(w)&0xffff
    x=0
    for c in b: x^=c
    r['xor8']=x
    r['crc32']=zlib.crc32(b)&0xffffffff; r['crc16ccitt']=binascii.crc_hqx(b,0); r['crc16ccittFFFF']=binascii.crc_hqx(b,0xffff)
    r['adler']=zlib.adler32(b)
    return r
fn=sys.argv[1]; d=open(fn,'rb').read()
targets={}
for o in (0,2,4,len(d)-2,len(d)-4):
    if 0<=o<=len(d)-4: targets['BE32@%x'%o]=struct.unpack_from('>I',d,o)[0]; targets['LE32@%x'%o]=struct.unpack_from('<I',d,o)[0]
    if 0<=o<=len(d)-2: targets['BE16@%x'%o]=struct.unpack_from('>H',d,o)[0]; targets['LE16@%x'%o]=struct.unpack_from('<H',d,o)[0]
spans={'all':d}
for s in (2,4,8,16,32): spans['from%d'%s]=d[s:]
spans['excl_last2']=d[:-2]; spans['excl_last4']=d[:-4]
hits=0
for sn,b in spans.items():
    for cn,v in cands(b).items():
        for tn,t in targets.items():
            if v==t and t not in (0,0xffff,0xffffffff) and v>0xff: print('HIT',fn,sn,cn,tn,hex(v)); hits+=1
            # also complement
            if cn.startswith('sum') and ((-v)&0xffff)==t and t>0xff: print('HIT neg',fn,sn,cn,tn,hex(t)); hits+=1
print(fn,'hits',hits)
