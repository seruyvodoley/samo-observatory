#!/usr/bin/env python3
"""Run one preregistered v7 or v6-control seed/arm/budget replicate."""
from __future__ import annotations
import argparse,json,os,platform,resource,time
from pathlib import Path
from morphology.ecology_v6 import advance as advance6, initial as initial6
from morphology.ecology_v7 import ALL_ARMS, CONTROL, advance, initial, public_metrics
from morphology.runtime_v6 import Recorder as Recorder6, source_hash as source_hash6
from morphology.runtime_v7 import Recorder as Recorder7, source_hash as source_hash7
from samo.genome_v4 import digest

TIERS={"short":(100,150000,6_000_000_000),"medium":(400,600000,30_000_000_000),"long":(1600,2000000,120_000_000_000)}

def cgroup_value(name):
    root=Path('/sys/fs/cgroup')
    try:
        lines=Path('/proc/self/cgroup').read_text().splitlines()
        rel=next((line.split('::',1)[1].lstrip('/') for line in lines if '::' in line), '')
        group=root/rel
        while group==root or root in group.parents:
            try:return (group/name).read_text().strip()
            except OSError:pass
            if group==root:return None
            group=group.parent
    except OSError:
        pass
    return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True);p.add_argument('--arm',choices=ALL_ARMS,required=True)
    p.add_argument('--tier',choices=TIERS,required=True);p.add_argument('--db',required=True);p.add_argument('--summary',required=True)
    a=p.parse_args();steps_cap,fuel_cap,cpu_cap=TIERS[a.tier];db=Path(a.db)
    if a.arm==CONTROL:
        rec=Recorder6(db);rec.initialize(a.seed,arm='neutral');advance_fn=advance6;source=source_hash6()
    else:
        rec=Recorder7(db);rec.initialize(a.seed,arm=a.arm);advance_fn=advance;source=source_hash7()
    start=time.process_time_ns();peak_rss=0;stop_reason='step_limit'
    try:
        state=rec.load();start_step=state['core']['step']
        while True:
            total_fuel=state['core']['fuel']+state.get('morphology_fuel',0)
            elapsed=time.process_time_ns()-start
            if state['core']['step']-start_step>=steps_cap:stop_reason='step_limit';break
            if total_fuel>=fuel_cap:stop_reason='vm_fuel_limit';break
            if elapsed>=cpu_cap:stop_reason='cpu_time_limit';break
            state,event=advance_fn(state)
            rec.commit(state,event)
            try:
                for line in Path('/proc/self/status').read_text().splitlines():
                    if line.startswith('VmHWM:'):peak_rss=max(peak_rss,int(line.split()[1])*1024)
            except OSError:pass
        elapsed=time.process_time_ns()-start
        if a.arm==CONTROL:
            compute_state=state['core'];morph=state
            metrics={"active_unique_phenotype_hashes":len({t['phenotype_hash'] for t in state['traits'].values()}),
                     "active_niches":len({tuple(t['niche']) for t in state['traits'].values()}),
                     "morphology_births":state['morphology_births'],"morphology_changes":state['morphology_changes'],
                     "phenotype_effects":state['morphology_effects'],"sphere_returns":state['sphere_returns'],
                     "morphology_fuel":state['morphology_fuel']}
        else:
            compute_state=state['core'];morph=state;metrics=public_metrics(state)
        result={"seed":a.seed,"arm":a.arm,"tier":a.tier,"protocol_hash":state.get('protocol_hash'),
                "source_hash":source,"environment":{"python":platform.python_version(),"platform":platform.platform(),
                    "cpu_max":cgroup_value('cpu.max'),"memory_max":cgroup_value('memory.max'),
                    "swap_max":cgroup_value('memory.swap.max'),"tasks_max":cgroup_value('pids.max')},
                "start_step":start_step,"end_step":state['core']['step'],"steps":state['core']['step']-start_step,
                "stop_reason":stop_reason,"combined_fuel":compute_state['fuel']+morph.get('morphology_fuel',0),
                "compute_fuel":compute_state['fuel'],"morphology_fuel":morph.get('morphology_fuel',0),
                "process_cpu_ns":elapsed,"peak_rss_bytes":peak_rss,"database_bytes":db.stat().st_size,
                "checkpoint_hash":digest(state),"compute_state_hash":digest(compute_state),"metrics":metrics,
                "births":compute_state['births'],"deaths":compute_state['deaths'],"recolonizations":compute_state['recolonizations'],
                "episodes":compute_state['episodes']}
        Path(a.summary).parent.mkdir(parents=True,exist_ok=True)
        tmp=Path(a.summary).with_suffix('.tmp');tmp.write_text(json.dumps(result,sort_keys=True,separators=(',',':')));os.replace(tmp,a.summary)
        print(json.dumps(result,sort_keys=True))
    finally:rec.close()

if __name__=='__main__':main()
