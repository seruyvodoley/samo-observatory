#!/usr/bin/env python3
"""Verify saved v7 matrix rows without changing the archived experiments."""
from __future__ import annotations
import argparse, json, sqlite3, zlib
from pathlib import Path
from samo.genome_v4 import digest


def read_compute_events(path: Path):
    db=sqlite3.connect(path)
    try:
        out={};vetoes=[]
        for n,payload,stored_hash in db.execute("select n,payload,hash from events order by n"):
            event=json.loads(zlib.decompress(payload))
            if event.get("index")!=n or digest(event)!=stored_hash:
                raise ValueError(f"event integrity failure at {path.name}:{n}")
            compute=event.get("computational")
            if not isinstance(compute,dict):
                raise ValueError(f"missing compute transition at {path.name}:{n}")
            out[n]=digest(compute)
            if compute.get("morphology_veto"):
                vetoes.append(n)
        return out,vetoes
    finally:
        db.close()


def verify(root: Path):
    rows=[json.loads(line) for line in (root/"matrix.jsonl").read_text().splitlines() if line]
    results=[]
    for control in (r for r in rows if r.get("arm")=="v6_neutral" and r.get("status")=="completed"):
        base,_=read_compute_events(root/(control["key"]+".sqlite"))
        cohort=[]
        for row in rows:
            if row.get("seed")!=control.get("seed") or row.get("tier")!=control.get("tier") or row.get("status")!="completed" or row.get("arm")=="v6_neutral":
                continue
            candidate,vetoes=read_compute_events(root/(row["key"]+".sqlite"))
            overlap=sorted(set(base)&set(candidate))
            mismatches=[n for n in overlap if base[n]!=candidate[n]]
            first=mismatches[0] if mismatches else None
            intentional=row["arm"]=="v7_niche_survival"
            logged=bool(intentional and first is not None and any(n<=first for n in vetoes))
            cohort.append({"arm":row["arm"],"shared_steps":len(overlap),"compute_mismatches":len(mismatches),
                           "first_mismatch":first,"registered_selection_intervention":intentional,
                           "veto_logged_before_divergence":logged,
                           "status":"registered_selection_divergence" if intentional and mismatches and logged else
                                    "unexpected_compute_divergence" if mismatches else "compute_identical"})
        results.append({"seed":control["seed"],"tier":control["tier"],"results":cohort})
    bad=[(x["seed"],x["tier"],r) for x in results for r in x["results"] if r["status"]=="unexpected_compute_divergence"]
    return {"archive":str(root),"runs":len(rows),"completed_runs":sum(r.get("status")=="completed" for r in rows),
            "original_matrix_status":json.loads((root/"matrix-summary.json").read_text()).get("status"),
            "original_comparator_warning":"control envelope was hashed instead of its computational projection",
            "event_hashes_verified":True,"unexpected_compute_divergences":len(bad),"replay":results}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("archive",type=Path);parser.add_argument("--output",type=Path)
    args=parser.parse_args();report=verify(args.archive)
    rendered=json.dumps(report,sort_keys=True,indent=2)
    if args.output:args.output.write_text(rendered+"\n")
    print(rendered)
    if report["unexpected_compute_divergences"]:raise SystemExit(1)


if __name__=="__main__":main()
