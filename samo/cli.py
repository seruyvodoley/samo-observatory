"""Offline command line. No experimental HTTP endpoints or remote deployment."""
import argparse
import json
import os
import secrets
import statistics
import tempfile
import time
from pathlib import Path
from .archive import Archive
from .engine import run_experiment, CONDITIONS, source_hash
from .exporter import export, export_csv, verify
from .genome import canonical, digest


def sealed_seeds(path, seeds):
    path = Path(path)
    if path.exists():
        payload = json.loads(path.read_text())
        if set(payload) != {str(s) for s in seeds}:
            raise ValueError('private seed manifest differs')
        return payload
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {str(seed): secrets.randbits(128) for seed in seeds}
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(payload, f)
    return payload


def replay(archive, private):
    original_runs, original_events, _ = verify(archive)
    with tempfile.TemporaryDirectory(prefix='samo-replay-') as directory:
        destination = Archive(Path(directory) / 'replay.sqlite')
        for r in original_runs:
            if r['status'] == 'interrupted':
                raise ValueError('interrupted replay requires completed continuation')
            if r['source_hash'] != source_hash():
                raise ValueError('source hash changed; use archived source version')
            repeated = run_experiment(destination, r['seed'], r['condition'], private[str(r['seed'])],
                                      r['attempt_limit'], r['fuel_ceiling'])
            if repeated['active_hash'] != r['active_hash']:
                raise ValueError('active genome replay mismatch')
        repeated_events = destination.all('events')
        def signature(e):
            return {k: e[k] for k in ('id', 'snapshot_hash', 'operator_hash', 'changes',
                                     'accepted', 'status', 'search_fuel', 'parent_ids')} | {
                'score': {k: v for k, v in e['score'].items() if k != 'cpu_seconds'}}
        if [signature(e) for e in original_events] != [signature(e) for e in repeated_events]:
            raise ValueError('event replay mismatch')
        for a, b in zip(original_runs, destination.all('runs')):
            for split in ('confirm', 'transfer'):
                if a.get(split, {}).get('behavior_hash') != b.get(split, {}).get('behavior_hash'):
                    raise ValueError('held-out replay mismatch')
        destination.close()
    return {'reproduced_runs': len(original_runs), 'reproduced_events': len(original_events),
            'genomes_and_predictions': 'exact', 'timing': 'excluded from equality'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', default='.private/release.sqlite')
    sub = p.add_subparsers(dest='command', required=True)
    pilot = sub.add_parser('pilot')
    pilot.add_argument('--seeds', default='17,41,93,137,211')
    pilot.add_argument('--conditions', default=','.join(CONDITIONS))
    pilot.add_argument('--attempts', type=int, default=60)
    pilot.add_argument('--fuel', type=int, default=1500000)
    pilot.add_argument('--private-seeds', default='.private/release-seeds-final.json')
    out = sub.add_parser('export')
    out.add_argument('--output', default='web/public/data/snapshot.json')
    out.add_argument('--csv', default='web/public/data/results.csv')
    sub.add_parser('audit')
    watch = sub.add_parser('watch', help='One continuous lineage, checkpointed; no resurrection on death')
    watch.add_argument('--seed', type=int, default=17)
    watch.add_argument('--attempts', type=int, default=1000000)
    watch.add_argument('--fuel', type=int, default=1000000000)
    watch.add_argument('--pause', type=float, default=5)
    watch.add_argument('--private-seeds', default='.private/watch-seeds.json')
    rep = sub.add_parser('replay')
    rep.add_argument('--private-seeds', default='.private/release-seeds-final.json')
    resume = sub.add_parser('resume')
    resume.add_argument('run_id')
    resume.add_argument('--private-seeds', default='.private/release-seeds-final.json')
    args = p.parse_args()
    archive = Archive(args.archive, read_only=args.command in ('export', 'audit', 'replay'))
    try:
        if args.command == 'watch':
            if args.pause < 0:
                raise ValueError('negative pause')
            private = sealed_seeds(args.private_seeds, [args.seed])
            existing = archive.all('runs')
            if len(existing) > 1:
                raise ValueError('watch requires its own archive with at most one lineage')
            run_id = existing[0]['id'] if existing else None
            if existing and existing[0]['status'] not in ('running', 'interrupted'):
                raise ValueError('lineage already terminated; watch never resurrects it')
            while True:
                started, cpu = time.monotonic(), time.process_time()
                run = run_experiment(archive, args.seed, 'samo', private[str(args.seed)],
                                     args.attempts, args.fuel, resume_id=run_id,
                                     protocol_path=Path(__file__).resolve().parents[1] / 'protocols/continuous-v1.json',
                                     checkpoint_steps=10)
                print(json.dumps({'id': run['id'], 'status': run['status'], 'attempts': run['attempts']}), flush=True)
                if run['status'] != 'interrupted':
                    break
                run_id = run['id']
                # Cooperative local pacing is NOT a cgroup or hard CPU guarantee.
                wait = max(args.pause, (time.process_time() - cpu) / .4 - (time.monotonic() - started))
                time.sleep(wait)
        elif args.command == 'pilot':
            seeds = [int(x) for x in args.seeds.split(',')]
            private = sealed_seeds(args.private_seeds, seeds)
            for seed in seeds:
                for condition in args.conditions.split(','):
                    run = run_experiment(archive, seed, condition, private[str(seed)], args.attempts, args.fuel)
                    print(json.dumps({k: run[k] for k in ('id', 'seed', 'condition', 'status', 'attempts', 'fuel', 'regressions')} |
                                     {'confirm_accuracy': run.get('confirm', {}).get('accuracy')}), flush=True)
        elif args.command == 'export':
            print(json.dumps(export(archive, args.output)))
            export_csv(archive, args.csv)
        elif args.command == 'audit':
            runs, events, evidence = verify(archive)
            print(json.dumps({'runs': len(runs), 'events': len(events), 'evidence': len(evidence), 'integrity': 'pass'}))
        elif args.command == 'replay':
            print(json.dumps(replay(archive, json.loads(Path(args.private_seeds).read_text()))))
        elif args.command == 'resume':
            r = next(r for r in archive.all('runs') if r['id'] == args.run_id)
            private = json.loads(Path(args.private_seeds).read_text())
            run = run_experiment(archive, r['seed'], r['condition'], private[str(r['seed'])], resume_id=r['id'])
            print(json.dumps({'id': run['id'], 'status': run['status']}))
    finally:
        archive.close()


if __name__ == '__main__':
    main()
