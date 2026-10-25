import sys
img,a,b=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
f=open(img,'rb'); f.seek(a*512)
Z=b'\0'*512; F=b'\xff'*512
cur=None; start=a; s=a; CH=2048
while s<=b:
    n=min(CH,b-s+1); buf=f.read(n*512)
    for i in range(n):
        sec=buf[i*512:(i+1)*512]
        k='Z' if sec==Z else 'F' if sec==F else 'D'
        if k!=cur:
            if cur: print(f"{start}-{s+i-1} ({s+i-start}) {cur}")
            cur=k; start=s+i
    s+=n
print(f"{start}-{b} ({b+1-start}) {cur}")
