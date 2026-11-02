"""Experimental v7 two-rate morphology ecology; compute core stays frozen v4."""
from __future__ import annotations

import copy
import json
import random
import time
from collections import Counter
from pathlib import Path

from samo.ecology_v4 import initial as core_initial, advance as core_advance
from samo.engine import state_tuple
from samo.genome_v4 import digest
from .ecology_v6 import (advance as advance6, initial as initial6,
                         public_metrics as public_metrics6)
from .development_v3 import (VERSION, describe, develop_v3, founder_v3,
                             mutate_v3, niche, silhouette_distance, validate)

PROTOCOL = "samo-ecology-v7-morphology"
PROTOCOL_SPEC = json.loads((Path(__file__).resolve().parents[1] / "protocols/ecology-v7-morphology.json").read_text())
PROTOCOL_HASH = digest(PROTOCOL_SPEC)
ARMS = ("v7_neutral", "v7_novelty", "v7_live_niche_search", "v7_niche_survival", "v7_archive_diversity", "v7_dual_rate")
CONTROL = "v6_neutral"
ALL_ARMS = (CONTROL,) + ARMS
ARCHIVE_LIMIT = 64
FEATURE_LIMIT = 512
DUAL_RATE = 0.125


def _trait(computational, genome, origin=None, feature_ages=None):
    out = develop_v3(computational, genome)
    d = describe(out["phenotype"])
    features = {"silhouette:" + name: digest(bits) for name, bits in d["silhouette_views"].items()}
    features["silhouette:combined"] = d["silhouette_hash"]
    features["shapes"] = digest(d["shape_counts"])
    ages = dict(feature_ages or {})
    return {"morphology_genome":genome,"morphology_hash":out["morphology_hash"],
            "phenotype_hash":out["phenotype_hash"],"phenotype":out["phenotype"],
            "descriptor":d,"niche":list(niche(d)),"interpreter":VERSION,
            "development_fuel":out["fuel"],"truncated":out["truncated"],
            "origin":origin,"features":features,"feature_ages":ages}


def initial(seed, size=4, mode="meta", arm=CONTROL):
    if arm not in ALL_ARMS:
        raise ValueError("unregistered v7 morphology arm")
    if arm == CONTROL:
        return initial6(seed,size=size,mode=mode,arm="neutral")
    core=core_initial(seed,size=size,mode=mode)
    rng=random.Random(seed ^ 0x6D6F7270687637)
    s={"protocol":PROTOCOL,"protocol_hash":PROTOCOL_HASH,"arm":arm,"core":core,
            "morphology_rng":rng.getstate(),"traits":{},"archive":[],"feature_history":{},
            "morphology_births":0,"morphology_events":0,"morphology_changes":0,
            "morphology_effects":0,"morphology_neutral":0,"silhouette_effects":0,
            "sphere_return_events":0,"spatial_collapse_events":0,"feature_reappearances":0,
            "dual_rate_events":0,
            "archive_evictions":0,"feature_evictions":0,"feature_eviction_root":digest([]),
            "morphology_fuel":0,"morphology_cpu_ns":0,"morphology_rng_transitions":0,
            "initial_morphology_assignments":0}
    # The computational core starts with a living population. Give every
    # initial organism a reproducible inherited morphology program now, so
    # public snapshots and later reproduction never begin with missing traits.
    for organism in core["population"]:
        start=time.process_time_ns()
        genome=founder_v3(rng)
        trait=_trait(organism["genome"],genome,origin={"kind":"experiment_founder_assignment",
                    "parent_id":None,"archive_genotype_donor":False})
        trait["origin"]["organism_id"]=organism["id"]
        s["traits"][organism["id"]]=trait
        _update_feature_history(s,trait,core["step"],{})
        _record_archive(s["archive"],trait,core["step"],organism["id"])
        s["morphology_fuel"]+=trait["development_fuel"]
        s["morphology_cpu_ns"]+=time.process_time_ns()-start
        s["initial_morphology_assignments"]+=1
    s["morphology_rng"]=rng.getstate()
    return s


def _distance(a,b):
    return silhouette_distance(a["silhouette_views"],b["silhouette_views"])


