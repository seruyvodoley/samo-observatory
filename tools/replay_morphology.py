import json,sqlite3,random
from pathlib import Path
from morphology.development import develop,digest,founder,mutate,bindings
from morphology.experiment import state_tuple
G=json.loads(Path('output/morphogenesis/computational.json').read_text());db=sqlite3.connect('output/morphogenesis/lines.sqlite');count=neutral=accepted=0
for line,n,raw in db.execute('SELECT line,n,payload FROM events ORDER BY line,n'):
 e=json.loads(raw);r=develop(G,e['morphology_genome']);assert r['phenotype_hash']==e['phenotype_hash'];assert r['morphology_hash']==e['morphology_hash'];assert {x['binding'] for x in r['phenotype']['nodes'] if not x['decorative']}=={b['id'] for b in bindings(G)}
 mode=line.split('/')[1];rng=random.Random();rng.setstate(state_tuple(e['rng_before']));child,op=(e['parent_genome'],'fixed') if mode=='fixed' else mutate(e['parent_genome'],rng,'parameter' if mode=='parameter' else 'generative')
 if mode=='structural' and op=='parameter':child=e['parent_genome']
 assert digest(child)==e['morphology_hash'];count+=1;neutral+=int(e['genotype_changed'] and not e['phenotype_changed']);accepted+=int(e['accepted'])
fork=json.loads(Path('output/morphogenesis/fork-history.json').read_text());ids={}
for e in fork:
 assert all(p in ids for p in e['parents']);assert develop(G,e['morphology_genome'])['phenotype_hash']==e['phenotype_hash'];ids[e['id']]=e
Path('output/morphogenesis/replay.json').write_text(json.dumps(dict(replayed=count,fork_events=len(fork),genotype_changes_without_appearance_change=neutral,accepted=accepted,mandatory_bindings_preserved=True),indent=2))
print(count,len(fork),neutral,accepted)
