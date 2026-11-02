#!/usr/bin/env python3
"""Run registered, seed-paired morphology policies on real v4 population births."""
import argparse, itertools, json, math, os, statistics, time
from pathlib import Path

from morphology.ecology_v6 import ARMS, advance, initial, public_metrics, PROTOCOL_HASH
from morphology.runtime_v6 import Recorder, source_hash
from samo.genome_v4 import digest

SEEDS = (314159, 271828, 161803, 141421, 173205, 223607, 244949, 264575)
FUEL_LIMIT = 2_000_000
CPU_LIMIT_NS = 6_000_000_000

def _exact_sign_p(values):
    nz=[x for x in values if x != 0]
    n=len(nz)
    if not n:return 1.0
    k=sum(x>0 for x in nz)
    return min(1.0,2*sum(math.comb(n,i) for i in range(min(k,n-k)+1))/2**n)

def run_one(root, seed, arm, step_limit):
    label=f"seed-{seed}-{arm}"
    db=root/(label+'.sqlite')
    rec=Recorder(db);rec.initialize(seed,arm=arm)
    state=rec.load();started=time.process_time_ns(); rows=[];core_hashes=[];founders=[];last_committed_cpu_ns=0
    status='step_ceiling'
    try:
        while state['core']['step']<step_limit:
            state,event=advance(state)
            rec.commit(state,event)
            committed_cpu_ns=time.process_time_ns()-started
            process_step_cpu_ns=committed_cpu_ns-last_committed_cpu_ns
            last_committed_cpu_ns=committed_cpu_ns
            compute=event['computational']
            core_hashes.append(digest(state['core']))
            if event['index']==0:
                founders=[digest(x['organism']['genome']) for x in compute.get('lifecycle',[]) if x.get('kind')=='founder']
            m=public_metrics(state)
            descriptors=[x['descriptor'] for x in state['traits'].values()]
            m['mean_spatial_span']=statistics.fmean([x['spatial_span'] for x in descriptors]) if descriptors else 0.0
            results=[x['result'] for x in compute.get('evaluations',[])]+([compute['result']] if 'result' in compute else [])
            scores=[x['accuracy'] for x in results if isinstance(x.get('accuracy'),(int,float))]
            rows.append({'step':state['core']['step'],'unique_forms':m['active_unique_forms'],
                         'active_niches':m['occupied_active_niches'],'archive_niches':m['bounded_archive_niches'],
                         'mean_spatial_span':m['mean_spatial_span'],'sphere_returns':m['sphere_returns'],
                         'max_retention':m['max_structural_retention_steps'],'morphology_fuel':m['morphology_fuel'],
                         'compute_fuel':state['core']['fuel'],'total_vm_fuel':state['core']['fuel']+state['morphology_fuel'],
                         'transition_cpu_ns':event['cpu_ns'],'process_cpu_ns':committed_cpu_ns,
                         'process_step_cpu_ns':process_step_cpu_ns,
                         'recolonizations':state['core']['recolonizations'],
                         'active_compute_accuracy':statistics.fmean(scores) if scores else None})
            cpu=committed_cpu_ns
            fuel=state['core']['fuel']+state['morphology_fuel']
            if cpu>=CPU_LIMIT_NS:
                status='cpu_budget';break
            if fuel>=FUEL_LIMIT:
                status='vm_fuel_budget';break
        metrics=public_metrics(state)
        summary={'seed':seed,'arm':arm,'status':status,'steps':state['core']['step'],
                 'compute_path_hash':digest(core_hashes),'compute_path_hashes':core_hashes,
                 'founder_genome_hashes':founders,
                 'births':state['core']['births'],'deaths':state['core']['deaths'],
                 'natural_recolonizations':state['core']['recolonizations'],
                 'compute_fuel':state['core']['fuel'],'morphology_fuel':state['morphology_fuel'],
                 'total_vm_fuel':state['core']['fuel']+state['morphology_fuel'],
                  'cpu_ns':time.process_time_ns()-started,'max_single_step_cpu_ns':max((x['transition_cpu_ns'] for x in rows),default=0),
                 'mean_unique_active_forms':statistics.fmean(x['unique_forms'] for x in rows),
                 'mean_active_niches':statistics.fmean(x['active_niches'] for x in rows),
                 'mean_spatial_span':statistics.fmean(x['mean_spatial_span'] for x in rows),
                 'sphere_returns':metrics['sphere_returns'],'max_structural_retention_steps':metrics['max_structural_retention_steps'],
                 'final_active_unique_forms':metrics['active_unique_forms'],
                 'final_active_niches':metrics['occupied_active_niches'],
                 'final_training_accuracy':next((x['active_compute_accuracy'] for x in reversed(rows) if x['active_compute_accuracy'] is not None),None),
                 'event_rows':len(rows),'checkpoint_hash':digest(state)}
        return summary, rows
    finally:rec.close()

