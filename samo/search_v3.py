"""Offline v3 research search ABI. Does not alter production v2."""
import copy, random
from .vm import OPS,MAX_CODE,Meter,execute,ins,Trap
from .genome import ancestor,validate,digest

def founder():
    g=ancestor();g['modules']=[[ins('CONST')]];g['router']=[ins('CONST')]
    g['dialect']=[[] for _ in range(4)]
    # Generic five-field edit emitter, without prediction algorithms.
    g['search']=[x for _ in range(5) for x in (ins('RAND'),ins('EMIT'))]
    return g

def edit(g,words):
    c=copy.deepcopy(g)
    for i in range(0,len(words)-4,5):
        target,pos,kind,opcode,arg=words[i:i+5];target%=6
        if target==3:
            a=c['memory'];value=arg&65535
        elif target==5:
            if kind%2 and len(c['modules'])>1:del c['modules'][pos%len(c['modules'])]
            elif len(c['modules'])<8:c['modules'].append([])
            continue
        else:
            a=c['modules'][pos%len(c['modules'])] if target==0 else c['search'] if target==1 else c['dialect'][pos%4] if target==2 else c['router']
            value=[opcode%len(OPS),(arg&65535)-32768]
        cap=64 if target==3 else MAX_CODE
        if kind%3==1 and a:del a[pos%len(a)]
        elif kind%3==2 and len(a)<cap:a.insert(pos%(len(a)+1),value)
        elif a:a[pos%len(a)]=value
    validate(c);return c

def reproduce(g,rng,mode='meta',external_probability=.2,search_operator=None):
    # Registered external exploration channel; no quality restoration.
    external=mode!='meta' or rng.random()<external_probability
    words=[];cost=0;failure=None
    if not external:
        meter=Meter(512,deadline=float('inf'))
        try:
            _,words,_=execute(g['search'] if search_operator is None else search_operator,[rng.randrange(65536) for _ in range(8)],g['memory'],g['dialect'],rng,meter)
        except (Trap,ValueError) as e:failure=str(e)
        cost=meter.used
    else:words=[rng.randrange(65536) for _ in range(5)];cost=5
    try:child=edit(g,words)
    except ValueError:return None,dict(search_fuel=cost,failure='invalid',external=external)
    return child,dict(search_fuel=cost,failure=failure,external=external,genotype_changed=digest(child)!=digest(g))
