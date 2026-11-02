"""Read-only scientific source-to-public phenotype verifier, under the observer budget."""
import json,sys
from pathlib import Path
from morphology.runtime_v5 import Recorder,unpack
from morphology.development import develop,digest
p=json.loads(Path(sys.argv[2]).read_text());assert p['protocol']=='samo-ecology-v5-morphology';r=Recorder(sys.argv[1],readonly=True);births={}
for n,blob,h in r.db.execute('SELECT n,payload,hash FROM events ORDER BY n'):
 e=unpack(blob);assert digest(e)==h
 for x in e['morphology']:births[x['id']]=x
checked=0;outside=[]
for form in p['population']+p.get('history',[]):
 internal='v4-'+form['id'][3:];record=births.get(internal)
 if record is None:outside.append(form['id']);continue
 assert digest(form['genome'])==record['computational_hash'];assert digest(form['morphology']['morphology_genome'])==record['morphology_hash'];assert form['morphology']['phenotype_hash']==record['phenotype_hash']
 result=develop(form['genome'],record['morphology_genome']);assert result['phenotype_hash']==form['morphology']['phenotype_hash'];checked+=1
f=p['population'][0] if p['population'] else None
shape=None
if f:
 anchors=[n for n in f['morphology']['phenotype']['nodes'] if not n['decorative']];shape=dict(id=f['id'],anchors=len(anchors),distinct_anchor_positions=len({tuple(n['position']) for n in anchors}),morphology_program=f['morphology']['morphology_genome'])
print(json.dumps(dict(public_step=p['step'],recorder_step=r.load()['core']['step'],verified_forms=checked,outside_raw_window=outside,selected_shape=shape)));r.close()
