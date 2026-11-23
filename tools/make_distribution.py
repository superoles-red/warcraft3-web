#!/usr/bin/env python3
"""Split a complete game ZIP into immutable resumable downloads for a static host."""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zlib
from pathlib import Path
from zipfile import ZipFile

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive', type=Path)
parser.add_argument('--output', type=Path, default=project/'local/distribution')
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(exist_ok=True, parents=True)
chunks = []
whole = hashlib.sha256()
with args.archive.open('rb') as reader:
    while block := reader.read(12*1024*1024):
        digest = hashlib.sha256(block).hexdigest()
        name = digest + '.bin'
        target = out/name
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            with tempfile.NamedTemporaryFile(dir=out, delete=False) as tmp:
                tmp.write(block)
            os.replace(tmp.name,target)
        whole.update(block)
        chunks.append({'file': name, 'bytes':len(block), 'sha256':digest,'crc32':zlib.crc32(block)})
with ZipFile(args.archive) as z:
    art = out/'presentation'
    art.mkdir(exist_ok=True)
    for item in z.namelist():
        if item.startswith('presentation/') and len(Path(item).parts) == 2:
            with z.open(item) as src, (art/Path(item).name).open('wb') as dst:
                shutil.copyfileobj(src, dst)
manifest = {'format':1, 'name':args.archive.name,'bytes':args.archive.stat().st_size,'id':whole.hexdigest(),'chunks':chunks}
with tempfile.NamedTemporaryFile(mode='w',dir=out,delete=False) as tmp:
    json.dump(manifest,tmp,separators=(',',':'))
os.replace(tmp.name,out/'manifest.json')
print(f'{len(chunks)} blocks, {manifest["bytes"]:,} bytes, SHA-256 {manifest["id"]}')
