#!/usr/bin/env python3
"""manual_iat_slot.py - read-only: print the runtime VA of the IAT slot for a
named import in a Windows CE PE32 module (for Ghidra xrefs when the thunk is
not named). Usage: python3 -I manual_iat_slot.py <module> <ImportName>"""
import struct,sys
d=open(sys.argv[1],'rb').read(); want=sys.argv[2]
pe=struct.unpack_from('<I',d,0x3c)[0]; ns=struct.unpack_from('<H',d,pe+6)[0]; opt=struct.unpack_from('<H',d,pe+20)[0]; base=struct.unpack_from('<I',d,pe+52)[0]
secs=[];o=pe+24+opt
for s in range(ns):
    vsz,va,rsz,raw=struct.unpack_from('<IIII',d,o+8); secs.append((va,max(vsz,rsz),raw)); o+=40
def r2f(r):
    for va,sz,raw in secs:
        if va<=r<va+sz: return r-va+raw
f=r2f(struct.unpack_from('<I',d,pe+24+104)[0])
while True:
    ilt,ts,fc,name,iat=struct.unpack_from('<IIIII',d,f)
    if name==0: break
    k=0
    while True:
        src=struct.unpack_from('<I',d,r2f(ilt or iat)+4*k)[0]
        if src==0: break
        if not src&0x80000000:
            nm=d[r2f(src)+2:d.index(b'\0',r2f(src)+2)].decode()
            if nm==want: print('%08x'%(base+iat+4*k))
        k+=1
    f+=20