def _proposal_choice(arm, proposals, active, archive, rng):
    if arm == "v7_neutral" or arm == "v7_dual_rate":
        return rng.randrange(len(proposals)),"uniform_single_proposal" if len(proposals)==1 else "uniform_proposal"
    if arm == "v7_novelty":
        scores=[min((_distance(p["descriptor"],a["descriptor"]) for a in active),default=1.) for p in proposals]
        best=max(scores);return rng.choice([i for i,x in enumerate(scores) if x==best]),"max_orthographic_silhouette_distance"
    counts=Counter(tuple(x["niche"]) for x in archive)
    scores=[counts[tuple(p["niche"])] for p in proposals]
    lowest=min(scores)
    tied=[i for i,x in enumerate(scores) if x==lowest]
    # Use novelty only as a tie break; archive entries contain descriptors, never genomes.
    if len(tied)>1:
        refs=[x["descriptor"] for x in archive]
        nearest=[min((_distance(proposals[i]["descriptor"],r) for r in refs),default=1.) for i in tied]
        high=max(nearest);tied=[i for i,v in zip(tied,nearest) if v==high]
    return rng.choice(tied),"least_occupied_archive_descriptor_niche"


def _record_archive(archive, trait, step, organism_id):
    cell=tuple(trait["niche"])
    for row in archive:
        if tuple(row["niche"])==cell:
            row["occupancy"]=min(65535,row["occupancy"]+1)
            row["last_seen"]=step;row["last_organism"]=organism_id
            row["descriptor"]=trait["descriptor"]
            row["descriptor_hash"]=digest(trait["descriptor"])
            return False
    archive.append({"niche":list(cell),"occupancy":1,"first_seen":step,"last_seen":step,
                    "last_organism":organism_id,"descriptor_hash":digest(trait["descriptor"]),
                    "descriptor":trait["descriptor"]})
    if len(archive)>ARCHIVE_LIMIT:
        archive.sort(key=lambda x:(x["last_seen"],x["first_seen"],x["niche"]))
        archive.pop(0);return True
    return False


def _apply_niche_survival_veto(prior_core, core, event, traits):
    """Registered compute-selection intervention for the v7 niche-survival arm."""
    if not event.get("accepted"):
        return None
    death=next((x for x in event.get("lifecycle",[]) if x.get("kind")=="death"),None)
    if death is None:return None
    incumbent=next((x for x in prior_core["population"] if x["id"]==death["id"]),None)
    old_trait=traits.get(death["id"])
    living=Counter(tuple(t["niche"]) for t in traits.values())
    if incumbent is None or old_trait is None or living[tuple(old_trait["niche"])]!=1:return None
    core["population"]=copy.deepcopy(prior_core["population"])
    core["births"]=prior_core["births"];core["deaths"]=prior_core["deaths"]
    core["last_change"]=prior_core["last_change"]
    event["lifecycle"]=[x for x in event["lifecycle"] if x.get("kind")!="death"]
    event["accepted"]=False;event["birth"]=False;event["status"]="morphology_niche_veto"
    event["morphology_veto"]={"kind":"last_live_morphology_niche","organism_id":death["id"],
        "niche":list(old_trait["niche"]),"candidate_id":event.get("candidate",{}).get("id"),
        "compute_trial_was_evaluated":True}
    event["population_ids"]=[x["id"] for x in core["population"]]
    event["state_hash"]=digest(core)
    return event["morphology_veto"]


def _update_feature_history(s, trait, step, inherited_ages):
    ages={}
    for name, sig in trait["features"].items():
        age=int(inherited_ages.get(name+":"+sig,0))+1 if name+":"+sig in inherited_ages else 1
        ages[name+":"+sig]=age
        row=s["feature_history"].setdefault(sig,{"first_seen":step,"last_seen":step,"active_steps":0,"max_lineage_age":0,"observations":0})
        if row["last_seen"]<step-1:s["feature_reappearances"]+=1
        row["last_seen"]=step;row["active_steps"]+=1;row["max_lineage_age"]=max(row["max_lineage_age"],age);row["observations"]+=1
    trait["feature_ages"]={k:v for k,v in ages.items() if k in {n+":"+sig for n,sig in trait["features"].items()}}
    if len(s["feature_history"])>FEATURE_LIMIT:
        items=sorted(s["feature_history"].items(),key=lambda kv:(kv[1]["last_seen"],kv[1]["first_seen"],kv[0]))
        count=len(items)-FEATURE_LIMIT
        removed=items[:count]
        s["feature_eviction_root"]=digest([s["feature_eviction_root"],[(k,v) for k,v in removed]])
        s["feature_evictions"]+=count
        for k,_ in removed:del s["feature_history"][k]


