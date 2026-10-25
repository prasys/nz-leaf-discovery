import sys,re
img=sys.argv[1]; offs=[int(x,0) for x in sys.argv[3:]]; w=int(sys.argv[2])
f=open(img,'rb')
for o in offs:
    f.seek(o-w); b=f.read(2*w)
    runs=[m.group().decode('shift_jis','replace') for m in re.finditer(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e]|[\xa1-\xdf])+',b) if len(m.group())>=4]
    print(f'== {o:#x} (sector {o//512}):',' | '.join(runs)[:2500]); print()
