"""Trusted, read-only scientific verifier with an external bounded immutable-record cache.
A cached record is reused only if BOTH compressed bytes and stored event hash are identical.
The cache belongs to the protected observer, never the evolving organism.
"""
import json,hashlib
from pathlib import Path
from .runtime_v5 import unpack,source_hash,public_form,PROTOCOL,PROTOCOL_HASH
from samo.genome_v4 import digest
from samo.engine import now
def verified_snapshot(recorder,cache):
    version=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()+source_hash()
    prior=cache.get("proofs",{}) if cache.get("version")==version else {}
    proofs={};hits=0
    outer_state=recorder.load()
    state=outer_state['core'] if outer_state else None
    if not state: raise ValueError('empty ecosystem')
    recent=[]
    for n,blob,h in recorder.db.execute('SELECT n,payload,hash FROM events ORDER BY n'):
        outer=unpack(blob)
        proof=h+':'+hashlib.sha256(blob).hexdigest();cached=prior.get(str(n))==proof
        if n!=outer['index'] or (not cached and digest(outer)!=h):raise ValueError('event integrity')
        proofs[str(n)]=proof;hits+=int(cached)
        e=outer['computational']
        # Validate the actual prequential commitments before projecting public results.
        results=[x['result'] for x in e['evaluations']]+([e['result']] if 'result' in e else [])
        for result in ([] if cached else results):
            rows=result['rows']
            for r in rows:
                if r['commitment']!=digest(dict(task_id=r['task_id'],index=r['index'],prediction=r['prediction'],prefix_hash=digest(r['prefix']))): raise ValueError('trial commitment')
                if r['correct']!=(r['prediction'] is not None and r['prediction']==r['target']): raise ValueError('trial score')
            if len(rows)!=result['total'] or abs(result['accuracy']-sum(r['correct'] for r in rows)/max(1,len(rows)))>1e-12: raise ValueError('aggregate score')
        recent.append({k:e[k] for k in ('index','episode','kind','family','task_index','status','accepted','changes','parent_ids','fuel_total','delta','birth','genotype_changed','behavior_changed','duplicate','external','search_error','meta_fuel','meta_scores') if k in e} |
                      dict(lifecycle=[{k:v for k,v in item.items() if k!='organism'} | (dict(id=item['organism']['id'],source=item['organism']['source']) if 'organism' in item else {}) for item in e['lifecycle']],
                           accuracy=e.get('result',{}).get('accuracy'), candidate_id=e.get('candidate',{}).get('id')))
    row=recorder.db.execute('SELECT payload FROM retention WHERE id=1').fetchone()
    retention=json.loads(row[0]) if row else dict(pruned_records=0,root=digest([]),through=-1)
    meta=recorder.db.execute('SELECT payload FROM metadata WHERE id=1').fetchone()
    cache.clear();cache.update(version=version,proofs=proofs,hits=hits,checked=len(proofs)-hits)
    return dict(schema=1,protocol=PROTOCOL,protocol_hash=PROTOCOL_HASH,generated_at=now(),observation=json.loads(meta[0]) if meta else {},
                step=state['step'],episode=state['episode'],attempts=state['attempts'],births=state['births'],deaths=state['deaths'],
                recolonizations=state['recolonizations'],fuel=state['fuel']+outer_state['morphology_fuel'],computational_fuel=state['fuel'],morphology_fuel=outer_state['morphology_fuel'],
                episodes=state['episodes'],episode_retention=state['episode_retention'],
                interventions=[json.loads(x[0]) for x in recorder.db.execute('SELECT payload FROM interventions ORDER BY id')],
                population=[public_form(x,outer_state['traits'][x['id']]) for x in state['population']],
                events=recent,retention=retention,claims=[],telemetry=dict(morphology_changes=outer_state['morphology_changes'],morphology_effects=outer_state['morphology_effects'],morphology_neutral=outer_state['morphology_neutral'],unique_genomes=len({digest(x['genome']) for x in state['population']}),genotype_changes=state['genotype_changes'],behavior_changes=state['behavior_changes'],search_errors=state['search_errors'],stagnant_attempts=state['stagnant_attempts'],last_change=state['last_change'],training_metric='exact-match; current selection tasks',independent_accuracy=None,capabilities_status='not independently assessed',new_capabilities=None,lost_capabilities=None,search_workability=(sum(not bool(e.get('search_error')) for e in recent if not e.get('external',True))/max(1,sum(not e.get('external',True) for e in recent))),search_workability_scope='retained endogenous attempts only'),
                limitations=['Training feedback only; no confirmed useful discoveries.',
                             'Raw trials retained for latest 1024 attempts; older records are explicitly thinned with a hash commitment. Private seed and archived source allow regeneration.',
                             'Infrastructure uptime, attempts and predictive capability are different measurements.'])

