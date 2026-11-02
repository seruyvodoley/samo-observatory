"""Read-only, bounded lineage snapshot exporter for the v7 observatory."""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import re
import time
from pathlib import Path

from samo.genome_v4 import canonical, digest
from .development_v3 import VERSION
from .runtime_v7 import PROTOCOL, Recorder, _form, source_hash, unpack

MAX_FORMS = 160
MAX_BYTES = 3_800_000


def _history_forms(recorder: Recorder) -> list[dict]:
    forms: list[dict] = []
    for n, blob, expected in recorder.db.execute("SELECT n,payload,hash FROM events ORDER BY n"):
        event = unpack(blob)
        if event.get("index") != n or digest(event) != expected:
            raise ValueError(f"event integrity mismatch at {n}")
        comp = event["computational"]
        organisms = [x["organism"] for x in comp.get("lifecycle", []) if x.get("kind") == "founder"]
        if comp.get("candidate") is not None and comp.get("accepted"):
            organisms.append(comp["candidate"])
        morph = {x["id"]: x for x in event.get("morphology_births", [])}
        for organism in organisms:
            row = morph.get(organism["id"])
            if not row:
                continue
            trait = {"morphology_genome": row["genotype"], "morphology_hash": row["morphology_hash"],
                     "phenotype_hash": row["phenotype_hash"], "phenotype": row["phenotype"],
                     "descriptor": row["descriptor"], "niche": row["niche"], "interpreter": VERSION,
                     "origin": row.get("origin"), "feature_ages": row.get("feature_ages", {})}
            forms.append(_form(organism, trait, view_id=f"{organism['id']}@birth-{n}", step=n))
        for change in event.get("morphology_events", []):
            organism = change.get("organism_snapshot")
            if not organism:
                continue
            trait = {"morphology_genome": change["morphology_genome"], "morphology_hash": change["morphology_hash"],
                     "phenotype_hash": change["phenotype_hash"], "phenotype": change["phenotype"],
                     "descriptor": change["descriptor"], "niche": change["niche"], "interpreter": VERSION,
                     "origin": change.get("origin"), "feature_ages": change.get("feature_ages", {})}
            forms.append(_form(organism, trait, view_id=f"{organism['id']}@morph-{n}", step=n))
    return forms


def lineage_snapshot(recorder: Recorder) -> dict:
    state = recorder.load()
    if state is None or state.get("protocol") != PROTOCOL:
        raise ValueError("no v7 checkpoint")
    historical = _history_forms(recorder)
    by_organism: dict[str, dict] = {}
    for form in historical:
        by_organism[form.get("organism_id") or form["id"]] = form
    active: list[dict] = []
    for organism in state["core"]["population"]:
        form = _form(organism, state["traits"][organism["id"]])
        active.append(form)
        by_organism[form["id"]] = form

    ordered = sorted(by_organism.values(), key=lambda f: (f["born"], int(re.search(r"(?:birth|morph)-(\d+)$", f["id"]).group(1)) if re.search(r"(?:birth|morph)-(\d+)$", f["id"]) else -1, f["id"]))
    selected: dict[str, dict] = {}
    queue: list[str] = []
    roots = ordered[-8:] + active
    for form in roots:
        key = form.get("organism_id") or form["id"]
        if key not in selected:
            selected[key] = form
            queue.append(key)
    truncated = False
    missing: set[str] = set()
    at = 0
    while at < len(queue):
        key = queue[at]
        at += 1
        for parent in selected[key].get("parents", []):
            if parent in selected:
                continue
            ancestor = by_organism.get(parent)
            if ancestor is None:
                missing.add(parent)
                continue
            if len(selected) >= MAX_FORMS:
                truncated = True
                missing.add(parent)
                continue
            selected[parent] = ancestor
            queue.append(parent)
    records = sorted(selected.values(), key=lambda f: (f["born"], f["id"]))
    for form in records:
        morphology = form.get("morphology")
        if morphology and isinstance(morphology.get("phenotype_payload"), str):
            raw = morphology.pop("phenotype_payload").encode("utf-8")
            morphology["phenotype_payload_gzip"] = base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")
    payload = {"step": state["core"]["step"], "forms": records,
               "truncated": truncated, "missing_parent_ids": sorted(missing)}
    payload_raw = canonical(payload)
    data = {"schema": 1, "protocol": PROTOCOL, "source_hash": source_hash(), "step": state["core"]["step"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "forms_payload": payload_raw.decode("utf-8"), "snapshot_id": digest(payload)}
    if len(canonical(data)) > MAX_BYTES:
        raise ValueError("lineage snapshot size ceiling")
    return data


def export_file(db: str, output: str) -> None:
    recorder = Recorder(db, readonly=True)
    try:
        data = lineage_snapshot(recorder)
    finally:
        recorder.close()
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    tmp = target.with_suffix(target.suffix + ".tmp")
    raw = canonical(data)
    with open(tmp, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, target)
    dfd = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    export_file(args.db, args.output)
    print("lineage snapshot published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