def _make_child(s, form, parent_id, traits, rng, morphology_arm, core_step):
    before=traits[parent_id]["morphology_genome"] if parent_id else None
    start=time.process_time_ns()
    if before is None:
        genome=founder_v3(rng);operator="registered_stochastic_rule_graph_founder";rule="fresh_seeded_generator"
        trait=_trait(form["genome"],genome,origin={"kind":"fresh_founder","parent_id":None,"archive_genotype_donor":False})
        fuel=trait["development_fuel"]; proposal_hashes=[];proposal_fuel=[];chosen=None
        inherited={}
    else:
        n=4 if morphology_arm in ("v7_novelty","v7_live_niche_search","v7_archive_diversity") else 1
        proposals=[];operators=[]
        for _ in range(n):
            g,op=mutate_v3(before,rng);proposals.append(_trait(form["genome"],g));operators.append(op)
        if morphology_arm=="v7_live_niche_search":
            # Select against live occupancy by choosing the underrepresented cell.
            counts=Counter(tuple(t["niche"]) for t in traits.values())
            scores=[(counts[tuple(p["niche"])],-min((_distance(p["descriptor"],t["descriptor"]) for t in traits.values()),default=1.)) for p in proposals]
            low=min(x[0] for x in scores); tied=[i for i,x in enumerate(scores) if x[0]==low]
            best=max(scores[i][1] for i in tied);tied=[i for i in tied if scores[i][1]==best]
            chosen=rng.choice(tied);rule="least_occupied_live_morphology_niche"
        else:
            chosen,rule=_proposal_choice(morphology_arm,proposals,list(traits.values()),s["archive"],rng)
        trait=proposals[chosen];genome=trait["morphology_genome"];operator=operators[chosen]
        proposal_hashes=[p["morphology_hash"] for p in proposals]
        proposal_fuel=[p["development_fuel"] for p in proposals]
        # Counterfactual keeps the no-op/effect distinction tied to the parent's current program.
        counter=_trait(form["genome"],before)
        fuel=sum(proposal_fuel)+counter["development_fuel"]
        inherited={k+":"+v:traits[parent_id]["feature_ages"].get(k+":"+v,0) for k,v in traits[parent_id]["features"].items()}
        trait["origin"]={"kind":"active_parent_mutation","parent_id":parent_id,"operator":operator,"selection_rule":rule,"archive_genotype_donor":False}
        trait["_counterfactual_hash"]=counter["phenotype_hash"]
    elapsed=time.process_time_ns()-start
    changed=before is not None and digest(before)!=digest(genome)
    effect=before is not None and trait["phenotype_hash"]!=trait.get("_counterfactual_hash",traits[parent_id]["phenotype_hash"])
    parent_descriptor=traits[parent_id]["descriptor"] if parent_id else None
    sphere_return=bool(parent_descriptor and not parent_descriptor["all_spheres"] and trait["descriptor"]["all_spheres"])
    collapse=bool(parent_descriptor and parent_descriptor["spatial_span"]>0 and
                  trait["descriptor"]["spatial_span"]<.4*parent_descriptor["spatial_span"])
    s["sphere_return_events"]+=int(sphere_return);s["spatial_collapse_events"]+=int(collapse)
    s["silhouette_effects"]+=int(parent_descriptor is not None and parent_descriptor["silhouette_hash"]!=trait["descriptor"]["silhouette_hash"])
    trait.pop("_counterfactual_hash",None)
    _update_feature_history(s,trait,core_step,inherited)
    _record_archive(s["archive"],trait,core_step,form["id"])
    s["morphology_births"]+=1;s["morphology_changes"]+=int(changed)
    s["morphology_effects"]+=int(effect);s["morphology_neutral"]+=int(changed and not effect)
    s["morphology_fuel"]+=fuel;s["morphology_cpu_ns"]+=elapsed
    row={"id":form["id"],"parents":list(form["parents"]),"source":"active_parent" if before else "fresh_founder",
         "parent_morphology_hash":digest(before) if before else None,"morphology_hash":trait["morphology_hash"],
         "phenotype_hash":trait["phenotype_hash"],"silhouette_hash":trait["descriptor"]["silhouette_hash"],
         "descriptor":trait["descriptor"],"niche":trait["niche"],"genotype":genome,"phenotype":trait["phenotype"],
         "operator":operator,"selection_rule":rule,"proposal_hashes":proposal_hashes,"proposal_fuel":proposal_fuel,
         "chosen":chosen,"genotype_changed":changed,"phenotype_changed":effect,
         "silhouette_changed":parent_descriptor is not None and parent_descriptor["silhouette_hash"]!=trait["descriptor"]["silhouette_hash"],
         "sphere_return":sphere_return,"spatial_collapse":collapse,"feature_ages":trait["feature_ages"],
         "development_fuel":fuel,"cpu_ns":elapsed,"origin":trait["origin"]}
    return trait,row


