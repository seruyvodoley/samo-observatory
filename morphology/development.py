"""Capability-free graph development interpreter. Integer-only serialized genome."""
import copy, hashlib, json, math
VERSION='samo-morphogenesis-1'
LIMITS=dict(rules=16, instructions=32, fuel=2048, nodes=256, depth=8, coordinate=32)
OPS=('move','turn','scale','emit','call','repeat','data','material')
def digest(x):
 return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def founder():
 return dict(version=1,root=0,rules=[dict(id=0,instruction_ids=[0,1],code=[[6,0,8,0],[3,0,0,0]])],next_id=1,next_instruction_id=2)
def validate(g):
 if not isinstance(g,dict) or g.get('version')!=1: raise ValueError('morphology version')
 rules=g.get('rules');root=g.get('root')
 if not isinstance(rules,list) or not 1<=len(rules)<=16: raise ValueError('rule limit')
 ids=[];instruction_ids=[]
 for r in rules:
  if not isinstance(r,dict) or type(r.get('id')) is not int or not 0<=r['id']<=65535:raise ValueError('rule id')
  ids.append(r['id']);code=r.get('code')
  if not isinstance(code,list) or len(code)>32:raise ValueError('instruction limit')
  ii=r.get('instruction_ids')
  if not isinstance(ii,list) or len(ii)!=len(code) or any(type(v)is not int or not 0<=v<=65535 for v in ii):raise ValueError('instruction identity')
  instruction_ids.extend(ii)
  for i in code:
   if not isinstance(i,list) or len(i)!=4 or any(type(v)is not int or abs(v)>32767 for v in i) or not 0<=i[0]<8:raise ValueError('instruction')
 if len(set(ids))!=len(ids) or root not in ids or type(g.get('next_id'))is not int or not max(ids)<g['next_id']<=65536:raise ValueError('rule identity')
 if len(set(instruction_ids))!=len(instruction_ids) or type(g.get('next_instruction_id'))is not int or not max(instruction_ids,default=-1)<g['next_instruction_id']<=65536:raise ValueError('instruction identity counter')
 return g
def bindings(g):
 if not isinstance(g,dict):raise ValueError('architecture')
 for key,limit in [('modules',8),('dialect',4)]:
  if not isinstance(g.get(key),list) or len(g[key])>limit:raise ValueError('architecture list')
 for code in g['modules']+g['dialect']+[g.get('router'),g.get('search')]:
  if not isinstance(code,list) or len(code)>96 or any(not isinstance(i,list) or len(i)!=2 or any(type(v)is not int or abs(v)>65535 for v in i) for i in code):raise ValueError('architecture code')
 if not isinstance(g.get('memory'),list) or len(g['memory'])>64 or any(type(v)is not int or not 0<=v<=65535 for v in g['memory']):raise ValueError('architecture memory')
 out=[]
 for part,codes in [('module',g['modules']),('router',[g['router']]),('search',[g['search']]),('dialect',g['dialect']),('memory',[g['memory']])]:
  for i,c in enumerate(codes):out.append(dict(id=f'{part}:{i}',part=part,index=i,count=len(c)))
 return out
