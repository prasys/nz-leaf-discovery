#!/usr/bin/env python3
"""Read-only source inventory from the original image, with private names withheld.

Run with python3 -I. Reads only FAT/exFAT metadata and allowlisted speech files.
Phonebook/PRIVATE payloads, BVOICE audio, and user grammar contents are never read.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, default=Path(os.environ.get(
        "NISSAN_IMG", "~/nissan/sdcard/nissan-sd-485-1972-00.img")).expanduser())
    ap.add_argument("--extract-gid", type=Path)
    args = ap.parse_args()
    if args.extract_gid and not args.extract_gid.resolve().is_relative_to(
        Path.home()/"nissan/work/language-speech"
    ):
        ap.error("GID output must be under ~/nissan/work/language-speech/")
    # Import the trusted repo parser, never modules from an extracted directory.
    os.environ["NISSAN_IMG"] = str(args.image)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"config-files"))
    import fatdir
    public = []
    def speech_walk(cluster, path):
        for entry in fatdir.readdir(cluster):
            name = entry["name"]
            if name in (".", ".."):
                continue
            child = path + "/" + name
            if entry["attr"] & 16:
                speech_walk(entry["clus"], child)
            else:
                chain = fatdir.chain(entry["clus"])
                public.append({"path": child, "size": entry["size"],
                               "first_image_offset": fatdir.data0+(chain[0]-2)*fatdir.csz,
                               "clusters": len(chain)})
                if args.extract_gid and child.upper()=="SPEECH/JP/GID/SJP00300.GID":
                    data=b"".join(fatdir.rd(fatdir.data0+(c-2)*fatdir.csz,fatdir.csz)
                                   for c in chain)[:entry["size"]]
                    args.extract_gid.parent.mkdir(parents=True, exist_ok=True)
                    with args.extract_gid.open("xb") as f:
                        f.write(data)
                    public[-1]["sha256"] = hashlib.sha256(data).hexdigest()
    speech = next(e for e in fatdir.walk("") if e["name"].upper()=="SPEECH")
    speech_walk(speech["clus"], "SPEECH")
    names=[]
    for e in fatdir.walk("DBDIR"):
        if e["name"].upper() in ("BVOICEB","BVOICED","BVOICEI"):
            clusters=fatdir.chain(e["clus"])
            names.append({"path":"DBDIR/"+e["name"], "size":e["size"],
                          "first_image_offset":fatdir.data0+(clusters[0]-2)*fatdir.csz,
                          "pages_4096":e["size"]//4096,
                          "contents":"redacted; payload not read"})
    with args.image.open("rb") as image:
        base=29925377*512
        def rd(off,n):
            image.seek(off)
            b=image.read(n)
            if len(b)!=n: raise ValueError("short image read")
            return b
        bs=rd(base,512)
        if bs[3:11]!=b"EXFAT   ":raise ValueError("no hidden exFAT")
        fatofs,fatlen,heap,ccount,root=struct.unpack_from("<5I",bs,0x50)
        bps,spc=1<<bs[0x6c],1<<bs[0x6d]
        csz=bps*spc
        fat=rd(base+fatofs*bps,fatlen*bps)
        def coff(c):return base+heap*bps+(c-2)*csz
        def directory(c, nofat=False, size=0):
            clusters=[]
            if nofat:clusters=list(range(c,c+(size+csz-1)//csz))
            else:
                seen=set()
                while 2<=c<0xfffffff7:
                    if c in seen or len(seen)>ccount:raise ValueError("exFAT cycle")
                    seen.add(c);clusters.append(c);c=struct.unpack_from("<I",fat,c*4)[0]
            data=b"".join(rd(coff(c),csz) for c in clusters)
            entries=[];p=0
            while p+32<=len(data) and data[p]:
                if data[p]!=0x85:p+=32;continue
                n=data[p+1]
                parts=[data[p+j*32:p+(j+1)*32] for j in range(1,n+1)]
                stream=next(s for s in parts if s[0]==0xc0)
                name=b"".join(s[2:32] for s in parts if s[0]==0xc1).decode("utf-16le").split("\0")[0]
                cluster,length=struct.unpack_from("<IQ",stream,20)
                entries.append((name,struct.unpack_from("<H",data,p+4)[0],cluster,
                                bool(stream[1]&2),length,
                                coff(clusters[p//csz])+p%csz))
                p+=32*(n+1)
            return entries
        system=next(e for e in directory(root) if e[0].upper()=="SPEECH")
        private=[]
        def count_only(entry, kind="other speech metadata"):
            if entry[0].upper()=="VTG":kind="voice-tag"
            elif entry[0].upper() in ("VR","TTG"):kind="generated grammar"
            if entry[1]&16:
                for child in directory(entry[2],entry[3],entry[4]):count_only(child,kind)
            else:private.append({"kind":kind,"directory_entry_image_offset":entry[5],"size":entry[4]})
        count_only(system)
    print(json.dumps({"public_speech_files":public,"bvoice_files":names,
                      "hidden_speech_file_count":len(private),
                      "hidden_voice_tag_file_count":sum(e["kind"]=="voice-tag" for e in private),
                      "hidden_speech_entries_counts_offsets_only":private},indent=2))
    fatdir.f.close()


if __name__ == "__main__":main()
