import json,os,sqlite3
from pathlib import Path
from morphology.runtime_v5 import Recorder
from morphology.ecology_v5 import advance
from morphology.development import digest
base=Path('/srv/samo-v5-acceptance/state');filler=base/'disk-full-probe';r=Recorder(base/'long.sqlite');before=r.load();previous=digest(before);failure=None
try:
 with filler.open('wb') as f:
  while True:
   try:f.write(b'x'*1048576);f.flush()
   except OSError as e:failure=e.errno;break
 s,e=advance(before)
 try:r.commit(s,e);raise AssertionError('commit unexpectedly succeeded on full disk')
 except (sqlite3.DatabaseError,OSError) as err:commit_error=type(err).__name__
 assert digest(r.load())==previous
finally:
 if filler.exists():filler.unlink()
 r.close()
r=Recorder(base/'long.sqlite');assert digest(r.load())==previous;s,e=advance(r.load());r.commit(s,e);print(json.dumps(dict(fill_errno=failure,commit_error=commit_error,checkpoint_preserved=True,before=before['core']['step'],after=r.load()['core']['step'])));r.close()
