import sys,struct,os,wave
src,out=sys.argv[1],sys.argv[2]; rate=int(sys.argv[3]) if len(sys.argv)>3 else 22050
os.makedirs(out,exist_ok=True)
d=open(src,'rb').read()
n=struct.unpack_from('<I',d,0x13920)[0]
rows=[]
for i in range(n):
    o=0x13940+16*i
    a,b,off,s1,s2=struct.unpack_from('<4BIII',d,o)[0:2]+struct.unpack_from('<III',d,o+4) if False else (None,)*5
    fb=d[o:o+4]; off,s1,s2=struct.unpack_from('<III',d,o+4)
    rows.append((i,fb.hex(),off,s2))
    blob=d[off:off+s2]
    if fb==b'\x02\x01\x01\x02':
        w=wave.open(os.path.join(out,f'clip{i:04d}_pcm.wav'),'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(blob); w.close()
    else:
        open(os.path.join(out,f'clip{i:04d}_{fb.hex()}.bin'),'wb').write(blob)
with open(os.path.join(out,'index.tsv'),'w') as f:
    for r in rows: f.write('\t'.join(map(str,r))+'\n')
print(n)
