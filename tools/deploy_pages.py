"""Operator-only deploy using the publisher's current OAuth access token over authenticated SSH.
Never prints credentials; never hands them to organism programs. The publisher is the
canonical OAuth session: a separate local Wrangler login can invalidate its rotating
refresh credential, so deploys must use this helper instead of local `wrangler login`.
"""
import json
import os
import subprocess
import argparse

parser=argparse.ArgumentParser(description='Publish reviewed static files to the existing SAMO Cloudflare Pages project.')
parser.add_argument('--whoami',action='store_true',help='verify the stored publisher authorization without deploying')
parser.add_argument('--list',action='store_true',help='list existing Pages deployments without deploying')
parser.add_argument('--branch',choices=['main','redesign-preview'],default='main',help='Pages branch to deploy')
args=parser.parse_args()

credentials=json.loads(subprocess.check_output(['ssh','-i',os.path.expanduser('~/.ssh/tunneldeck_ed25519'),'-o','BatchMode=yes',
                                              'root@10.68.0.1','cat /srv/samo/publisher/oauth.json']))
env=os.environ.copy();env['CLOUDFLARE_API_TOKEN']=credentials['access_token'];env['CLOUDFLARE_ACCOUNT_ID']='b999769911d82e5e2d6de5c278921c24'
wrangler=['npx','--yes','wrangler@4.156.0']
if args.whoami:
    subprocess.run([*wrangler,'whoami'],env=env,check=True)
elif args.list:
    subprocess.run([*wrangler,'pages','deployment','list','--project-name','samo-observatory'],env=env,check=True)
else:
    subprocess.run([*wrangler,'pages','deploy','web/dist','--project-name','samo-observatory','--branch',args.branch,'--commit-dirty=true'],env=env,check=True)
