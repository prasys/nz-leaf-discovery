import sys,re
P=sys.argv[1]
d=open(P+'/ICNSC001.DAT','rb').read()
print('ICNSC SJIS runs:',[m.group().decode('shift_jis','replace') for m in re.finditer(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\xfc])+',d)])
b=open(P+'/BICON001/BICON001.DAT','rb').read()
names=[m.group().decode('utf-16be','replace') for m in re.finditer(rb'(?:[\x00-\x9f][\x20-\xff]){2,}',b)]
print('BICON UTF16BE count',len(names),names[:80])
