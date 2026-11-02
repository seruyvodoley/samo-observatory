import sqlite3,zlib,json,statistics
from collections import Counter
from samo.ecology import initial,advance
from samo.evaluator import evaluate,tasks
from samo.genome import digest
s=json.loads(zlib.decompress(sqlite3.connect('.private/vps-replay.sqlite').execute('SELECT payload FROM checkpoint').fetchone()[0]));state=initial(s['seed'],s['size'])
c=Counter();bits=[];errors=[];operators=set()
for _ in range(1014):
 state,e=advance(state);c['attempts']+=1;operators.add(e['operator_hash'])
 c['sterile']+=e.get('status')=='sterile'
 if 'candidate' not in e:continue
 c['candidates']+=1;c['accepted']+=e['accepted'];c['zero_accuracy']+=e['result']['accuracy']==0;c['nonzero_accuracy']+=e['result']['accuracy']>0;c['nonzero_delta']+=e['delta']!=0
 rows=e['result']['rows'];bits.append(sum(0 if x['prediction'] is None else 16-(x['prediction']^x['target']).bit_count() for x in rows)/(16*len(rows)));errors.append(e['result']['mae'])
probe=tasks(9057331)
behaviors=[evaluate(x['genome'],probe,'diagnostic',deterministic=True)['behavior_hash'] for x in state['population']]
result=dict(counts=dict(c),bit_accuracy_range=[min(bits),max(bits)],mae_range=[min(errors),max(errors)],distinct_search_operators=len(operators),genotype_diversity=len({digest(x['genome']) for x in state['population']}),common_probe_behavior_diversity=len(set(behaviors)),interpretation='With exact-match ties delta=0, Metropolis acceptance is 1. This is protocol-driven neutral drift, not evidence of useful improvement. Dense diagnostic metrics are not a tested replacement selector; no v3 superiority claim or live selection change.')
print(json.dumps(result,indent=2));open('output/fitness-audit.json','w').write(json.dumps(result,indent=2))
