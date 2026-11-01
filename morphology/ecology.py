"""Versioned experimental co-inheritance adapter around the unchanged v4 computational engine.
Morphology is inherited on real computational births; it never changes prediction fitness.
"""
import copy,random
from samo.ecology_v4 import initial as core_initial,advance as core_advance
from .development import founder,mutate,develop,digest,VERSION
from .experiment import state_tuple
PROTOCOL='samo-ecology-morphology-experimental-1'
def initial(seed):return dict(protocol=PROTOCOL,core=core_initial(seed),traits={},rng=random.Random(seed^0x4D4F5250).getstate(),morphology_fuel=0)
def advance(previous):
 if previous['protocol']!=PROTOCOL:raise ValueError('protocol')
 s=copy.deepcopy(previous);core,event=core_advance(s['core']);rng=random.Random();rng.setstate(state_tuple(s['rng']));traits={};records=[]
 for form in core['population']:
  ident=form['id']
  if ident in s['traits']:traits[ident]=s['traits'][ident];continue
  parent=next((x for x in form['parents'] if x in s['traits']),None)
  base=s['traits'][parent]['morphology_genome'] if parent else founder()
  child,op=mutate(base,rng) if parent else (base,'registered_morphology_founder')
  result=develop(form['genome'],child);s['morphology_fuel']+=result['fuel']
  trait=dict(morphology_genome=child,morphology_hash=result['morphology_hash'],phenotype_hash=result['phenotype_hash'],interpreter=VERSION)
  traits[ident]=trait;records.append(dict(id=ident,parent=parent,parent_morphology_hash=digest(base) if parent else None,operator=op,morphology_changed=digest(base)!=digest(child),phenotype_changed=None if not parent else result['phenotype_hash']!=s['traits'][parent]['phenotype_hash'],computational_hash=digest(form['genome']),fuel=result['fuel'],truncated=result['truncated'],**trait))
 s.update(core=core,traits=traits,rng=rng.getstate());event=dict(protocol=PROTOCOL,computational=event,morphology=records,morphology_fuel=s['morphology_fuel'],state_hash=digest(s));return s,event
