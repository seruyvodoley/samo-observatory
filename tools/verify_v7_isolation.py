#!/usr/bin/env python3
"""Read-only acceptance evidence for the v7 candidate systemd service."""
import argparse,json,os,socket,subprocess
from pathlib import Path

def read(p):return Path(p).read_text().strip()

def main():
    p=argparse.ArgumentParser();p.add_argument('--writable-dir',required=True);p.add_argument('--project-mount',required=True);a=p.parse_args()
    cg=read('/proc/self/cgroup').split(':')[-1];base=Path('/sys/fs/cgroup')/cg.lstrip('/')
    expected={'cpu.max':'40000 100000','memory.max':'512000000','memory.swap.max':'0','pids.max':'32'}
    actual={k:read(base/k) for k in expected}
    if actual!=expected:raise SystemExit('resource cgroup mismatch: '+repr(actual))
    interfaces=sorted(x.name for x in Path('/sys/class/net').iterdir())
    if interfaces!=['lo']:raise SystemExit('non-loopback interface visible: '+repr(interfaces))
    try:
        s=socket.socket();s.settimeout(1);s.connect(('1.1.1.1',443))
        raise SystemExit('network unexpectedly reachable')
    except OSError:pass
    probe=Path(a.writable_dir)/'.isolation-probe'
    probe.write_text('ok');probe.unlink()
    try:
        Path('/etc/samo-v7-write-probe').write_text('unexpected')
        Path('/etc/samo-v7-write-probe').unlink()
        raise SystemExit('protected system path is writable')
    except OSError:pass
    mount=subprocess.run(['findmnt','-n','-o','FSTYPE,OPTIONS',a.project_mount],capture_output=True,text=True,check=True).stdout.strip()
    fstype,options=mount.split(' ',1)
    if fstype!='ext4' or 'noexec' not in options.split(','):
        raise SystemExit('project mount is not bounded ext4/noexec: '+mount)
    report={'status':'passed','cgroup':str(base),**actual,'interfaces':interfaces,
            'network_denied':True,'writable_path_only_probe':'passed','protected_system_write':'denied',
            'project_mount':mount,'project_mount_path':a.project_mount}
    print(json.dumps(report,sort_keys=True))

if __name__=='__main__':main()
