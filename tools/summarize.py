"""Descriptive run-level analysis. No generation-level pseudo-replication or p-values."""
import json
import statistics
from pathlib import Path
from samo.archive import Archive

root=Path(__file__).resolve().parents[1]
archive=Archive(root/'.private/release.sqlite',read_only=True)
runs=archive.all('runs');events=archive.all('events')
summary={'snapshot_hash':json.loads((root/'web/public/data/snapshot.json').read_text())['snapshot_hash'],
         'runs':len(runs),'events':len(events),'conditions':{},'accepted_changes':{},
         'cpu_seconds':sum(r['cpu_seconds'] for r in runs),
         'wall_seconds':sum(r['wall_seconds'] for r in runs),
         'peak_rss_bytes':max(r['peak_rss_bytes'] for r in runs),
         'archive_bytes':archive.path.stat().st_size,
         'sources':sorted(set(r['source_hash'] for r in runs))}
for c in ('fixed','random','gp','meta','samo'):
    rs=[r for r in runs if r['condition']==c]
    values=[r.get('confirm',{}).get('accuracy',0) for r in rs]
    summary['conditions'][c]={'independent_n':len(rs),'confirm_mean':statistics.mean(values),
        'confirm_min':min(values),'confirm_max':max(values),
        'transfer_mean':statistics.mean(r.get('transfer',{}).get('accuracy',0) for r in rs),
        'sterile':sum(r['status']=='sterile' for r in rs),
        'regressions':sum(r['regressions'] for r in rs),'fuel':sum(r['fuel'] for r in rs),
        'confirm_values':values,'seeds':[r['seed'] for r in rs]}
for c in ('modules','search','dialect','memory','router','architecture'):
    summary['accepted_changes'][c]=sum(e['accepted'] and c in e['changes'] for e in events)
summary['expert_baseline_mean']=statistics.mean(r['baselines']['expert']['accuracy'] for r in runs)
archive.close()
(root/'output/experiment-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
