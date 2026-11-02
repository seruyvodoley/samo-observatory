"""Bounded SQLite recorder/exporter for the isolated v7 research candidate."""
from __future__ import annotations

import hashlib
import json
import os
import argparse
import signal
import sqlite3
import sys
import time
import zlib
from pathlib import Path

from samo.genome_v4 import canonical, digest
from .development_v3 import VERSION, develop_v3, validate
from .ecology_v7 import ALL_ARMS, ARMS, PROTOCOL, PROTOCOL_HASH, advance, initial, public_metrics

RECENT = 1024
DB_LIMIT = 64_000_000
STATE_LIMIT = 2_000_000
EVENT_LIMIT = 2_000_000


def source_hash():
    root=Path(__file__).resolve().parents[1]
    files=[p for p in (root/"samo").glob("*.py") if not p.name.startswith("._")]
    files += [root/"morphology"/x for x in ("development.py","development_v2.py","development_v3.py","ecology_v6.py","ecology_v7.py","runtime_v7.py")]
    files += [root/"protocols/ecology-v7-morphology.json",
              root/"tools/run_v7_comparison.py",root/"tools/run_v7_matrix.py",
              root/"tools/verify_v7_matrix_archive.py",
              root/"tools/verify_v7_isolation.py",root/"deploy/samo-organism-v7.service",
              root/"web/package.json",root/"web/package-lock.json",root/"web/index.html"]
    files += [root/"tests/morphology/test_v7_candidate.py",
              root/"tests/morphology/test_v7_matrix_verifier.py"]
    files += [p for p in (root/"web/src").rglob("*") if p.is_file() and p.suffix in (".ts",".tsx",".css",".svg")]
    return digest({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)})


def unpack(blob, limit=EVENT_LIMIT):
    d=zlib.decompressobj();raw=d.decompress(blob,limit+1)
    if len(raw)>limit or not d.eof or d.unused_data:raise ValueError("compressed record limit or corruption")
    return json.loads(raw)


class Recorder:
    def __init__(self,path,readonly=False):
        self.path=Path(path)
        if readonly:
            src=sqlite3.connect(self.path.resolve().as_uri()+"?mode=ro",uri=True);self.db=sqlite3.connect(":memory:")
            try:src.backup(self.db,pages=64,sleep=.01)
            finally:src.close()
            self.db.execute("BEGIN");return
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o640);os.close(fd)
        self.db=sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=DELETE");self.db.execute("PRAGMA synchronous=FULL");self.db.execute("PRAGMA max_page_count=16384")
        self.db.executescript("""CREATE TABLE IF NOT EXISTS checkpoint(id INTEGER PRIMARY KEY,payload BLOB,hash TEXT,source TEXT);
        CREATE TABLE IF NOT EXISTS events(n INTEGER PRIMARY KEY,payload BLOB,hash TEXT);
        CREATE TABLE IF NOT EXISTS retention(id INTEGER PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS protocol(id INTEGER PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS run(id INTEGER PRIMARY KEY,payload TEXT);""")

    def load(self):
        row=self.db.execute("SELECT payload,hash,source FROM checkpoint WHERE id=1").fetchone()
        if not row:return None
        state=unpack(row[0],STATE_LIMIT)
        if digest(state)!=row[1] or row[2]!=source_hash():raise ValueError("checkpoint hash/source mismatch")
        if state["protocol"]!=PROTOCOL or state["protocol_hash"]!=PROTOCOL_HASH or state["arm"] not in ALL_ARMS:raise ValueError("protocol mismatch")
        if state["arm"]=="v6_neutral":return state
        if set(state["traits"])!={x["id"] for x in state["core"]["population"]}:raise ValueError("active trait identity mismatch")
        for org in state["core"]["population"]:
            trait=state["traits"][org["id"]];validate(trait["morphology_genome"])
            out=develop_v3(org["genome"],trait["morphology_genome"])
            if out["morphology_hash"]!=trait["morphology_hash"] or out["phenotype_hash"]!=trait["phenotype_hash"]:raise ValueError("phenotype integrity mismatch")
        if len(state["feature_history"])>512 or len(state["archive"])>64:raise ValueError("unbounded ecology state")
        return state

    def initialize(self,seed,arm="v7_neutral",size=4,mode="meta"):
        existing=self.load()
        if existing is not None:
            run_row=self.db.execute("SELECT payload FROM run WHERE id=1").fetchone()
            config=json.loads(run_row[0]) if run_row else {}
            if (existing.get("arm")!=arm or config.get("seed")!=seed or
                    config.get("size")!=size or config.get("mode")!=mode):
                raise ValueError("resume configuration does not match registered run")
            return
        if self.db.execute("SELECT count(*) FROM events").fetchone()[0]:raise ValueError("events exist without checkpoint")
        s=initial(seed,size=size,mode=mode,arm=arm)
        raw=canonical(s)
        with self.db:
            self.db.execute("INSERT INTO checkpoint VALUES(1,?,?,?)",(zlib.compress(raw),digest(s),source_hash()))
            self.db.execute("INSERT INTO protocol VALUES(1,?)",(json.dumps({"protocol":PROTOCOL,"hash":PROTOCOL_HASH,"arm":arm,"registered_at":time.time()}),))
            initial_assignments=[{"organism_id":org_id,"morphology_hash":trait["morphology_hash"],
                                  "phenotype_hash":trait["phenotype_hash"],"origin":trait["origin"]}
                                 for org_id,trait in sorted(s.get("traits",{}).items())]
            run={"seed":seed,"size":size,"mode":mode,"arm":arm,"source_hash":source_hash(),
                 "initial_morphology_assignments":initial_assignments}
            self.db.execute("INSERT INTO run VALUES(1,?)",(json.dumps(run,sort_keys=True,separators=(",",":")),))

    def commit(self,state,event):
        if self.path.stat().st_size*2+4_000_000>DB_LIMIT:raise RuntimeError("database safety ceiling")
        sr=canonical(state);er=canonical(event)
        if len(sr)>STATE_LIMIT or len(er)>EVENT_LIMIT:raise ValueError("record size ceiling")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO checkpoint VALUES(1,?,?,?)",(zlib.compress(sr),digest(state),source_hash()))
            self.db.execute("INSERT INTO events VALUES(?,?,?)",(event["index"],zlib.compress(er),digest(event)))
            if state["core"]["step"]>RECENT:
                before=state["core"]["step"]-RECENT
                rows=self.db.execute("SELECT n,hash FROM events WHERE n<? ORDER BY n",(before,)).fetchall()
                prior=self.db.execute("SELECT payload FROM retention WHERE id=1").fetchone()
                acc=json.loads(prior[0]) if prior else {"pruned_records":0,"root":digest([]),"through":-1}
                for n,h in rows:acc={"root":digest([acc["root"],n,h]),"through":n,"pruned_records":acc["pruned_records"]+1}
                self.db.execute("INSERT OR REPLACE INTO retention VALUES(1,?)",(json.dumps(acc,separators=(",",":")),))
                self.db.execute("DELETE FROM events WHERE n<?",(before,))
            if self.path.stat().st_size>DB_LIMIT:raise RuntimeError("database hard ceiling reached")

    def close(self):self.db.close()


