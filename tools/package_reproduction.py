"""Package public source provenance only; sealed archives/seeds are never included."""
import json
import hashlib
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
paths=sorted([*root.glob('samo/*.py'),*root.glob('protocols/*.json'),*root.glob('tests/*.py'),root/'pyproject.toml'])
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
output=root/'output/reproduction-source.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
    for p in paths:z.write(p,str(p.relative_to(root)))
    z.writestr('MANIFEST.json',json.dumps(manifest,indent=2))
(root/'output/source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(output)
