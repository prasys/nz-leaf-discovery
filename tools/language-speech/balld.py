import sys,re
d=open(sys.argv[1],'rb').read()
# records: ... 02 c0 <klen> key <vlen> value
for m in re.finditer(rb'\x02\xc0([\x01-\x40])',d):
    kl=m.group(1)[0]; o=m.end()
    k=d[o:o+kl]
    if not re.fullmatch(rb'[A-Z0-9_]+',k): continue
    vl=d[o+kl]; v=d[o+kl+1:o+kl+1+vl]
    try: vs=v.decode('shift_jis')
    except: vs=v.hex()
    print(f'{m.start():#07x} {k.decode()} = {vs!r}')
