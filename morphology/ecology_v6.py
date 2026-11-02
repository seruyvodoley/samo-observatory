"""v6 morphology as an inherited trait on genuine v4 population births.

Computational evolution remains delegated to the frozen v4 transition. Morphology
uses its own PRNG and is absent from compute fitness, evaluation and selection.
The bounded archive stores descriptors only and cannot resurrect genotypes.
"""
from __future__ import annotations

import copy
import json
import random
import time
from pathlib import Path

from samo.ecology_v4 import initial as core_initial, advance as core_advance
from samo.engine import state_tuple
from samo.genome_v4 import digest
from .development_v2 import (VERSION, describe, develop_v2, founder_v2,
                             mutate_v2, niche, validate)

PROTOCOL = "samo-ecology-v6-morphology"
PROTOCOL_SPEC = json.loads((Path(__file__).resolve().parents[1] / "protocols/ecology-v6-morphology.json").read_text())
PROTOCOL_HASH = digest(PROTOCOL_SPEC)
ARMS = ("neutral", "novelty", "bounded_archive_diversity")
ARCHIVE_LIMIT = 64
PROPOSALS = 4


def _trait(computational, genome):
    out = develop_v2(computational, genome)
    return {"morphology_genome": genome, "morphology_hash": out["morphology_hash"],
            "phenotype_hash": out["phenotype_hash"], "phenotype": out["phenotype"],
            "descriptor": describe(out["phenotype"]), "niche": list(niche(describe(out["phenotype"]))),
            "interpreter": VERSION, "development_fuel": out["fuel"], "truncated": out["truncated"]}


def initial(seed, size=4, mode="meta", arm="neutral"):
    if arm not in ARMS:
        raise ValueError("unregistered morphology arm")
    core = core_initial(seed, size=size, mode=mode)
    mrng = random.Random(seed ^ 0x6D6F7270687636)
    return {"protocol": PROTOCOL, "protocol_hash": PROTOCOL_HASH, "arm": arm,
            "core": core, "morphology_rng": mrng.getstate(), "traits": {},
            "archive": [], "morphology_events": 0, "morphology_births": 0,
            "morphology_fuel": 0, "morphology_cpu_ns": 0,
            "morphology_changes": 0, "morphology_neutral": 0, "morphology_effects": 0,
            "sphere_returns": 0, "retention_steps": {}, "previous_active": {}}


def _distance(a, b):
    # Stable normalized L1 distance over separately interpretable descriptors.
    keys = ("decorative_nodes", "spatial_span", "branch_nodes", "shape_types")
    scale = (32.0, 16.0, 8.0, 4.0)
    return sum(min(1.0, abs(float(a[k]) - float(b[k])) / d) for k, d in zip(keys, scale)) / len(keys)


def _choose(arm, proposals, active, archive, rng):
    if arm == "neutral":
        return rng.randrange(len(proposals)), "uniform_proposal"
    if arm == "novelty":
        descriptors = [x["descriptor"] for x in active]
        scores = [min((_distance(p["descriptor"], d) for d in descriptors), default=1.0)
                  for p in proposals]
        top = [i for i, x in enumerate(scores) if x == max(scores)]
        return rng.choice(top), "max_nearest_active_distance"
    counts = {}
    for row in archive:
        k = tuple(row["niche"])
        counts[k] = counts.get(k, 0) + row.get("occupancy", 1)
    scores = [counts.get(tuple(p["niche"]), 0) for p in proposals]
    low = min(scores)
    top = [i for i, x in enumerate(scores) if x == low]
    # A tie among equally underrepresented niches uses novelty as a secondary,
    # non-quality criterion; no genotype or computational score is consulted.
    chosen = rng.choice(top)
    return chosen, "least_recorded_niche"


def _record_niche(archive, trait, step, organism_id):
    key = tuple(trait["niche"])
    for row in archive:
        if tuple(row["niche"]) == key:
            row["occupancy"] = min(65535, row["occupancy"] + 1)
            row["last_seen"] = step
            row["last_organism"] = organism_id
            return
    archive.append({"niche": list(key), "occupancy": 1, "first_seen": step,
                    "last_seen": step, "last_organism": organism_id,
                    "descriptor_hash": digest(trait["descriptor"])})
    if len(archive) > ARCHIVE_LIMIT:
        # Deterministic least-recently-seen eviction. It preserves occupancy
        # telemetry only; there are no stored genotypes to donate or revive.
        archive.sort(key=lambda x: (x["last_seen"], x["first_seen"], x["niche"]))
        del archive[0]


