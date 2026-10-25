import sys,struct,datetime
d=open(sys.argv[1],'rb').read()
assert d[0x40:0x44]==b'ECEC',d[0x40:0x44]
va,off=struct.unpack('<II',d[0x44:0x4c]); base=va-off
print('ROMHDR va %#x off %#x base %#x'%(va,off,base))
F='<17I2HI2I'; r=struct.unpack(F,d[off:off+struct.calcsize(F)])
names='dllfirst dlllast physfirst physlast nummods RAMStart RAMFree RAMEnd CopyEntries CopyOffset ProfileLen ProfileOffset numfiles KernelFlags FSRamPercent DrivglobStart DrivglobLen CPUType MiscFlags pExtensions TrackingStart TrackingLen'.split()
for n,v in zip(names,r): print(' %s=%#x'%(n,v))
nm,nf=r[4],r[12]
def cstr(a):
    o=a-base
    if not 0<=o<len(d): return '?%#x'%a
    e=d.index(b'\0',o); return d[o:e].decode('latin1')
def ft(lo,hi):
    t=(hi<<32)|lo
    try: return (datetime.datetime(1601,1,1)+datetime.timedelta(microseconds=t//10)).isoformat(' ')
    except Exception: return hex(t)
p=off+struct.calcsize(F)
print('MODULES',nm)
for i in range(nm):
    a,lo,hi,sz,nmp,e32,o32,lo_=struct.unpack('<8I',d[p:p+32]); p+=32
    print(' M %-28s size=%9d attr=%#x time=%s'%(cstr(nmp),sz,a,ft(lo,hi)))
print('FILES',nf)
for i in range(nf):
    a,lo,hi,rs,cs,nmp,lo_=struct.unpack('<7I',d[p:p+28]); p+=28
    print(' F %-36s real=%9d comp=%9d attr=%#x time=%s load=%#x'%(cstr(nmp),rs,cs,a,ft(lo,hi),lo_))
