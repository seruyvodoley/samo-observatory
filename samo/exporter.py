"""Read-only public snapshot boundary: integrity checks, bounded schema, atomic write."""
import csv
import io
import json
import os
from pathlib import Path
from .engine import now
from .genome import canonical, digest

MAX_SNAPSHOT = 4_000_000


def public_run(run):
    keys = ('id', 'seed', 'condition', 'protocol_id', 'protocol_hash', 'source_hash',
            'environment', 'started_at', 'observed_at', 'status', 'fuel_ceiling', 'fuel',
            'attempt_limit', 'attempts', 'accepted', 'regressions', 'active_id', 'active_hash',
            'best_accuracy', 'latest_score', 'cpu_seconds', 'wall_seconds', 'peak_rss_bytes',
            'confirm', 'transfer', 'validation', 'baselines', 'os_isolation')
    return {key: run[key] for key in keys if key in run}


def verify(archive):
    runs, events = archive.all('runs'), archive.all('events')
    evidence = []
    for ev in archive.iter_records('evidence'):
        for row in ev['result']['rows']:
            expected = digest({'task_id': row['task_id'], 'index': row['index'],
                               'prediction': row['prediction'], 'prefix_hash': digest(row['prefix'])})
            if row['commitment'] != expected:
                raise ValueError('prediction commitment mismatch')
            if row['correct'] != (row['prediction'] is not None and row['prediction'] == row['target']):
                raise ValueError('score mismatch')
        # Stream raw trials; observer memory does not scale with all raw rows.
        result = ev['result']
        rows = result['rows']
        if rows:
            if result['total'] != len(rows) or abs(result['accuracy'] - sum(r['correct'] for r in rows) / len(rows)) > 1e-12:
                raise ValueError('aggregate accuracy mismatch')
            if result['fuel'] != sum(r['fuel'] for r in rows) or result['failures'] != sum(r['status'] != 'ok' for r in rows):
                raise ValueError('aggregate cost or failures mismatch')
        ev['result']['rows'] = []
        evidence.append(ev)
    run_map = {r['id']: r for r in runs}
    ev_map = {e['id']: e for e in evidence}
    seen = {}
    for run in runs:
        if digest(run['protocol']) != run['protocol_hash']:
            raise ValueError('protocol hash mismatch')
        archive.artifact(run['active_hash'])
    for e in events:
        if e['id'] in seen or e['run_id'] not in run_map:
            raise ValueError('duplicate event or missing run')
        run = run_map[e['run_id']]
        if e['protocol_hash'] != run['protocol_hash']:
            raise ValueError('protocol mismatch')
        for parent in e['parent_ids']:
            if parent not in seen or seen[parent]['run_id'] != e['run_id']:
                raise ValueError('missing parent, cross-run edge or cycle')
            if seen[parent]['ordinal'] >= e['ordinal']:
                raise ValueError('noncausal edge')
        genome = archive.artifact(e['snapshot_hash'])
        if digest(genome['dialect']) != e['runtime_hash'] or digest(genome['search']) != e['search_hash'] or digest(genome['memory']) != e['memory_hash']:
            raise ValueError('component hash mismatch')
        ev = ev_map.get(e['evidence_id'])
        if not ev or ev['snapshot_hash'] != e['snapshot_hash'] or ev['run_id'] != e['run_id']:
            raise ValueError('missing or mismatched evidence')
        if e['score'] != {k: v for k, v in ev['result'].items() if k != 'rows'}:
            raise ValueError('event score differs from evidence')
        if e['parent_ids']:
            parent_g = archive.artifact(seen[e['parent_ids'][0]]['snapshot_hash'])
            from .genome import ancestor
            operator = ancestor()['search'] if run['condition'] in ('gp', 'random') else parent_g['search']
            if digest(operator) != e['operator_hash']:
                raise ValueError('executed operator provenance mismatch')
        seen[e['id']] = e
    for run in runs:
        active = seen.get(run['active_id'])
        if not active or active['run_id'] != run['id'] or active['snapshot_hash'] != run['active_hash']:
            raise ValueError('active state reference mismatch')
    for ev in evidence:
        run = run_map.get(ev['run_id'])
        if not run or run['protocol_hash'] != ev['protocol_hash']:
            raise ValueError('evidence protocol mismatch')
        archive.artifact(ev['snapshot_hash'])
        for row in ev['result']['rows']:
            expected = digest({'task_id': row['task_id'], 'index': row['index'],
                               'prediction': row['prediction'], 'prefix_hash': digest(row['prefix'])})
            if row['commitment'] != expected:
                raise ValueError('prediction commitment mismatch')
            if row['correct'] != (row['prediction'] is not None and row['prediction'] == row['target']):
                raise ValueError('score mismatch')
    return runs, events, evidence


def build_snapshot(archive):
    runs, events, evidence = verify(archive)
    if len(events) > 2000:
        raise ValueError('public snapshot node limit; create explicitly segmented archive')
    public_events = [{k: v for k, v in e.items() if k != 'rng_before'} for e in events]
    used = {e['snapshot_hash'] for e in events} | {r['active_hash'] for r in runs}
    artifacts = {h: archive.artifact(h) for h in sorted(used)}
    pub_evidence = [{k: v for k, v in ev.items() if k != 'result'} |
                    {'result': {k: v for k, v in ev['result'].items() if k != 'rows'}} for ev in evidence]
    latest = max((r['observed_at'] for r in runs), default=None)
    source_status = ('running' if any(r['status'] == 'running' for r in runs) else 'stopped') if runs else 'empty'
    data = {'schema_version': 1, 'generated_at': now(), 'latest_observation_at': latest,
            'source_status': source_status, 'archive_complete': True, 'truncated': False,
            'source_run_ids': [r['id'] for r in runs], 'runs': [public_run(r) for r in runs],
            'events': public_events, 'artifacts': artifacts, 'evidence': pub_evidence,
            'claims': [], 'protocols': list({r['protocol_hash']: r['protocol'] for r in runs}.values()),
            'budget': {'cpu_fraction': 0.4, 'memory_bytes': 256000000,
                       'organism_storage_bytes': 1000000000, 'archive_bytes': 64000000,
                       'os_enforced': False},
            'limitations': ['Local pilot only; Linux isolation not accepted.',
                            'No confirmed inventions; language pathway is tested, emergence unproven.',
                            'Same fuel ceiling, unequal actual cost; no superiority claim.',
                            'Public snapshot excludes sealed task seeds, raw holdout and RNG.']}
    data['snapshot_hash'] = digest(data)
    if len(canonical(data)) > MAX_SNAPSHOT:
        raise ValueError('snapshot byte limit')
    return data


def export(archive, destination):
    data = build_snapshot(archive)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('wb') as f:
        f.write(canonical(data))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return {'snapshot_hash': data['snapshot_hash'], 'bytes': path.stat().st_size,
            'runs': len(data['runs']), 'events': len(data['events'])}


def export_csv(archive, destination):
    runs, _, _ = verify(archive)
    fields = ['run_id', 'seed', 'condition', 'status', 'confirm_accuracy', 'transfer_accuracy',
              'attempts', 'accepted', 'regressions', 'fuel', 'cpu_seconds', 'wall_seconds', 'peak_rss_bytes']
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in runs:
            row = {k: r.get(k) for k in fields if k in r}
            row.update(run_id=r['id'], confirm_accuracy=r.get('confirm', {}).get('accuracy', 0),
                       transfer_accuracy=r.get('transfer', {}).get('accuracy', 0))
            writer.writerow(row)