def _form(org,trait,view_id=None,step=None):
    genome_hash=digest(org["genome"])
    return {"id":view_id or org["id"],"organism_id":org["id"],"parents":org["parents"],
            "source":org["source"],"born":org["born"],"genome":org["genome"],"hash":genome_hash,
            "identity_hash":digest([genome_hash,trait["morphology_hash"],trait["interpreter"]]),
            "origin":trait.get("origin"),"morphology":{
                "morphology_genome":trait["morphology_genome"],"morphology_hash":trait["morphology_hash"],
                "phenotype_hash":trait["phenotype_hash"],"phenotype_payload":canonical(trait["phenotype"]).decode(),
                "phenotype_payload_hash":digest(trait["phenotype"]),
                "descriptor":trait["descriptor"],"niche":trait["niche"],"interpreter":trait["interpreter"],
                "origin":trait.get("origin"),"feature_ages":trait.get("feature_ages",{}),
                "development_fuel":trait.get("development_fuel",0),"truncated":trait.get("truncated",False)}}


def snapshot(recorder):
    s=recorder.load()
    if s is None:raise ValueError("no checkpoint")
    if s.get("arm")=="v6_neutral":
        from .runtime_v6 import snapshot as snapshot6
        # Do not change the control's representation or source; it is exported by v6 runtime.
        return snapshot6(recorder)
    events=[];history=[]
    for n,blob,h in recorder.db.execute("SELECT n,payload,hash FROM events ORDER BY n"):
        ev=unpack(blob)
        if ev["index"]!=n or digest(ev)!=h:raise ValueError("event hash mismatch")
        births=[]
        comp=ev["computational"]
        organisms=[x["organism"] for x in comp.get("lifecycle",[]) if x.get("kind")=="founder"]
        if comp.get("candidate") is not None and comp.get("accepted"):organisms.append(comp["candidate"])
        morph_by_id={x["id"]:x for x in ev["morphology_births"]}
        for org in organisms:
            row=morph_by_id.get(org["id"])
            if row:
                trait={"morphology_genome":row["genotype"],"morphology_hash":row["morphology_hash"],
                       "phenotype_hash":row["phenotype_hash"],"phenotype":row["phenotype"],
                       "descriptor":row["descriptor"],"niche":row["niche"],"interpreter":VERSION,
                       "origin":row["origin"],"feature_ages":row.get("feature_ages",{})}
                births.append(_form(org,trait,view_id=f"{org['id']}@birth-{n}",step=n))
        for change in ev["morphology_events"]:
            org=change.get("organism_snapshot")
            if org:
                trait={"morphology_genome":change["morphology_genome"],"morphology_hash":change["morphology_hash"],
                       "phenotype_hash":change["phenotype_hash"],"phenotype":change["phenotype"],
                       "descriptor":change["descriptor"],"niche":change["niche"],"interpreter":VERSION,
                       "origin":change["origin"],"feature_ages":change.get("feature_ages",{})}
                births.append(_form(org,trait,view_id=f"{org['id']}@morph-{n}",step=n))
        history.extend(births)
        comp=ev["computational"]
        lifecycle=[{"kind":x.get("kind","event"),"id":x.get("id") or x.get("organism",{}).get("id"),
                    "reason":x.get("reason"),"source":x.get("organism",{}).get("source")} for x in comp.get("lifecycle",[])]
        events.append({"index":n,"episode":ev["episode"],"kind":comp.get("kind","attempt"),
                       "family":next((x.get("result",{}).get("family") for x in comp.get("evaluations",[]) if x.get("result",{}).get("family")),"unknown"),
                       "lifecycle":lifecycle,"compute_birth":comp.get("birth",False),
                       "accepted":comp.get("accepted",False),
                       "morphology_selection":ev.get("morphology_selection"),
                       "morphology_births":[{k:x[k] for k in ("id","parents","source","phenotype_hash","silhouette_hash","descriptor","niche","operator","selection_rule","genotype_changed","phenotype_changed","origin") if k in x} for x in ev["morphology_births"]],
                       "morphology_events":[{k:x[k] for k in ("kind","organism_id","parent_hash","morphology_hash","phenotype_hash","operator","genotype_changed","phenotype_changed","origin","descriptor","niche") if k in x} for x in ev["morphology_events"]],"active_unique_forms":ev["active_unique_forms"],
                       "active_niches":ev["active_niches"],"cpu_ns":ev["cpu_ns"],"morphology_fuel_total":ev["morphology_fuel_total"]})
    population=[_form(x,s["traits"][x["id"]]) for x in s["core"]["population"]]
    history_total=len(history);events_total=len(events)
    history=history[-8:];events=events[-128:]
    retention=recorder.db.execute("SELECT payload FROM retention WHERE id=1").fetchone()
    run_row=recorder.db.execute("SELECT payload FROM run WHERE id=1").fetchone()
    run_config=json.loads(run_row[0]) if run_row else {}
    data={"schema":1,"protocol":PROTOCOL,"protocol_hash":PROTOCOL_HASH,"source_hash":source_hash(),
          "arm":s["arm"],"generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
          "run":{"seed":run_config.get("seed"),"size":run_config.get("size"),
                 "mode":run_config.get("mode"),"arm":run_config.get("arm"),
                 "source_hash":run_config.get("source_hash")},
          "observation":{"observed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
                         "status":"latest_saved","environment":"registered v7 research runtime"},
          "step":s["core"]["step"],"episode":s["core"]["episode"],"attempts":s["core"]["attempts"],
          "births":s["core"]["births"],"deaths":s["core"]["deaths"],"recolonizations":s["core"]["recolonizations"],
          "fuel":s["core"]["fuel"]+s["morphology_fuel"],"computational_fuel":s["core"]["fuel"],
          "morphology_fuel":s["morphology_fuel"],"population":population,"events":events,
          "history":history,"episodes":s["core"]["episodes"],
          "initial_morphology_assignments":run_config.get("initial_morphology_assignments",[]),
          "retention":{**(json.loads(retention[0]) if retention else {"pruned_records":0,"root":digest([]),"through":-1}),
              "snapshot_history_omitted":history_total-len(history),"snapshot_events_omitted":events_total-len(events),
              "snapshot_first_event":events[0]["index"] if events else None},
          "morphology":{"active_unique_forms":public_metrics(s)["active_unique_phenotype_hashes"],
              "active_unique_silhouettes":public_metrics(s)["active_unique_silhouettes"],
              "occupied_active_niches":public_metrics(s)["occupied_live_niches"],
              "bounded_archive_niches":public_metrics(s)["archive_descriptor_cells"],
              "morphology_births":s["morphology_births"],"morphology_events":s["morphology_events"],
              "morphology_changes":s["morphology_changes"],"neutral_morphology_changes":s["morphology_neutral"],
              "phenotype_effects":s["morphology_effects"],"sphere_returns":s["sphere_return_events"],
              "spatial_collapse_events":s["spatial_collapse_events"],
              "max_structural_retention_steps":public_metrics(s)["max_observed_lineage_feature_age"],
              "morphology_fuel":s["morphology_fuel"],"morphology_cpu_ns":s["morphology_cpu_ns"]},
          "telemetry":{**public_metrics(s),"unique_genomes":len({digest(x["genome"]) for x in s["core"]["population"]}),
              "genotype_changes":s["core"]["genotype_changes"],"behavior_changes":s["core"]["behavior_changes"],
              "search_errors":s["core"]["search_errors"],"stagnant_attempts":s["core"]["stagnant_attempts"],
              "independent_accuracy":None},
          "computational":{"protocol":"samo-ecology-v4","training_accuracy":None,
              "independent_accuracy":None,"capability_status":"not_independently_assessed"},
          "claims":["Morphology diversity is not evidence of prediction ability.","Archive cells store descriptors only; archived genotypes are never revived.","A within-line morphology event does not create a computational birth."]}
    data["snapshot_id"]=digest(data)
    if len(canonical(data))>4_000_000:raise ValueError("public snapshot size ceiling")
    return data


