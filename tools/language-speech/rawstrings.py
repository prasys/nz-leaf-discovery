import sys,re
img,s0,s1,out=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]
f=open(img,'rb'); f.seek(s0*512); total=(s1-s0+1)*512
rx_sj=re.compile(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e\t])+')
rx_u16=re.compile(rb'(?:[\x20-\x7e]\x00|[\x00-\xff][\x30-\x9f]|[\x00-\xff][\x4e-\x9f]){4,}')
o=open(out,'w',encoding='utf-8'); CH=1<<24; pos=0; ov=4096
while pos<total:
    f.seek(s0*512+pos); b=f.read(min(CH+ov,total-pos))
    for m in rx_sj.finditer(b):
        if m.start()>=CH: break
        t=m.group()
        if len(t)>=6:
            s=t.decode('shift_jis','replace')
            if s.count('�')==0: o.write(f'S {s0*512+pos+m.start():#x}\t{s}\n')
    for al in (0,1):
        for m in rx_u16.finditer(b,al):
            if m.start()>=CH: break
            t=m.group(); 
            if (m.start()-al)%2: continue
            t=t[:len(t)//2*2]; s=t.decode('utf-16le','replace')
            if len(s)>=4 and '�' not in s and sum(c.isprintable() for c in s)==len(s): o.write(f'U {s0*512+pos+m.start():#x}\t{s}\n')
    pos+=CH