def advance(previous):
    if previous.get("protocol")=="samo-ecology-v6-morphology":
        return advance6(previous)
    if previous.get("protocol")!=PROTOCOL or previous.get("protocol_hash")!=PROTOCOL_HASH or previous.get("arm") not in ARMS:
        raise ValueError("v7 protocol mismatch")
    start=time.process_time_ns();s=copy.deepcopy(previous)
    prior_core=s["core"]
    core,event=core_advance(prior_core)
    morphology_selection=None
    if s["arm"]=="v7_niche_survival" and event.get("accepted"):
        morphology_selection=_apply_niche_survival_veto(prior_core,core,event,s["traits"])
    rng=random.Random();rng.setstate(state_tuple(s["morphology_rng"]))
    traits=dict(s["traits"]);morph_births=[];morph_events=[]
    life=event["lifecycle"]
    forms=[x["organism"] for x in life if x["kind"]=="founder"]
    if event.get("candidate") is not None and event.get("accepted"):forms.append(event["candidate"])
    for form in forms:
        parent_id=next((x for x in form.get("parents",[]) if x in traits),None)
        if form.get("parents") and parent_id is None:raise ValueError("no active morphology parent; archive resurrection refused")
        trait,row=_make_child(s,form,parent_id,traits,rng,s["arm"],core["step"])
        traits[form["id"]]=trait;morph_births.append(row)
    active_ids={x["id"] for x in core["population"]}
    traits={k:v for k,v in traits.items() if k in active_ids}
    # This is a separate heritable event: it changes the living line's morphology
    # without a compute birth and therefore cannot be mistaken for a new genome.
    if s["arm"]=="v7_dual_rate" and traits and rng.random()<DUAL_RATE:
        target_id=rng.choice(sorted(traits))
        organism=next(x for x in core["population"] if x["id"]==target_id)
        parent=traits[target_id];before=parent["morphology_genome"]
        child,operator=mutate_v3(before,rng)
        start_m=time.process_time_ns();candidate=_trait(organism["genome"],child)
        counter=_trait(organism["genome"],before)
        inherited={k+":"+v:parent["feature_ages"].get(k+":"+v,0) for k,v in parent["features"].items()}
        candidate["origin"]={"kind":"within_lineage_morphology_change","organism_id":target_id,"parent_morphology_hash":digest(before),"operator":operator,"archive_genotype_donor":False}
        _update_feature_history(s,candidate,core["step"],inherited)
        candidate["development_fuel"]+=counter["development_fuel"]
        elapsed=time.process_time_ns()-start_m
        changed=digest(before)!=digest(child);effect=candidate["phenotype_hash"]!=counter["phenotype_hash"]
        sphere_return=not parent["descriptor"]["all_spheres"] and candidate["descriptor"]["all_spheres"]
        collapse=parent["descriptor"]["spatial_span"]>0 and candidate["descriptor"]["spatial_span"]<.4*parent["descriptor"]["spatial_span"]
        silhouette_changed=parent["descriptor"]["silhouette_hash"]!=candidate["descriptor"]["silhouette_hash"]
        s["morphology_fuel"]+=candidate["development_fuel"];s["morphology_cpu_ns"]+=elapsed
        s["morphology_changes"]+=int(changed);s["morphology_effects"]+=int(effect);s["morphology_neutral"]+=int(changed and not effect)
        s["sphere_return_events"]+=int(sphere_return);s["spatial_collapse_events"]+=int(collapse);s["silhouette_effects"]+=int(silhouette_changed)
        s["morphology_events"]+=1;s["dual_rate_events"]+=1
        _record_archive(s["archive"],candidate,core["step"],target_id)
        traits[target_id]=candidate
        morph_events.append({"kind":"within_lineage_morphology_change","organism_id":target_id,"parent_hash":digest(before),
                             "morphology_hash":candidate["morphology_hash"],"phenotype_hash":candidate["phenotype_hash"],
                             "operator":operator,"genotype_changed":changed,"phenotype_changed":effect,"cpu_ns":elapsed,
                             "silhouette_changed":silhouette_changed,"sphere_return":sphere_return,"spatial_collapse":collapse,
                             "fuel":candidate["development_fuel"],"origin":candidate["origin"],
                             "morphology_genome":child,"phenotype":candidate["phenotype"],
                             "descriptor":candidate["descriptor"],"niche":candidate["niche"],
                             "feature_ages":candidate["feature_ages"],"organism_snapshot":copy.deepcopy(organism)})
    s["core"]=core;s["traits"]=traits;s["morphology_rng"]=rng.getstate()
    s["morphology_rng_transitions"]+=1
    prev_n=len(s["archive"]);active_unique=len({x["phenotype_hash"] for x in traits.values()})
    e={"index":event["index"],"episode":event["episode"],"protocol":PROTOCOL,"arm":s["arm"],
       "computational":event,"morphology_selection":morphology_selection,
       "morphology_births":morph_births,"morphology_events":morph_events,
       "active_unique_forms":active_unique,"active_niches":len({tuple(x["niche"]) for x in traits.values()}),
       "archive_size":prev_n,"morphology_fuel_total":s["morphology_fuel"],"cpu_ns":time.process_time_ns()-start}
    e["decision_hash"]=digest({"core":core,"rng":s["morphology_rng"],"traits":{k:(v["morphology_hash"],v["phenotype_hash"]) for k,v in traits.items()},"archive":s["archive"],"arm":s["arm"]})
    e["state_hash"]=digest(s)
    return s,e


