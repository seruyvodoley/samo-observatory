"""Bounded morphology interpreter v2 for isolated, versioned research.

This module does not alter the production v5 interpreter. Its genome is a
capability-free rule graph; all recursion and output are bounded here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import Counter

from .development import bindings

VERSION = "samo-morphogenesis-2"
LIMITS = {"rules": 16, "instructions": 32, "fuel": 2048,
          "nodes": 256, "depth": 8, "coordinate": 32}
OPS = ("move", "turn", "scale", "emit", "call", "repeat", "data", "material", "branch")


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def validate(genome):
    if not isinstance(genome, dict) or genome.get("version") != 2:
        raise ValueError("morphology v2 version")
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
    rule_ids = set(ids)
    for rule in rules:
        for op, a, _c, _d in rule["code"]:
            if op in (4, 5, 8) and a not in rule_ids:
                raise ValueError("morphology call target")
    return genome


def founder_v2(rng: random.Random):
    """Generate a reproducible founder by bounded mutation of a small grammar seed."""
    genome = {"version": 2, "root": 0,
              "rules": [{"id": 0, "instruction_ids": [0, 1],
                         "code": [[6, 0, 8, 0], [3, 0, 0, 0]]}],
              "next_id": 1, "next_instruction_id": 2}
    for _ in range(rng.randint(2, 6)):
        genome, _ = mutate_v2(genome, rng)
    validate(genome)
    return genome


def _instruction(genome, rng):
    op = rng.randrange(len(OPS))
    a = rng.choice([r["id"] for r in genome["rules"]]) if op in (4, 5, 8) else rng.randint(-64, 64)
    return [op, a, rng.randint(-64, 64), rng.randint(-64, 64)]


def mutate_v2(parent, rng: random.Random):
    child = copy.deepcopy(parent)
    rule = rng.choice(child["rules"])
    kind = rng.choice(("parameter", "insert", "delete", "rule_add", "rule_delete", "rewire"))
    if kind == "parameter" and rule["code"]:
        item = rng.choice(rule["code"])
        slot = rng.randrange(1, 4)
        if slot == 1 and item[0] in (4, 5, 8):
            item[slot] = rng.choice([r["id"] for r in child["rules"]])
        else:
            item[slot] = rng.randint(-128, 128)
    elif kind == "insert" and len(rule["code"]) < LIMITS["instructions"] and child["next_instruction_id"] < 65536:
        at = rng.randrange(len(rule["code"]) + 1)
        rule["code"].insert(at, _instruction(child, rng))
        rule["instruction_ids"].insert(at, child["next_instruction_id"])
        child["next_instruction_id"] += 1
    elif kind == "delete" and rule["code"]:
        at = rng.randrange(len(rule["code"]))
        rule["code"].pop(at)
        rule["instruction_ids"].pop(at)
    elif kind == "rule_add" and len(child["rules"]) < LIMITS["rules"] and child["next_id"] < 65536 and child["next_instruction_id"] < 65536:
        new_id = child["next_id"]
        child["next_id"] += 1
        child["rules"].append({"id": new_id,
                               "instruction_ids": [child["next_instruction_id"]],
                               "code": [_instruction(child, rng)]})
        child["next_instruction_id"] += 1
        if len(rule["code"]) < LIMITS["instructions"] and child["next_instruction_id"] < 65536:
            rule["code"].append([4, new_id, 0, 0])
            rule["instruction_ids"].append(child["next_instruction_id"])
            child["next_instruction_id"] += 1
    elif kind == "rule_delete" and len(child["rules"]) > 1:
        target = rng.choice([r for r in child["rules"] if r["id"] != child["root"]])
        child["rules"].remove(target)
        replacement = rng.choice([r["id"] for r in child["rules"]])
        for r in child["rules"]:
            for item in r["code"]:
                if item[0] in (4, 5, 8) and item[1] == target["id"]:
                    item[1] = replacement
    elif kind == "rewire" and rule["code"]:
        at = rng.randrange(len(rule["code"]))
        target = rng.choice(child["rules"])["id"]
        rule["code"][at] = [rng.choice((4, 5, 8)), target, rng.randint(-64, 64), rng.randint(-128, 128)]
    validate(child)
    return child, kind


def develop_v2(computational, morph):
    validate(morph)
    architecture = bindings(computational)
    if len(architecture) > 16:
        raise ValueError("architecture limit")
    rules = {r["id"]: r["code"] for r in morph["rules"]}
    instruction_ids = {r["id"]: r["instruction_ids"] for r in morph["rules"]}
    nodes, edges = [], []
    used, truncated = 0, False
    # Keep mandatory computational anchors in the budget from the start. This
    # prevents a later anchor from evicting decorative nodes of an earlier one.
    decorative_limit = LIMITS["nodes"] - len(architecture)

    def add_node(identity, binding, position, scale, shape, material, decorative, parent=None):
        nonlocal truncated
        if len(nodes) >= LIMITS["nodes"]:
            truncated = True
            return None
        node = {"id": identity, "binding": binding["id"],
                "position": [round(max(-32, min(32, v)), 6) for v in position],
                "scale": round(max(.05, min(3, scale)), 6),
                "shape": shape % 4, "material": material % 360,
                "decorative": decorative}
        nodes.append(node)
        if parent:
            edges.append([parent, identity])
        return identity

    def run(rule_id, binding, ordinal, path, position, scale, angle, material, depth, parent):
        nonlocal used, truncated
        shape = 0
        if depth >= LIMITS["depth"]:
            truncated = True
            return position, scale, material, shape
        for offset, (op, a, c, d) in enumerate(rules.get(rule_id, [])):
            if used >= LIMITS["fuel"] or len(nodes) >= decorative_limit:
                truncated = True
                break
            used += 1
            tag = f"{path}/r{rule_id}:i{instruction_ids[rule_id][offset]}"
            if op == 0:
                position = [position[0] + a/16*math.cos(angle) - c/16*math.sin(angle),
                            position[1] + a/16*math.sin(angle) + c/16*math.cos(angle),
                            position[2] + d/16]
            elif op == 1:
                angle += a * math.pi / 128
            elif op == 2:
                scale = max(.05, min(3, scale * (1 + a/128)))
            elif op == 3:
                shape = a % 4
                parent = add_node(tag, binding, position,
                                  scale * (1 + min(binding["count"], 96)/192),
                                  shape, material, True, parent)
            elif op == 4:
                _p, _s, _m, child_shape = run(a, binding, ordinal, tag, position[:], scale,
                                                angle, material, depth + 1, parent)
                shape = child_shape
            elif op == 5:
                count = min(4, abs(c) % 5)
                for j in range(count):
                    _p, _s, _m, child_shape = run(a, binding, ordinal, tag + f"/copy{j}",
                                                    position[:], scale,
                                                    angle + j*d*math.pi/128, material,
                                                    depth + 1, parent)
                    shape = child_shape
            elif op == 6:
                value = [ordinal, binding["count"], len(architecture), len(computational["memory"])][abs(a) % 4]
                position[abs(d) % 3] += value * c / 16
            elif op == 7:
                material = a % 360
            elif op == 8:
                count = 2 + abs(c) % 3
                radius = .25 + min(1.0, abs(d)/128) * .75
                for j in range(count):
                    theta = angle + (2*math.pi*j/count) + d*math.pi/128
                    child_position = [position[0] + radius*math.cos(theta),
                                      position[1] + radius*math.sin(theta),
                                      position[2] + (j-(count-1)/2)*radius*.25]
                    _p, _s, _m, child_shape = run(a, binding, ordinal, tag + f"/branch{j}",
                                                    child_position, scale, theta, material,
                                                    depth + 1, parent)
                    shape = child_shape
        return position, scale, material, shape

    for ordinal, binding in enumerate(architecture):
        start = len(nodes)
        result = run(morph["root"], binding, ordinal, binding["id"],
                     [0., 0., 0.], .35, 0., ordinal*37, 0, None)
        position, scale, material, anchor_shape = result
        anchor = add_node(binding["id"], binding, position, scale,
                          anchor_shape, material, False)
        if anchor and len(nodes) > start + 1:
            edges.append([anchor, nodes[start]["id"]])
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e[0] in ids and e[1] in ids]
    phenotype = {"version": VERSION, "nodes": nodes, "edges": edges}
    visual = {n["id"]: [n["binding"], n["position"], n["scale"], n["shape"], n["material"], n["decorative"]] for n in nodes}
    appearance = {"nodes": sorted(visual.values(), key=lambda x: json.dumps(x)),
                  "edges": sorted([[visual[a][1], visual[b][1]] for a, b in edges], key=lambda x: json.dumps(x))}
    return {"phenotype": phenotype, "phenotype_hash": digest(appearance),
            "morphology_hash": digest(morph), "fuel": used,
            "truncated": truncated, "binding_count": len(architecture)}


def describe(phenotype):
    """Return independent structural measurements; no scalar complexity score."""
    nodes = phenotype.get("nodes", [])
    edges = phenotype.get("edges", [])
    positions = {tuple(n["position"]) for n in nodes}
    shapes = Counter(n["shape"] for n in nodes)
    decorative = [n for n in nodes if n["decorative"]]
    out_degree = Counter(a for a, _b in edges)
    branch_nodes = sum(v > 1 for v in out_degree.values())
    if positions:
        mins = [min(p[i] for p in positions) for i in range(3)]
        maxs = [max(p[i] for p in positions) for i in range(3)]
        span = math.sqrt(sum((maxs[i]-mins[i])**2 for i in range(3)))
    else:
        span = 0.0
    return {"nodes": len(nodes), "decorative_nodes": len(decorative),
            "unique_positions": len(positions), "shape_types": len(shapes),
            "shape_counts": dict(shapes),
            "spherical_fraction": (shapes.get(0, 0)/len(nodes)) if nodes else None,
            "edges": len(edges), "branch_nodes": branch_nodes,
            "spatial_span": round(span, 6)}


def niche(descriptor):
    """Bounded MAP-Elites descriptor cells, deliberately not ordered by quality."""
    n = descriptor["decorative_nodes"]
    node_bin = 0 if n == 0 else 1 if n <= 3 else 2 if n <= 15 else 3
    span = descriptor["spatial_span"]
    span_bin = 0 if span < .01 else 1 if span < .75 else 2 if span < 2.5 else 3
    branches = descriptor["branch_nodes"]
    branch_bin = 0 if branches == 0 else 1 if branches == 1 else 2
    shapes = descriptor["shape_types"]
    shape_bin = 0 if shapes <= 1 else 1 if shapes == 2 else 2
    return node_bin, span_bin, branch_bin, shape_bin
