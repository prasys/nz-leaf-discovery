import re,sys
d=open(sys.argv[1],'rb').read()
for m in re.finditer(rb'(?:[\x20-\x7e]\x00){%d,}'%int(sys.argv[2]),d):
    print('%x %s'%(m.start(),m.group().decode('utf-16le')))
