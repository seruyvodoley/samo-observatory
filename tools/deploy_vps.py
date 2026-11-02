"""Deploy the built, static observatory to its read-only VPS origin.

The live ecosystem snapshot is produced on the VPS and is deliberately excluded
from this sync so a frontend release cannot replace newer scientific data.
"""
import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The deployment key is restricted to this directory by rrsync, so the remote
# path must be relative to its locked root.
DEST = "./"


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


parser = argparse.ArgumentParser(description="Deploy the reviewed observatory build to the VPS.")
parser.add_argument("--build", action="store_true", help="build the web app before deployment")
parser.add_argument("--host", default=os.environ.get("SAMO_DEPLOY_HOST"), help="SSH destination, or set SAMO_DEPLOY_HOST")
parser.add_argument("--identity", default=os.environ.get("SAMO_DEPLOY_IDENTITY"), help="SSH identity file; otherwise use the SSH agent/config")
args = parser.parse_args()

if not args.host:
    parser.error("set --host or SAMO_DEPLOY_HOST")

if args.build:
    run("npm", "run", "build", "--prefix", "web")

dist = ROOT / "web" / "dist"
if not (dist / "index.html").is_file():
    raise SystemExit("web/dist/index.html is missing; build the website first")
ssh = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes"]
rsync_ssh = "ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes"
if args.identity:
    identity = Path(args.identity).expanduser()
    if not identity.is_file():
        raise SystemExit("The selected SSH identity is unavailable")
    ssh += ["-i", str(identity)]
    rsync_ssh += " -i " + str(identity)
run(*ssh, args.host, "test -d /srv/samo/site/data && test -f /srv/samo/site/data/ecosystem.json")
run(
    "rsync", "-rtzp", "--exclude=/data/***",
    "-e", rsync_ssh,
    str(dist) + "/", args.host + ":" + DEST,
)
print("Static observatory deployed without deleting files or replacing VPS scientific data.")
