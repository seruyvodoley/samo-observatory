#!/usr/bin/env bash
# Disposable VM only. No execution on the shared production VPS.
set -euo pipefail
test "${SAMO_DISPOSABLE_VM:-}" = YES
root=/srv/samo
mkdir -p "$root/code" "$root/state/tmp" "$root/site/data"
cp -a /tmp/samo-package/samo /tmp/samo-package/protocols /tmp/samo-package/tests "$root/code/"
cp /tmp/samo-package/tools/linux-probes.py "$root/code/"
groupadd -f --system samo-data
id samo-organism >/dev/null 2>&1 || useradd --system --gid samo-data --no-create-home --shell /usr/sbin/nologin samo-organism
id samo-export >/dev/null 2>&1 || useradd --system --gid samo-data --no-create-home --shell /usr/sbin/nologin samo-export
chown -R samo-organism:samo-data "$root/state"; chmod 2750 "$root/state"
chown samo-export:samo-data "$root/site/data"
cp /tmp/samo-package/deploy/samo-organism.service /etc/systemd/system/
cp /tmp/samo-package/deploy/samo-recorder-export.{service,timer} /etc/systemd/system/
# VM has no project mount yet; bind mount service to its independent disposable rootfs.
sed -i '/Requires=srv-samo.mount/d;/After=srv-samo.mount/d' /etc/systemd/system/samo-{organism,recorder-export}.service
cat >/etc/systemd/system/samo.slice <<'UNIT'
[Slice]
CPUQuota=60%
MemoryMax=768000000
MemorySwapMax=0
TasksMax=48
UNIT
mkdir -p /etc/systemd/system/samo-organism.service.d
cat >/etc/systemd/system/samo-organism.service.d/probe.conf <<'UNIT'
[Service]
Type=oneshot
Environment=SAMO_ENV=disposable-vm
WatchdogSec=0
ExecStart=
ExecStart=/usr/bin/python3 /srv/samo/code/linux-probes.py
UNIT
systemctl daemon-reload
systemctl start samo-organism.service
cat "$root/state/probe-result.json"
mv /etc/systemd/system/samo-organism.service.d/probe.conf /tmp/probe.conf.completed
systemctl daemon-reload; systemctl start samo-organism.service
sleep 8
systemctl is-active --quiet samo-organism.service
cat /sys/fs/cgroup/samo.slice/samo-organism.service/{cpu.max,memory.max,memory.swap.max,pids.max}
cd "$root/code"; python3 -m unittest discover -s tests -q
before=$(runuser -u samo-organism -- python3 -c "from samo.ecology_runtime import Recorder; r=Recorder('$root/state/ecology.sqlite');print(r.load()['step'])")
systemctl kill --signal=KILL samo-organism.service
sleep 35
systemctl is-active --quiet samo-organism.service
after=$(runuser -u samo-organism -- python3 -c "from samo.ecology_runtime import Recorder; r=Recorder('$root/state/ecology.sqlite');print(r.load()['step'])")
test "$after" -gt "$before"
systemctl start samo-recorder-export.service
test -s "$root/site/data/ecosystem.json"
printf 'CRASH_RESUME before=%s after=%s\n' "$before" "$after"
systemctl show samo-organism.service -p NRestarts -p Result -p MemoryPeak -p CPUUsageNSec
# CPU enforcement including two child workers, measured independently of wall pacing.
systemd-run --unit=samo-cpu-probe --slice=samo.slice -p RemainAfterExit=yes -p CPUQuota=40% -p MemoryMax=512000000 -p MemorySwapMax=0 /usr/bin/python3 -c 'import subprocess,time; a=subprocess.Popen(["python3","-c","while True: pass"]); b=subprocess.Popen(["python3","-c","while True: pass"]); time.sleep(8); a.terminate();b.terminate();a.wait();b.wait()'
sleep 9
systemctl show samo-cpu-probe -p CPUUsageNSec -p Result
usage=$(systemctl show samo-cpu-probe -p CPUUsageNSec --value)
test "$usage" -lt 4500000000
# Hard OOM in bounded probe cgroup. Never on the production VPS.
systemd-run --unit=samo-memory-probe --slice=samo.slice -p MemoryMax=512000000 -p MemorySwapMax=0 -p OOMPolicy=kill /usr/bin/python3 -c 'a=bytearray(650000000);import time;time.sleep(5)'
sleep 5
test "$(systemctl show samo-memory-probe -p Result --value)" = oom-kill
systemctl show samo-memory-probe -p Result -p MemoryPeak
echo LINUX_APPLICATION_ACCEPTANCE_PASSED