def export_file(path,data):
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    raw=canonical(data)
    if len(raw)>4_000_000:raise ValueError("snapshot public size limit")
    tmp=target.with_suffix(target.suffix+".tmp")
    with open(tmp,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.chmod(tmp,0o644);os.replace(tmp,target)
    dfd=os.open(target.parent,os.O_RDONLY)
    try:os.fsync(dfd)
    finally:os.close(dfd)


def _cli():
    parser=argparse.ArgumentParser(description="Bounded SAMO v7 organism runtime")
    sub=parser.add_subparsers(dest="command",required=True)
    run=sub.add_parser("run",help="resume or initialize the registered organism and continuously export its state")
    run.add_argument("--db",required=True);run.add_argument("--seed",type=int,required=True)
    run.add_argument("--arm",choices=ARMS,default="v7_neutral")
    run.add_argument("--export",required=True);run.add_argument("--pause",type=float,default=1.0)
    run.add_argument("--max-steps",type=int,default=0,help=argparse.SUPPRESS)
    export=sub.add_parser("export",help="publish a verified static snapshot from the latest checkpoint")
    export.add_argument("--db",required=True);export.add_argument("--output",required=True)
    verify=sub.add_parser("verify",help="verify the checkpoint and SQLite integrity without changing state")
    verify.add_argument("--db",required=True)
    args=parser.parse_args()
    if args.command=="run":
        if args.pause<0 or args.pause>3600 or args.max_steps<0:parser.error("invalid pause or step limit")
        stop=False
        def request_stop(_signum,_frame):
            nonlocal stop;stop=True
        signal.signal(signal.SIGTERM,request_stop);signal.signal(signal.SIGINT,request_stop)
        recorder=Recorder(args.db)
        try:
            recorder.initialize(args.seed,arm=args.arm)
            state=recorder.load();start_step=state["core"]["step"]
            # Publish only after the first transition has created the current
            # founder population; this avoids exporting a misleading empty view.
            completed=0
            while not stop:
                state,event=advance(state)
                recorder.commit(state,event);completed+=1
                export_file(args.export,snapshot(recorder))
                print(json.dumps({"step":state["core"]["step"],"episode":state["core"]["episode"],
                                  "active":len(state["core"]["population"]),"event":event["computational"].get("kind",event.get("kind")),
                                  "snapshot":str(args.export)},separators=(",",":")),flush=True)
                if args.max_steps and completed>=args.max_steps:break
                if args.pause:time.sleep(args.pause)
        finally:recorder.close()
        return 0
    recorder=Recorder(args.db,readonly=args.command=="verify")
    try:
        state=recorder.load()
        if state is None:raise ValueError("no checkpoint")
        if args.command=="export":export_file(args.output,snapshot(recorder))
        else:
            integrity=recorder.db.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity!="ok":raise ValueError("SQLite integrity check failed: "+str(integrity))
            print(json.dumps({"status":"verified","protocol":state["protocol"],"step":state["core"]["step"],
                              "episode":state["core"]["episode"],"active":len(state["core"]["population"]),
                              "integrity":integrity,"source_hash":source_hash()},sort_keys=True))
    finally:recorder.close()
    return 0


if __name__=="__main__":
    try:raise SystemExit(_cli())
    except Exception as exc:
        print(json.dumps({"status":"error","error":type(exc).__name__,"detail":str(exc)},sort_keys=True),file=sys.stderr)
        raise SystemExit(1)
