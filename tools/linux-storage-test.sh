#!/usr/bin/env bash
set -euo pipefail
test "${SAMO_DISPOSABLE_VM:-}" = YES
img=/var/tmp/samo-capacity-test.img
mnt=/mnt/samo-capacity-test
test ! -e "$img"
test "$(df -B1 --output=avail /var/tmp | tail -1)" -gt 1300000000
fallocate -l 999997440 "$img"
loop=$(losetup --find --show "$img")
trap 'umount "$mnt" 2>/dev/null || true; losetup -d "$loop"' EXIT
mkfs.ext4 -q -F -m 0 -N 26752 "$loop"
mkdir -p "$mnt";mount -o nosuid,nodev,noexec "$loop" "$mnt"
stat -c 'IMAGE_BYTES=%s' "$img"
python3 - <<'PY'
import errno
from pathlib import Path
p=Path('/mnt/samo-capacity-test')
n=0
try:
    for i in range(40000):
        (p/str(i)).touch();n+=1
except OSError as e:
    assert e.errno==errno.ENOSPC
    print('INODE_ENOSPC_CONFIRMED created=',n)
else: raise RuntimeError('inode cap did not stop allocation')
for i in range(n): (p/str(i)).unlink()
PY
set +e
fallocate -l 1100000000 "$mnt/overfill.bin"
rc=$?
set -e
test "$rc" != 0
df -B1 "$mnt"
test "$(df -B1 --output=avail "$mnt" | tail -1)" -eq 0
echo BLOCK_ENOSPC_CONFIRMED