def public_metrics(state):
    if state.get("protocol")=="samo-ecology-v6-morphology":
        return {"control":"unchanged_v6_neutral","morphology_protocol":"samo-morphogenesis-2",
                **public_metrics6(state)}
    traits=state["traits"].values()
    desc=[x["descriptor"] for x in traits]
    return {"active_unique_phenotype_hashes":len({x["phenotype_hash"] for x in traits}),
            "active_unique_silhouettes":len({x["descriptor"]["silhouette_hash"] for x in traits}),
            "occupied_live_niches":len({tuple(x["niche"]) for x in traits}),
            "archive_descriptor_cells":len(state["archive"]),
            "all_sphere_active_forms":sum(x["descriptor"]["all_spheres"] for x in traits),
            "spatially_compact_active_forms":sum(x["descriptor"]["spatially_compact"] for x in traits),
            "sphere_return_events":state["sphere_return_events"],"spatial_collapse_events":state["spatial_collapse_events"],
            "silhouette_effects":state["silhouette_effects"],"feature_reappearances":state["feature_reappearances"],
            "mean_spatial_span":sum(x["spatial_span"] for x in desc)/max(1,len(desc)),
            "mean_radius_of_gyration":sum(x["radius_of_gyration"] for x in desc)/max(1,len(desc)),
            "morphology_births":state["morphology_births"],"morphology_events":state["morphology_events"],
            "dual_rate_events":state["dual_rate_events"],"morphology_changes":state["morphology_changes"],
            "initial_morphology_assignments":state["initial_morphology_assignments"],
            "phenotype_effects":state["morphology_effects"],"neutral_changes":state["morphology_neutral"],
            "max_observed_lineage_feature_age":max((x["max_lineage_age"] for x in state["feature_history"].values()),default=0),
            "bounded_feature_history":len(state["feature_history"]),"feature_history_evictions":state["feature_evictions"],
            "archive_niches":len(state["archive"]),"morphology_fuel":state["morphology_fuel"],
            "morphology_cpu_ns":state["morphology_cpu_ns"]}
