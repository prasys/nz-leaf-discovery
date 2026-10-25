import sys,re
d=open(sys.argv[1],'rb').read()
pat=re.compile(rb'(?:[\x20-\x7e]\x00){%d,}'%int(sys.argv[2]))
for m in pat.finditer(d):
    print('%08x %s'%(m.start(), m.group().decode('utf-16le')))