def advance(previous):
    start = time.process_time_ns()
    if previous["protocol"] != PROTOCOL or previous["protocol_hash"] != PROTOCOL_HASH:
        raise ValueError("morphology v6 protocol mismatch")
    s = copy.deepcopy(previous)
    # This is the sole computation/selection transition, exactly the frozen v4.
    core, event = core_advance(s["core"])
    rng = random.Random()
    rng.setstate(state_tuple(s["morphology_rng"]))
    traits = dict(s["traits"])
    morph_rows = []
    life = event["lifecycle"]
    births = [x["organism"] for x in life if x["kind"] == "founder"]
    candidate = event.get("candidate")
    if candidate is not None and event.get("accepted"):
        births.append(candidate)
    for form in births:
        parent_id = next((x for x in form["parents"] if x in traits), None)
        if form["parents"] and parent_id is None:
            raise ValueError("no active morphological parent; refusing archive resurrection")
        before = traits[parent_id]["morphology_genome"] if parent_id else None
        t0 = time.process_time_ns()
        if before is None:
            genome = founder_v2(rng)
            proposal_hashes = []
            chosen = None
            mutation_operator = "registered_seeded_v2_founder"
            selection_rule = "fresh_founder"
            proposal_fuel = []
            trait = _trait(form["genome"], genome)
            fuel = trait["development_fuel"]
            counterfactual = None
        else:
            proposals, operators = [], []
            for _ in range(PROPOSALS):
                child, op = mutate_v2(before, rng)
                proposals.append(_trait(form["genome"], child))
                operators.append(op)
            chosen, selection_rule = _choose(s["arm"], proposals, list(traits.values()), s["archive"], rng)
            genome = proposals[chosen]["morphology_genome"]
            proposal_hashes = [x["morphology_hash"] for x in proposals]
            proposal_fuel = [x["development_fuel"] for x in proposals]
            mutation_operator = operators[chosen]
            trait = proposals[chosen]
            counterfactual = _trait(form["genome"], before)
            fuel = sum(proposal_fuel) + counterfactual["development_fuel"]
        trait["origin"] = ({"kind": "registered_seeded_generator", "parent_id": None,
                            "selection_rule": "new_seeded_program", "archive_genotype_donor": False}
                           if before is None else
                           {"kind": "inherited_from_active_parent", "parent_id": parent_id,
                            "mutation_operator": mutation_operator, "selection_rule": selection_rule,
                            "archive_genotype_donor": False})
        elapsed = time.process_time_ns() - t0
        s["morphology_fuel"] += fuel
        s["morphology_cpu_ns"] += elapsed
        changed = before is not None and digest(before) != digest(genome)
        effect = before is not None and trait["phenotype_hash"] != counterfactual["phenotype_hash"]
        s["morphology_changes"] += int(changed)
        s["morphology_neutral"] += int(changed and not effect)
        s["morphology_effects"] += int(effect)
        old_sphere = before is not None and all(n["shape"] == 0 for n in traits[parent_id]["phenotype"]["nodes"])
        new_sphere = all(n["shape"] == 0 for n in trait["phenotype"]["nodes"])
        sphere_return = bool(before is not None and not old_sphere and new_sphere)
        s["sphere_returns"] += int(sphere_return)
        traits[form["id"]] = trait
        _record_niche(s["archive"], trait, core["step"], form["id"])
        s["morphology_births"] += 1
        morph_rows.append({"id": form["id"], "parents": list(form["parents"]),
                           "source": "fresh_founder" if before is None else "active_parent",
                           "parent_morphology_hash": digest(before) if before else None,
                           "morphology_hash": trait["morphology_hash"],
                           "phenotype_hash": trait["phenotype_hash"],
                           "descriptor": trait["descriptor"], "niche": trait["niche"],
                           "genotype": genome, "phenotype": trait["phenotype"],
                           "truncated": trait["truncated"],
                           "mutation_operator": mutation_operator, "selection_rule": selection_rule,
                           "origin": trait["origin"],
                           "proposal_hashes": proposal_hashes, "proposal_fuel": proposal_fuel,
                           "chosen_proposal": chosen, "morphology_changed": changed,
                           "phenotype_changed": effect, "sphere_return": sphere_return,
                           "development_fuel": fuel, "cpu_ns": elapsed,
                           "interpreter": VERSION, "genotype": genome})
    active_ids = {x["id"] for x in core["population"]}
    previous_active = s["previous_active"]
    active_now = {}
    for x in core["population"]:
        tr = traits[x["id"]]
        age = previous_active.get(x["id"], {}).get("age", 0) + 1
        active_now[x["id"]] = {"age": age, "phenotype_hash": tr["phenotype_hash"]}
        s["retention_steps"].setdefault(tr["phenotype_hash"], 0)
        s["retention_steps"][tr["phenotype_hash"]] = max(s["retention_steps"][tr["phenotype_hash"]], age)
    s["previous_active"] = active_now
    s["traits"] = {k: v for k, v in traits.items() if k in active_ids}
    s["core"] = core
    s["morphology_rng"] = rng.getstate()
    s["morphology_events"] += 1
    e = {"index": event["index"], "episode": event["episode"], "protocol": PROTOCOL,
         "arm": s["arm"], "computational": event, "morphology_births": morph_rows,
         "archive_size": len(s["archive"]), "population_unique_phenotypes": len({x["phenotype_hash"] for x in s["traits"].values()}),
         "population_occupied_niches": len({tuple(x["niche"]) for x in s["traits"].values()}),
         "morphology_fuel_total": s["morphology_fuel"], "cpu_ns": time.process_time_ns() - start}
    e["decision_hash"] = digest({"core": core, "morphology_rng": s["morphology_rng"],
                                 "traits": {k: {"morphology_hash": v["morphology_hash"], "phenotype_hash": v["phenotype_hash"]} for k,v in s["traits"].items()},
                                 "archive": s["archive"], "arm": s["arm"]})
    e["state_hash"] = digest(s)
    return s, e


def public_metrics(state):
    traits = state["traits"].values()
    return {"active_unique_forms": len({x["phenotype_hash"] for x in traits}),
            "occupied_active_niches": len({tuple(x["niche"]) for x in traits}),
            "bounded_archive_niches": len(state["archive"]),
            "morphology_births": state["morphology_births"],
            "morphology_changes": state["morphology_changes"],
            "neutral_morphology_changes": state["morphology_neutral"],
            "phenotype_effects": state["morphology_effects"],
            "sphere_returns": state["sphere_returns"],
            "max_structural_retention_steps": max(state["retention_steps"].values(), default=0),
            "morphology_fuel": state["morphology_fuel"],
            "morphology_cpu_ns": state["morphology_cpu_ns"]}
