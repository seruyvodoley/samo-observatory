"""Run inside the production service sandbox in disposable VM only."""
import json
import socket
import subprocess
from pathlib import Path
from samo.genome import ancestor, predict
from samo.vm import ins

results={}
for name,path in [('code_readonly','/srv/samo/code/should-not-exist'),('etc_readonly','/etc/samo-escape'),('root_inaccessible','/root/samo-escape')]:
    try: Path(path).write_text('probe'); results[name]=False
    except OSError: results[name]=True
try:
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM);sock.close();results['network_socket_denied']=False
except OSError: results['network_socket_denied']=True
g=ancestor();g['router']=[ins('JMP',0)]
value,cost,error,_=predict(g,[1,2,3],128)
results['untrusted_infinite_loop_fuel_trapped']=value is None and cost==128 and error=='fuel'
g=ancestor();g['router']=[[65535,0]]
value,cost,error,_=predict(g,[1],128)
results['invalid_opcode_rejected']=value is None and error=='invalid opcode'
Path('/srv/samo/state/probe-result.json').write_text(json.dumps(results))
if not all(results.values()): raise SystemExit(1)
