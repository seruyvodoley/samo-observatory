#!/usr/bin/env python3
"""Preregistered, sequential, byte-matched v6/v7 comparison matrix."""
from __future__ import annotations
import argparse,json,os,subprocess,sys,time,zlib,sqlite3
from pathlib import Path
from samo.genome_v4 import digest
from morphology.ecology_v7 import ALL_ARMS,CONTROL,PROTOCOL_HASH
from morphology.runtime_v7 import source_hash

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=json.loads((ROOT/"protocols/ecology-v7-morphology.json").read_text())
SEEDS=PROTOCOL["seeds"]
TIERS=[x["name"] for x in PROTOCOL["budget_tiers"]]
CEILING=PROTOCOL["retention"]["matrix_archive_max_bytes"]

def events(path,arm):
    c=sqlite3.connect(path)
    try:
        rows=c.execute("select n,payload,hash from events order by n").fetchall()
        out={};vetoes=[]
        for n,b,h in rows:
            e=json.loads(zlib.decompress(b))
            if e.get("index")!=n or digest(e)!=h:raise ValueError("event integrity failure at step "+str(n))
            # Both v6 control and v7 events wrap the frozen compute transition
            # under the same key. Hashing the outer v6 envelope accidentally
            # compared morphology metadata to compute-only payloads.
            comp=compute_projection(e)
            out[n]=digest(comp)
            if comp.get("morphology_veto"):vetoes.append(n)
        return out,vetoes
    finally:c.close()

def compute_projection(event):
    """Return the comparable compute transition from either protocol envelope."""
    comp=event.get("computational")
    if not isinstance(comp,dict):
        raise ValueError("event is missing its computational transition")
    return comp

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",default="/mnt/samo-v7/state/matrix");p.add_argument("--seeds",nargs="*",type=int,default=SEEDS);p.add_argument("--tiers",nargs="*",choices=TIERS,default=TIERS)
    a=p.parse_args();root=Path(a.root);root.mkdir(parents=True,exist_ok=True)
    protocol_bytes=PROTOCOL_HASH
    manifest={"protocol":"samo-ecology-v7-morphology","protocol_hash":protocol_bytes,"source_hash":source_hash(),
              "registered_seeds":SEEDS,"executed_seeds":a.seeds,"executed_tiers":a.tiers,
              "arms":ALL_ARMS,"started_unix_ns":time.time_ns(),"runs":[],"compute_core_replay":[],"status":"running"}
    journal=root/"matrix.jsonl"; summary=root/"matrix-summary.json"
    for tier in a.tiers:
        for seed in a.seeds:
            seed_rows=[]
            for arm in ALL_ARMS:
                key=f"{tier}-s{seed}-{arm}"
                db=root/(key+".sqlite");out=root/(key+".json")
                if db.exists() or out.exists():
                    row={"key":key,"seed":seed,"arm":arm,"tier":tier,"status":"preexisting_artifact_collision"}
                    manifest["runs"].append(row)
                else:
                    fs=os.statvfs(root)
                    used=(fs.f_blocks-fs.f_bfree)*fs.f_frsize
                    if used>=CEILING-70_000_000:
                        row={"key":key,"seed":seed,"arm":arm,"tier":tier,"status":"not_started_archive_budget_guard","used_bytes":used}
                        manifest["runs"].append(row)
                    else:
                        cmd=[sys.executable,str(ROOT/"tools/run_v7_comparison.py"),"--seed",str(seed),"--arm",arm,"--tier",tier,"--db",str(db),"--summary",str(out)]
                        started=time.time_ns()
                        try:
                            result=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=3600)
                            if result.returncode==0 and out.exists():
                                row=json.loads(out.read_text());row["status"]="completed";row["key"]=key
                            else:
                                row={"key":key,"seed":seed,"arm":arm,"tier":tier,"status":"failed","exit_code":result.returncode,
                                     "stderr_tail":result.stderr[-4000:],"stdout_tail":result.stdout[-1000:],"elapsed_ns":time.time_ns()-started}
                        except subprocess.TimeoutExpired as e:
                            row={"key":key,"seed":seed,"arm":arm,"tier":tier,"status":"timeout","elapsed_ns":time.time_ns()-started,
                                 "stderr_tail":str(e.stderr)[-1000:]}
                manifest["runs"].append(row);seed_rows.append(row)
                with journal.open("a") as f:f.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n");f.flush();os.fsync(f.fileno())
                tmp=summary.with_suffix(".tmp");tmp.write_text(json.dumps(manifest,sort_keys=True,separators=(",",":")));os.replace(tmp,summary)
            completed={x["arm"]:x for x in seed_rows if x.get("status")=="completed"}
            common=[];maps={};veto_steps={}
            for arm,row in completed.items():
                try:maps[arm],veto_steps[arm]=events(root/(row["key"]+".sqlite"),arm)
                except Exception as exc:maps[arm]={};veto_steps[arm]=[];manifest["compute_core_replay"].append({"seed":seed,"tier":tier,"arm":arm,"status":"read_error","error":str(exc)})
            if CONTROL in maps:
                keys=set(maps[CONTROL])
                for arm,em in maps.items():
                    overlap=sorted(keys&set(em))
                    mismatch=[i for i in overlap if maps[CONTROL][i]!=em[i]]
                    expected=arm=="v7_niche_survival"
                    first=mismatch[0] if mismatch else None
                    common.append({"arm":arm,"shared_steps":len(overlap),"mismatches":len(mismatch),"first_mismatch":first,
                                   "registered_compute_selection_intervention":expected,
                                   "veto_logged_at_or_before_first_mismatch":bool(expected and first is not None and any(x<=first for x in veto_steps.get(arm,[]))),
                                   "status":"expected_selection_divergence" if expected and mismatch else "identical" if not mismatch else "unexpected_divergence"})
                manifest["compute_core_replay"].append({"seed":seed,"tier":tier,"results":common})
        tmp=summary.with_suffix(".tmp");tmp.write_text(json.dumps(manifest,sort_keys=True,separators=(",",":")));os.replace(tmp,summary)
    manifest["ended_unix_ns"]=time.time_ns()
    statuses={}
    for row in manifest["runs"]:statuses[row["status"]]=statuses.get(row["status"],0)+1
    manifest["status"]="complete" if all(row.get("status")=="completed" for row in manifest["runs"]) else "partial_or_failed"
    manifest["status_counts"]=statuses
    manifest["total_archive_bytes"]=sum(x.stat().st_size for x in root.iterdir() if x.is_file())
    tmp=summary.with_suffix(".tmp");tmp.write_text(json.dumps(manifest,sort_keys=True,separators=(",",":")));os.replace(tmp,summary)
    print(json.dumps({k:manifest[k] for k in ("status","status_counts","total_archive_bytes","compute_core_replay")},sort_keys=True))
    if manifest["total_archive_bytes"]>CEILING:raise SystemExit("matrix archive exceeded registered ceiling")
    if any(x.get("mismatches",0) and x.get("arm")!="v7_niche_survival" for y in manifest["compute_core_replay"] for x in y.get("results",[])):
        raise SystemExit("frozen computational core divergence detected")
    if any(x.get("mismatches",0) and not x.get("veto_logged_at_or_before_first_mismatch") for y in manifest["compute_core_replay"] for x in y.get("results",[]) if x.get("arm")=="v7_niche_survival"):
        raise SystemExit("unlogged compute-selection divergence in niche-survival arm")

if __name__=="__main__":main()
