#!/usr/bin/python3
"""Trusted KV publisher. Reads only an independently verified public document, no organism execution."""
import json
import os
import time
import hashlib
import subprocess
from datetime import datetime,timezone
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

BASE=Path('/srv/samo/publisher')
CREDENTIALS=BASE/'oauth.json'
ACCOUNT='b999769911d82e5e2d6de5c278921c24'
NAMESPACE='78b3dd11ab844ef38d9af83e8634fba6'
CLIENT='54d11594-84e4-41aa-b438-e81b8fa78ee7'

def atomic(path,data):
    temp=path.with_suffix('.tmp')
    with open(temp,'w') as f:
        os.fchmod(f.fileno(),0o600);json.dump(data,f);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def main():
    path=Path('/srv/samo/site/data/ecosystem.json')
    if path.stat().st_size>4_000_000: raise ValueError('snapshot cap')
    raw=path.read_bytes(); data=json.loads(raw)
    if data.get('schema')!=1 or data.get('protocol') not in ('samo-ecology-v2','samo-ecology-v4') or len(data.get('population',[]))>8 or len(data.get('events',[]))>1024: raise ValueError('snapshot schema')
    if data.get('observation',{}).get('environment')!='vps': raise ValueError('only production observation may publish')
    result=subprocess.run(['systemctl','show','samo-organism.service','-p','ActiveState','-p','SubState','-p','NRestarts'],capture_output=True,text=True,timeout=5,check=True)
    infra=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    data['infrastructure']=dict(checked_at=datetime.now(timezone.utc).isoformat(),organism=infra.get('ActiveState','unknown'),detail=infra.get('SubState','unknown'),technical_restarts=int(infra.get('NRestarts','0')))
    data['published_at']=datetime.now(timezone.utc).isoformat()
    raw=json.dumps(data,sort_keys=True,separators=(',',':')).encode()
    credentials=json.loads(CREDENTIALS.read_text())
    if time.time()>credentials['expires_at']-300:
        payload=urllib.parse.urlencode(dict(grant_type='refresh_token',refresh_token=credentials['refresh_token'],client_id=CLIENT)).encode()
        request=urllib.request.Request('https://dash.cloudflare.com/oauth2/token',data=payload,headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'node','Accept':'*/*'})
        with urllib.request.urlopen(request,timeout=30) as response: refreshed=json.load(response)
        credentials.update(access_token=refreshed['access_token'],refresh_token=refreshed.get('refresh_token',credentials['refresh_token']),expires_at=time.time()+refreshed['expires_in'])
        atomic(CREDENTIALS,credentials)
    request=urllib.request.Request(f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/storage/kv/namespaces/{NAMESPACE}/values/snapshot',method='PUT',data=raw,
                                  headers={'Authorization':'Bearer '+credentials['access_token'],'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=30) as response: result=json.load(response)
    if not result.get('success'): raise RuntimeError('KV publication rejected')
    atomic(BASE/'status.json',dict(published_at=time.time(),observed_at=data['observation']['observed_at'],step=data['step'],sha256=hashlib.sha256(raw).hexdigest()))

if __name__=='__main__':
    try: main()
    except Exception as error:
        details=dict(error=type(error).__name__,time=time.time())
        if isinstance(error,urllib.error.HTTPError):
            details['http_status']=error.code
            details['endpoint']=urllib.parse.urlsplit(error.url).netloc
            details['content_type']=error.headers.get('Content-Type')
            try:
                body=json.loads(error.read(10000))
                details['reason']={k:body[k] for k in ('error','error_description','errors','success') if k in body}
            except Exception: pass
        atomic(BASE/'error.json',details)
        raise SystemExit(1)
