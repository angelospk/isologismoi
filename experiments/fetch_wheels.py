import json,urllib.request,sys,zipfile,hashlib
from pathlib import Path
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
from packaging.requirements import Requirement
from packaging.version import Version
DEST=Path("experiments/.wheelhouse");DEST.mkdir(exist_ok=True)
tags=set(sys_tags())
def fetch(arg):
 req=Requirement(arg)
 info=json.load(urllib.request.urlopen("https://pypi.org/pypi/"+req.name+"/json",timeout=20))
 versions=[]
 for v in info["releases"]:
  try: version=Version(v)
  except Exception:continue
  if not version.is_prerelease and version in req.specifier:versions.append(version)
 versions.sort(reverse=True)
 found=None
 for v in versions:
  for f in info["releases"][str(v)]:
   if not f["filename"].endswith(".whl"):continue
   try: good=bool(parse_wheel_filename(f["filename"])[3]&tags)
   except:good=False
   if good:found=f;break
  if found:break
 if not found:
  for v in versions:
   for f in info["releases"][str(v)]:
    if f["filename"].endswith(".tar.gz"):found=f;break
   if found:break
 if not found:raise RuntimeError("No compatible artifact "+arg)
 p=DEST/found["filename"]
 if not p.exists() or not (zipfile.is_zipfile(p) if p.suffix==".whl" else p.stat().st_size==found["size"]):
  offset=p.stat().st_size if p.exists() else 0
  request=urllib.request.Request(found["url"],headers={"Range":"bytes="+str(offset)+"-"} if offset else {})
  with urllib.request.urlopen(request,timeout=30) as r,p.open("ab" if r.status==206 else "wb") as w:
   while chunk:=r.read(1024*1024):w.write(chunk)
  if hashlib.sha256(p.read_bytes()).hexdigest()!=found["digests"]["sha256"]:raise ValueError("download checksum mismatch "+p.name)
 print(p.name,flush=True)
from concurrent.futures import ThreadPoolExecutor
args=sys.argv[1:]
if len(args)==2 and args[0]=="--requirements-json":args=json.loads(Path(args[1]).read_text())
with ThreadPoolExecutor(max_workers=4) as pool:
 list(pool.map(fetch,args))