def summarize(rows):
    out={}
    for arm in ARMS:
        vals=[x['final_active_unique_forms'] for x in rows if x['arm']==arm]
        means=[x['mean_unique_active_forms'] for x in rows if x['arm']==arm]
        out[arm]={'n':len(vals),'primary_final_mean':statistics.fmean(vals),'primary_final_sd':statistics.stdev(vals) if len(vals)>1 else 0,
                  'primary_final_median':statistics.median(vals),'primary_final_per_seed':{str(x['seed']):x['final_active_unique_forms'] for x in rows if x['arm']==arm},
                  'secondary_mean_over_attempts':statistics.fmean(means),'per_replicate_cpu_ns':{str(x['seed']):x['cpu_ns'] for x in rows if x['arm']==arm},
                  'per_replicate_vm_fuel':{str(x['seed']):x['total_vm_fuel'] for x in rows if x['arm']==arm}}
    contrasts={}
    ref={x['seed']:x for x in rows if x['arm']=='neutral'}
    for arm in ('novelty','bounded_archive_diversity'):
        alt={x['seed']:x for x in rows if x['arm']==arm}
        diffs=[alt[s]['final_active_unique_forms']-ref[s]['final_active_unique_forms'] for s in SEEDS if s in ref and s in alt]
        contrasts[f'{arm}-minus-neutral']={'n':len(diffs),'mean_paired_difference':statistics.fmean(diffs) if diffs else None,
               'paired_differences':diffs,'exact_two_sided_sign_p':_exact_sign_p(diffs)}
    out['paired_contrasts']=contrasts
    checks=[]
    for seed in SEEDS:
        cohort=[x for x in rows if x['seed']==seed]
        if len(cohort)!=len(ARMS):checks.append(False);continue
        common=min(len(x['compute_path_hashes']) for x in cohort)
        checks.append(all(len({x['compute_path_hashes'][i] for x in cohort})==1 for i in range(common)))
    out['compute_paths_identical_within_common_prefix']=all(checks)
    out['common_prefix_steps_by_seed']={str(seed):min(x['steps'] for x in rows if x['seed']==seed) for seed in SEEDS if any(x['seed']==seed for x in rows)}
    return out

def common_budget_analysis(summaries, series):
    arms=ARMS; lookup={(x['seed'],x['arm']):x['rows'] for x in series}; selected=[]
    for seed in sorted({x['seed'] for x in summaries}):
        cohort=[x for x in summaries if x['seed']==seed]
        cpu_cap=min(x['cpu_ns'] for x in cohort)
        fuel_cap=min(x['total_vm_fuel'] for x in cohort)
        for arm in arms:
            candidates=[r for r in lookup[(seed,arm)] if r['process_cpu_ns']<=cpu_cap and r['total_vm_fuel']<=fuel_cap]
            row=candidates[-1] if candidates else None
            selected.append({'seed':seed,'arm':arm,'common_cpu_cap_ns':cpu_cap,'common_vm_fuel_cap':fuel_cap,
                             'step':row['step'] if row else 0,'unique_active_forms':row['unique_forms'] if row else 0,
                             'active_niches':row['active_niches'] if row else 0,
                             'process_cpu_ns':row['process_cpu_ns'] if row else 0,
                             'vm_fuel':row['total_vm_fuel'] if row else 0,
                             'overshoot_ceiling_ns':row['process_step_cpu_ns'] if row else 0})
    result={}
    for arm in arms:
        rows=[x for x in selected if x['arm']==arm]
        vals=[x['unique_active_forms'] for x in rows]
        result[arm]={'n':len(vals),'mean':statistics.fmean(vals),'sd':statistics.stdev(vals) if len(vals)>1 else 0,
                     'per_seed':{str(x['seed']):x for x in rows}}
    contrasts={};ref={x['seed']:x for x in selected if x['arm']=='neutral'}
    for arm in arms[1:]:
        alt={x['seed']:x for x in selected if x['arm']==arm}
        differences=[alt[s]['unique_active_forms']-ref[s]['unique_active_forms'] for s in ref]
        contrasts[f'{arm}-minus-neutral']={'n':len(differences),'mean_paired_difference':statistics.fmean(differences),
            'paired_differences':differences,'exact_two_sided_sign_p':_exact_sign_p(differences)}
    result['paired_contrasts']=contrasts
    result['endpoint_rule']='last committed transition at or below the per-seed minimum realized process CPU and combined VM fuel across arms'
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--steps',type=int,default=600);ap.add_argument('--seeds',type=int,nargs='*',default=SEEDS)
    args=ap.parse_args();root=Path(args.root);root.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(Path('protocols/v6-diversity-comparison.json').read_text())
    amendments=[json.loads(Path(f'protocols/v6-diversity-comparison-amendment-{n}.json').read_text()) for n in (1,2,3)]
    manifest['registered_amendments']=amendments
    manifest.update({'protocol_hash':digest(manifest),'source_hash':source_hash(),'v6_protocol_hash':PROTOCOL_HASH,
                     'steps_requested':args.steps,'seeds_run':args.seeds,'started_cpu_ns':time.process_time_ns(),
                     'environment':{'python':os.sys.version,'platform':os.sys.platform}})
    (root/'protocol.json').write_text(json.dumps(manifest,sort_keys=True,indent=2))
    summaries=[];series=[]
    for seed in args.seeds:
        for arm in ARMS:
            summary,rows=run_one(root,seed,arm,args.steps);summaries.append(summary)
            series.append({'seed':seed,'arm':arm,'rows':rows})
            print(json.dumps({'seed':seed,'arm':arm,'steps':summary['steps'],'births':summary['births'],
                              'recolonizations':summary['natural_recolonizations'],'fuel':summary['total_vm_fuel'],
                              'cpu_ns':summary['cpu_ns'],'mean_forms':summary['mean_unique_active_forms']},sort_keys=True),flush=True)
    result={'protocol':manifest,'runs':summaries,'analysis':summarize(summaries),
            'exact_common_budget_analysis':common_budget_analysis(summaries,series)}
    result['result_hash']=digest(result)
    (root/'results.json').write_text(json.dumps(result,sort_keys=True,indent=2))
    (root/'timeseries.json').write_text(json.dumps(series,separators=(',',':')))
    print(json.dumps({'result_hash':result['result_hash'],'summary':result['analysis']},sort_keys=True),flush=True)

if __name__=='__main__':main()
