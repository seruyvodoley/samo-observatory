"""Neutral morphology co-inheritance on real computational births. Versioned independently."""
import copy,json,random
from pathlib import Path
from samo.ecology_v4 import initial as core_initial,advance as core_advance
from samo.engine import state_tuple
from .development import founder,mutate,develop,digest,validate,VERSION
PROTOCOL='samo-ecology-v5-morphology'
PROTOCOL_HASH=digest(json.loads((Path(__file__).resolve().parents[1]/'protocols/ecology-v5-morphology.json').read_text()))
def initial(seed):
 return dict(protocol=PROTOCOL,protocol_hash=PROTOCOL_HASH,core=core_initial(seed),traits={},rng=random.Random(seed^0x4D4F5250).getstate(),morphology_fuel=0,morphology_changes=0,morphology_effects=0,morphology_neutral=0)
def advance(previous):
 if previous['protocol']!=PROTOCOL or previous['protocol_hash']!=PROTOCOL_HASH:raise ValueError('morphology protocol')
 s=copy.deepcopy(previous);core,event=core_advance(s['core']);rng=random.Random();rng.setstate(state_tuple(s['rng']));available=dict(s['traits']);records=[]
 births=[i['organism'] for i in event['lifecycle'] if i['kind']=='founder']+([event['candidate']] if event.get('candidate') else [])
 for form in births:
  parent=next((i for i in form['parents'] if i in available),None)
  if form['parents'] and parent is None:raise ValueError('missing morphological parent')
  base=available[parent]['morphology_genome'] if parent else founder()
  child,op=mutate(base,rng) if parent else (base,'registered_morphology_founder')
  result=develop(form['genome'],child);changed=digest(base)!=digest(child)
  counter=develop(form['genome'],base) if parent and changed else result
  fuel=result['fuel']+(counter['fuel'] if counter is not result else 0);s['morphology_fuel']+=fuel
  effect=bool(parent and result['phenotype_hash']!=counter['phenotype_hash']);s['morphology_changes']+=int(changed);s['morphology_effects']+=int(effect);s['morphology_neutral']+=int(changed and not effect)
  trait=dict(morphology_genome=child,morphology_hash=result['morphology_hash'],phenotype_hash=result['phenotype_hash'],interpreter=VERSION)
  available[form['id']]=trait
  records.append(dict(id=form['id'],parent=parent,parent_morphology_hash=digest(base) if parent else None,operator=op,morphology_changed=changed,morphology_effect=effect,computational_effect=None if not parent else counter['phenotype_hash']!=available[parent]['phenotype_hash'],phenotype_changed=None if not parent else result['phenotype_hash']!=available[parent]['phenotype_hash'],computational_hash=digest(form['genome']),fuel=fuel,truncated=result['truncated'],**trait))
 s.update(core=core,traits={x['id']:available[x['id']] for x in core['population']},rng=rng.getstate())
 e=dict(index=event['index'],protocol=PROTOCOL,protocol_hash=PROTOCOL_HASH,computational=event,morphology=records,morphology_fuel=s['morphology_fuel'],state_hash=digest(s))
 return s,e