def develop(computational,morph):
 validate(morph);bs=bindings(computational)
 if len(bs)>16:raise ValueError('architecture limit')
 rules={r['id']:r['code'] for r in morph['rules']};nodes=[];edges=[];used=0;truncated=False
 def node(identity,b,p,s,shape,material,decor,parent=None):
  nonlocal truncated
  if len(nodes)>=256:truncated=True;return None
  x=dict(id=identity,binding=b['id'],position=[round(max(-32,min(32,v)),6) for v in p],scale=round(max(.05,min(3,s)),6),shape=shape%4,material=material%360,decorative=decor)
  nodes.append(x)
  if parent:edges.append([parent,identity])
  return identity
 def run(rule,b,ordinal,path,p,s,angle,mat,depth,parent):
  nonlocal used,truncated
  if depth>=8:truncated=True;return
  for k,(op,a,c,d) in enumerate(rules.get(rule,[])):
   if used>=2048 or len(nodes)>=256:truncated=True;return
   used+=1;tag=f'{path}/r{rule}:i{next(r["instruction_ids"][k] for r in morph["rules"] if r["id"]==rule)}'
   if op==0:p=[p[0]+a/16*math.cos(angle)-c/16*math.sin(angle),p[1]+a/16*math.sin(angle)+c/16*math.cos(angle),p[2]+d/16]
   elif op==1:angle+=a*math.pi/128
   elif op==2:s=max(.05,min(3,s*(1+a/128)))
   elif op==3:
    parent=node(tag,b,p,s*(1+min(b['count'],96)/192),a,mat,True,parent)
   elif op==4:run(a,b,ordinal,tag,p[:],s,angle,mat,depth+1,parent)
   elif op==5:
    for j in range(min(4,abs(c)%5)):
     run(a,b,ordinal,tag+f'/copy{j}',p[:],s,angle+j*d*math.pi/128,mat,depth+1,parent)
   elif op==6:
    v=[ordinal,b['count'],len(bs),len(computational['memory'])][abs(a)%4]
    p[abs(d)%3]+=v*c/16
   elif op==7:mat=a%360
  return p,s,mat
 # Mandatory binding anchors cannot be erased by a development program. Decorations are explicitly separate.
 for ordinal,b in enumerate(bs):
  start=len(nodes)
  result=run(morph['root'],b,ordinal,b['id'],[0.,0.,0.],.35,0.,ordinal*37,0,None)
  p,s,mat=result if result else ([0.,0.,0.],.2,0)
  # Reserve room for every remaining required component even when ornament fuel/nodes exhaust.
  while len(nodes)>=256-(len(bs)-ordinal):nodes.pop();truncated=True
  anchor=node(b['id'],b,p,s,0,mat,False)
  if len(nodes)>start+1:edges.append([anchor,nodes[start]['id']])
 ids={n['id'] for n in nodes};edges=[e for e in edges if e[0] in ids and e[1] in ids]
 phenotype=dict(version=VERSION,nodes=nodes,edges=edges)
 visual={n['id']:[n['binding'],n['position'],n['scale'],n['shape'],n['material'],n['decorative']] for n in nodes}
 appearance=dict(nodes=sorted(visual.values(),key=lambda x:json.dumps(x)),edges=sorted([[visual[a][1],visual[b][1]] for a,b in edges],key=lambda x:json.dumps(x)))
 return dict(phenotype=phenotype,phenotype_hash=digest(appearance),morphology_hash=digest(morph),fuel=used,truncated=truncated,binding_count=len(bs))
def mutate(g,rng,mode='generative'):
 child=copy.deepcopy(g);r=rng.choice(child['rules']);kind=rng.choice(['parameter'] if mode=='parameter' else ['parameter','insert','delete','rule_add','rule_delete','rewire'])
 ins=lambda:[rng.randrange(8),rng.randint(-64,64),rng.randint(-64,64),rng.randint(-64,64)]
 if kind=='parameter' and r['code']:
  i=rng.choice(r['code']);i[rng.randrange(1,4)]=rng.randint(-128,128)
 elif kind=='insert' and len(r['code'])<32 and child['next_instruction_id']<65536:
  at=rng.randrange(len(r['code'])+1);r['code'].insert(at,ins());r['instruction_ids'].insert(at,child['next_instruction_id']);child['next_instruction_id']+=1
 elif kind=='delete' and r['code']:
  at=rng.randrange(len(r['code']));r['code'].pop(at);r['instruction_ids'].pop(at)
 elif kind=='rule_add' and len(child['rules'])<16 and child['next_id']<65536 and child['next_instruction_id']<65534:
  nid=child['next_id'];child['next_id']+=1;child['rules'].append(dict(id=nid,instruction_ids=[child['next_instruction_id']],code=[ins()]));child['next_instruction_id']+=1;
  if len(r['code'])<32:r['code'].append([4,nid,0,0]);r['instruction_ids'].append(child['next_instruction_id']);child['next_instruction_id']+=1
 elif kind=='rule_delete' and len(child['rules'])>1:
  target=rng.choice([x for x in child['rules'] if x['id']!=child['root']]);child['rules'].remove(target)
 elif kind=='rewire' and r['code']:r['code'][rng.randrange(len(r['code']))]=[rng.choice([4,5]),rng.choice(child['rules'])['id'],rng.randrange(5),rng.randint(-128,128)]
 validate(child);return child,kind
