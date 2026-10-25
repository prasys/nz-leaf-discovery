import sys,struct
f=open(sys.argv[1],'rb')
a,b=int(sys.argv[2]),int(sys.argv[3])
f.seek(a*512); s=a
while s<=b:
    buf=f.read(512*4096)
    if not buf: break
    for i in range(len(buf)//512):
        sec=buf[i*512:(i+1)*512]
        if sec[0x30:0x34]==b'SUM4' or sec[0x50:0x54]==b'470-' or b'JLNI' in sec[:0x40] or (sec[4:16]==b'\0'*12 and sec[16:512]==b'\0'*496 and sec[:4]!=b'\0'*4):
            print(s+i, sec[:0x80].hex())
    s+=len(buf)//512
