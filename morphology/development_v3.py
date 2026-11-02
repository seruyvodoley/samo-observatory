"""Bounded, versioned v3 morphology language with geometric descriptors.

The genome is an inert rule graph interpreted by this module. It cannot make
system calls, access files, read clocks, spawn processes, or perform network IO.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import Counter, defaultdict, deque

from .development import bindings

VERSION = "samo-morphogenesis-3"
LIMITS = {"rules": 16, "instructions": 32, "fuel": 2048,
          "nodes": 256, "depth": 8, "coordinate": 32, "scale": 3.0}
OPS = ("move", "orient", "scale", "emit", "call", "repeat", "data",
       "material", "branch", "mirror_emit", "taper", "connect")
SILHOUETTE_SIZE = 16


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def validate(genome):
    if not isinstance(genome, dict) or genome.get("version") != 3:
        raise ValueError("morphology v3 version")
    rules = genome.get("rules")
    if not isinstance(rules, list) or not 1 <= len(rules) <= LIMITS["rules"]:
        raise ValueError("morphology rule limit")
    ids, instruction_ids = [], []
    for rule in rules:
        if not isinstance(rule, dict) or type(rule.get("id")) is not int or not 0 <= rule["id"] <= 65535:
            raise ValueError("morphology rule id")
        code, identities = rule.get("code"), rule.get("instruction_ids")
        if not isinstance(code, list) or len(code) > LIMITS["instructions"]:
            raise ValueError("morphology instruction limit")
        if not isinstance(identities, list) or len(identities) != len(code):
            raise ValueError("morphology instruction identity")
        if any(type(x) is not int or not 0 <= x <= 65535 for x in identities):
            raise ValueError("morphology instruction identity")
        ids.append(rule["id"])
        instruction_ids.extend(identities)
        for item in code:
            if (not isinstance(item, list) or len(item) != 4 or
                    any(type(v) is not int or abs(v) > 32767 for v in item) or
                    not 0 <= item[0] < len(OPS)):
                raise ValueError("morphology instruction")
    if len(set(ids)) != len(ids) or len(set(instruction_ids)) != len(instruction_ids):
        raise ValueError("duplicate morphology identity")
    root = genome.get("root")
    if type(root) is not int or root not in ids:
        raise ValueError("morphology root")
    if type(genome.get("next_id")) is not int or genome["next_id"] <= max(ids):
        raise ValueError("morphology rule counter")
    if type(genome.get("next_instruction_id")) is not int or genome["next_instruction_id"] <= max(instruction_ids, default=-1):
        raise ValueError("morphology instruction counter")
    known = set(ids)
    for rule in rules:
        for op, a, _c, _d in rule["code"]:
            if op in (4, 5, 8) and a not in known:
                raise ValueError("morphology call target")
    return genome


def _instruction(genome, rng):
    op = rng.randrange(len(OPS))
    a = rng.choice([r["id"] for r in genome["rules"]]) if op in (4, 5, 8) else rng.randint(-64, 64)
    return [op, a, rng.randint(-64, 64), rng.randint(-64, 64)]


def founder_v3(rng: random.Random):
    """Seeded rule-graph generator; no stored shape preset is selected."""
    # Data binding and emission provide the ABI anchor; all geometric choices
    # and optional structure are sampled into the inherited program.
    n = rng.randint(2, 7)
    code = [[6, rng.randrange(4), rng.randint(-24, 24), rng.randrange(3)],
            [3, rng.randrange(4), 0, 0]]
    identities = [0, 1]
    next_i = 2
    g = {"version": 3, "root": 0,
         "rules": [{"id": 0, "instruction_ids": identities, "code": code}],
         "next_id": 1, "next_instruction_id": next_i}
    for _ in range(n - 2):
        ins = _instruction(g, rng)
        g["rules"][0]["code"].insert(rng.randrange(len(g["rules"][0]["code"]) + 1), ins)
        g["rules"][0]["instruction_ids"].append(g["next_instruction_id"])
        g["next_instruction_id"] += 1
    for _ in range(rng.randint(0, 3)):
        g, _ = mutate_v3(g, rng)
    validate(g)
    return g


def mutate_v3(parent, rng: random.Random):
    validate(parent)
    child = copy.deepcopy(parent)
    rule = rng.choice(child["rules"])
    kind = rng.choice(("parameter", "insert", "delete", "rule_add", "rule_delete", "rewire"))
    if kind == "parameter" and rule["code"]:
        item = rng.choice(rule["code"])
        slot = rng.randrange(1, 4)
        item[slot] = (rng.choice([r["id"] for r in child["rules"]])
                      if slot == 1 and item[0] in (4, 5, 8) else rng.randint(-128, 128))
    elif kind == "insert" and len(rule["code"]) < LIMITS["instructions"] and child["next_instruction_id"] < 65536:
        at = rng.randrange(len(rule["code"])+1)
        rule["code"].insert(at, _instruction(child, rng))
        rule["instruction_ids"].insert(at, child["next_instruction_id"])
        child["next_instruction_id"] += 1
    elif kind == "delete" and rule["code"]:
        at = rng.randrange(len(rule["code"]))
        rule["code"].pop(at); rule["instruction_ids"].pop(at)
    elif kind == "rule_add" and len(child["rules"]) < LIMITS["rules"] and child["next_id"] < 65536:
        rid = child["next_id"]; child["next_id"] += 1
        child["rules"].append({"id": rid, "instruction_ids": [child["next_instruction_id"]],
                               "code": [_instruction(child, rng)]})
        child["next_instruction_id"] += 1
        if len(rule["code"]) < LIMITS["instructions"]:
            rule["code"].append([4, rid, 0, 0])
            rule["instruction_ids"].append(child["next_instruction_id"])
            child["next_instruction_id"] += 1
    elif kind == "rule_delete" and len(child["rules"]) > 1:
        target = rng.choice([r for r in child["rules"] if r["id"] != child["root"]])
        child["rules"].remove(target)
        replacement = rng.choice([r["id"] for r in child["rules"]])
        for r in child["rules"]:
            for ins in r["code"]:
                if ins[0] in (4, 5, 8) and ins[1] == target["id"]:
                    ins[1] = replacement
    elif kind == "rewire" and rule["code"]:
        at = rng.randrange(len(rule["code"]))
        target = rng.choice(child["rules"])["id"]
        rule["code"][at] = [rng.choice((4, 5, 8)), target, rng.randint(-64, 64), rng.randint(-128, 128)]
    validate(child)
    return child, kind


def develop_v3(computational, morph):
    validate(morph)
    architecture = bindings(computational)
    if len(architecture) > 16:
        raise ValueError("architecture limit")
    rules = {r["id"]: r["code"] for r in morph["rules"]}
    identities = {r["id"]: r["instruction_ids"] for r in morph["rules"]}
    nodes, edges, used = [], [], 0
    truncated = False
    decorative_cap = LIMITS["nodes"] - len(architecture)

    def add(binding, p, scale, shape, material, decorative, parent, tag):
        nonlocal truncated
        node_cap = decorative_cap if decorative else LIMITS["nodes"]
        if len(nodes) >= node_cap:
            truncated = True
            return None
        ident = tag
        node = {"id": ident, "binding": binding["id"],
                "position": [round(max(-32., min(32., float(v))), 6) for v in p],
                "scale": round(max(.05, min(LIMITS["scale"], float(scale))), 6),
                "shape": int(shape) % 4, "material": int(material) % 360,
                "decorative": bool(decorative)}
        nodes.append(node)
        if parent is not None:
            edges.append([parent, ident])
        return ident

    def run(rule_id, binding, ordinal, tag, pos, scale, az, el, material, depth, parent):
        nonlocal used, truncated
        last = parent
        if depth >= LIMITS["depth"]:
            truncated = True
            return pos, scale, az, el, material, last
        for off, (op, a, c, d) in enumerate(rules.get(rule_id, [])):
            if used >= LIMITS["fuel"] or len(nodes) >= decorative_cap:
                truncated = True
                break
            used += 1
            here = f"{tag}/r{rule_id}:i{identities[rule_id][off]}"
            if op == 0:  # local three-axis movement
                pos = [pos[0] + a/32*math.cos(az),
                       pos[1] + a/32*math.sin(az) + c/32*math.sin(el),
                       pos[2] + d/32 + c/32*math.cos(el)]
            elif op == 1:  # orientation changes the local growth frame
                az += a * math.pi/128
                el = max(-math.pi/2, min(math.pi/2, el + c*math.pi/256))
            elif op == 2:
                scale = max(.05, min(LIMITS["scale"], scale*(1+a/128)))
            elif op == 3:
                shape = a % 4
                last = add(binding, pos, scale*(1+min(binding["count"], 96)/192), shape, material, True, last, here)
                if last is not None and c % 3 == 0:
                    axis = abs(d) % 3
                    mirror = pos[:]; mirror[axis] *= -1
                    add(binding, mirror, scale, shape, material, True, last, here+"/mirror")
            elif op == 4:
                _p, _s, _az, _el, _m, child = run(a, binding, ordinal, here, pos[:], scale, az, el, material, depth+1, last)
                if child is not None: last = child
            elif op == 5:
                count = 1 + abs(c) % 4
                for j in range(count):
                    delta = d*math.pi/128
                    _p, _s, _az, _el, _m, child = run(a, binding, ordinal, here+f"/repeat{j}", pos[:], scale, az+j*delta, el, material, depth+1, last)
                    if child is not None: last = child
            elif op == 6:
                value = (ordinal, binding["count"], len(architecture), len(computational["memory"]))[abs(a)%4]
                axis = abs(d)%3
                pos[axis] += value*c/64
            elif op == 7:
                material = a % 360
            elif op == 8:
                count = 2 + abs(c)%4
                radius = .2 + min(1.,abs(d)/128)*1.1
                for j in range(count):
                    theta = az + 2*math.pi*j/count + d*math.pi/128
                    child_pos = [pos[0]+radius*math.cos(theta), pos[1]+radius*math.sin(theta), pos[2]+(j-(count-1)/2)*radius*.35]
                    _p,_s,_az,_el,_m,child=run(a,binding,ordinal,here+f"/branch{j}",child_pos,scale,theta,el,material,depth+1,last)
                    if child is not None:last=child
            elif op == 9:  # emit mirrored pair about a selected axis
                axis = abs(a)%3
                p2 = pos[:]; p2[axis] *= -1
                last = add(binding,pos,scale,abs(c)%4,material,True,last,here)
                add(binding,p2,scale,abs(c)%4,material,True,last,here+"/reflection")
            elif op == 10:  # depth-dependent taper; may also reverse
                scale = max(.05,min(LIMITS["scale"],scale*(1 + (a/128)*(depth+1)/LIMITS["depth"])))
            elif op == 11 and len(nodes) > 1:  # connect to a prior node, without fabricating geometry
                target = nodes[abs(a)%len(nodes)]["id"]
                if last is not None and target != last:
                    edges.append([target,last])
        return pos, scale, az, el, material, last

    for ordinal, binding in enumerate(architecture):
        before = len(nodes)
        pos, scale, _az, _el, material, last = run(morph["root"], binding, ordinal, binding["id"], [0.,0.,0.], .35, ordinal*.29, 0., ordinal*37, 0, None)
        anchor = add(binding,pos,scale,0,material,False,None,binding["id"])
        if anchor is not None and len(nodes)>before+1:
            edges.append([anchor,nodes[before]["id"]])
    ids = {n["id"] for n in nodes}
    edges = sorted({(a,b) for a,b in edges if a in ids and b in ids and a != b})
    phenotype = {"version": VERSION,"nodes":nodes,"edges":[list(e) for e in edges]}
    visual = [[n["binding"],n["position"],n["scale"],n["shape"],n["material"],n["decorative"]] for n in nodes]
    appearance = {"nodes":sorted(visual,key=lambda x:json.dumps(x,separators=(",",":"))), "edges":[]}
    # Edges are represented by endpoint coordinates, so instruction identity is irrelevant.
    by_id={n["id"]:n for n in nodes}
    appearance["edges"]=sorted([[by_id[a]["position"],by_id[b]["position"]] for a,b in edges], key=lambda x:json.dumps(x,separators=(",",":")))
    return {"phenotype":phenotype,"phenotype_hash":digest(appearance),"morphology_hash":digest(morph),
            "fuel":used,"truncated":truncated,"binding_count":len(architecture)}


def _silhouette(nodes, axis_a, axis_b):
    points=[(n["position"][axis_a],n["position"][axis_b],max(.05,n["scale"]),n["shape"]) for n in nodes]
    if not points:return "0"*(SILHOUETTE_SIZE*SILHOUETTE_SIZE//4)
    min_a=min(x-r for x,_,r,_shape in points); max_a=max(x+r for x,_,r,_shape in points)
    min_b=min(y-r for _,y,r,_shape in points); max_b=max(y+r for _,y,r,_shape in points)
    da=max(1e-9,max_a-min_a); db=max(1e-9,max_b-min_b)
    grid=0
    for a,b,r,shape in points:
        ca=(a-min_a)/da*(SILHOUETTE_SIZE-1); cb=(b-min_b)/db*(SILHOUETTE_SIZE-1)
        ra=max(0,int(math.ceil(r/da*(SILHOUETTE_SIZE-1))))
        rb=max(0,int(math.ceil(r/db*(SILHOUETTE_SIZE-1))))
        for iy in range(max(0,int(cb)-rb),min(SILHOUETTE_SIZE,int(cb)+rb+1)):
            for ix in range(max(0,int(ca)-ra),min(SILHOUETTE_SIZE,int(ca)+ra+1)):
                dx=(ix-ca)/max(1,ra);dy=(iy-cb)/max(1,rb)
                inside=(abs(dx)<=1 and abs(dy)<=1) if shape==2 else (abs(dx)+abs(dy)<=1.25 if shape==3 else dx*dx+dy*dy<=1.5)
                if inside:grid |= 1 << (iy*SILHOUETTE_SIZE+ix)
    return grid.to_bytes(SILHOUETTE_SIZE*SILHOUETTE_SIZE//8,"little").hex()


def describe(phenotype):
    nodes=phenotype.get("nodes",[]); edges=phenotype.get("edges",[])
    positions=[n["position"] for n in nodes]
    shape_counts=Counter(n["shape"] for n in nodes)
    unique_positions=len({tuple(p) for p in positions})
    if positions:
        means=[sum(p[i] for p in positions)/len(positions) for i in range(3)]
        spans=[max(p[i] for p in positions)-min(p[i] for p in positions) for i in range(3)]
        span=math.sqrt(sum(x*x for x in spans))
        gyr=math.sqrt(sum(sum((p[i]-means[i])**2 for p in positions) for i in range(3))/len(positions))
        variances=sorted((sum((p[i]-means[i])**2 for p in positions)/len(positions) for i in range(3)),reverse=True)
        anisotropy=0. if variances[0]<1e-12 else 1-variances[-1]/variances[0]
    else: span=gyr=anisotropy=0.
    out_degree=Counter(a for a,_ in edges)
    adj=defaultdict(set)
    for a,b in edges:adj[a].add(b);adj[b].add(a)
    ids={n["id"] for n in nodes}; components=0; unseen=set(ids)
    while unseen:
        components+=1; todo=[unseen.pop()]
        while todo:
            for other in adj[todo.pop()]&unseen:
                unseen.remove(other);todo.append(other)
    projections={"xy":_silhouette(nodes,0,1),"xz":_silhouette(nodes,0,2),"yz":_silhouette(nodes,1,2)}
    silhouette_hash=digest(projections)
    all_spheres=bool(nodes) and all(n["shape"]==0 for n in nodes)
    spatially_compact=bool(nodes) and span<.45 and gyr<.18
    return {"nodes":len(nodes),"decorative_nodes":sum(bool(n["decorative"]) for n in nodes),
            "unique_positions":unique_positions,"shape_types":len(shape_counts),"shape_counts":dict(shape_counts),
            "spherical_fraction":shape_counts.get(0,0)/len(nodes) if nodes else None,
            "edges":len(edges),"branch_nodes":sum(v>1 for v in out_degree.values()),"components":components,
            "spatial_span":round(span,6),"radius_of_gyration":round(gyr,6),"anisotropy":round(anisotropy,6),
            "all_spheres":all_spheres,"spatially_compact":spatially_compact,
            "silhouette_hash":silhouette_hash,"silhouette_views":projections}


def silhouette_distance(a,b):
    """Mean normalized bit distance over matched orthographic silhouettes."""
    views=("xy","xz","yz")
    distances=[]
    for view in views:
        aa=bytes.fromhex(a[view]);bb=bytes.fromhex(b[view])
        distances.append(sum(bin(x^y).count("1") for x,y in zip(aa,bb))/(8*len(aa)))
    return sum(distances)/len(distances)


def niche(descriptor):
    span=descriptor["spatial_span"]; nodes=descriptor["decorative_nodes"]
    return (0 if nodes==0 else 1 if nodes<=3 else 2 if nodes<=15 else 3,
            0 if span<.01 else 1 if span<.75 else 2 if span<2.5 else 3,
            0 if descriptor["branch_nodes"]==0 else 1 if descriptor["branch_nodes"]==1 else 2,
            0 if descriptor["shape_types"]<=1 else 1 if descriptor["shape_types"]==2 else 2)
