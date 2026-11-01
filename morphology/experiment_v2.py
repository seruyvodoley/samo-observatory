"""Seeded, bounded comparison of morphology representations and selection.

All records from this script are isolated benchmark attempts, never ecology
births and never production telemetry.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import math
import random
import sqlite3
import statistics
import os
import time
from pathlib import Path

from . import development as v1
from . import development_v2 as v2

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "protocols" / "ecology-v6-morphology-pilot.json"
CONDITIONS = ("v5-neutral", "v6-neutral", "v6-novelty", "v6-map-elites")


def seed_for(seed, step, channel):
    raw = f"morph-v6-pilot:{seed}:{step}:{channel}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def phenotype(genome, computational, condition):
    return (v1.develop(computational, genome) if condition == "v5-neutral"
            else v2.develop_v2(computational, genome))


def resident_bytes():
    """Current RSS sample; VM memory ceilings are enforced outside this process."""
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return None


def founder_for(seed, slot, condition):
    if condition == "v5-neutral":
        return v1.founder()
    return v2.founder_v2(random.Random(seed_for(seed, slot, "founder")))


def mutate_for(genome, rng, condition):
    return v1.mutate(genome, rng) if condition == "v5-neutral" else v2.mutate_v2(genome, rng)


def desc_for(result, condition):
    if condition == "v5-neutral":
        # v1 has the same measurable fields except anchor-shell semantics.
        return v2.describe(result["phenotype"])
    return v2.describe(result["phenotype"])


def _artifact(db, genome, result, descriptor, interpreter):
    identity = result["morphology_hash"]
    body = json.dumps({"genome": genome, "phenotype_hash": result["phenotype_hash"],
                       "descriptor": descriptor, "interpreter": interpreter},
                      sort_keys=True, separators=(",", ":"))
    db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?)", (identity, body))
    return identity


def _population_metrics(population, archive, artifacts):
    active_hashes = [item["phenotype_hash"] for item in population]
    active_descriptors = [item["descriptor"] for item in population]
    archive_hashes = [item["phenotype_hash"] for item in archive.values()]
    archive_descriptors = [item["descriptor"] for item in archive.values()]
    hamming = []
    for a, b in itertools.combinations(active_descriptors, 2):
        aa, bb = v2.niche(a), v2.niche(b)
        hamming.append(sum(x != y for x, y in zip(aa, bb)) / len(aa))
    return {"active_size": len(population), "archive_size": len(archive),
            "unique_phenotypes": len(set(active_hashes)),
            "occupied_niches": len({v2.niche(d) for d in active_descriptors}),
            "archive_unique_phenotypes": len(set(archive_hashes)),
            "archive_occupied_niches": len({v2.niche(d) for d in archive_descriptors}),
            "median_pairwise_descriptor_hamming": statistics.median(hamming) if hamming else 0.0}


def run(db_path, input_path):
    protocol = json.loads(PROTOCOL_PATH.read_text())
    computational = json.loads(Path(input_path).read_text())
    if len(json.dumps(computational, separators=(",", ":"))) > 100_000:
        raise ValueError("frozen computational genome exceeds input cap")
    protocol_hash = hashlib.sha256(json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    input_hash = v1.digest(computational)
    source_files = [Path(__file__), Path(v1.__file__), Path(v2.__file__), PROTOCOL_PATH]
    source_hash = v1.digest({p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files})
    identity = v1.digest({"protocol_hash": protocol_hash, "input_hash": input_hash, "source_hash": source_hash})
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA max_page_count=24414")  # 100 MB at 4096 bytes/page.
    db.executescript("""
      CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS artifacts (hash TEXT PRIMARY KEY, payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS founders (run_id TEXT NOT NULL, slot INTEGER NOT NULL,
        payload TEXT NOT NULL, PRIMARY KEY(run_id,slot));
      CREATE TABLE IF NOT EXISTS events (run_id TEXT NOT NULL, attempt INTEGER NOT NULL,
        payload TEXT NOT NULL, PRIMARY KEY(run_id,attempt));
      CREATE TABLE IF NOT EXISTS endpoints (run_id TEXT NOT NULL, attempt INTEGER NOT NULL,
        payload TEXT NOT NULL, PRIMARY KEY(run_id,attempt));
      CREATE TABLE IF NOT EXISTS results (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    """)
    old = dict(db.execute("SELECT key,value FROM meta"))
    if old and old.get("identity") != identity:
        raise ValueError("existing experiment database has different frozen inputs or sources")
    with db:
        for k, v in {"identity": identity, "protocol_hash": protocol_hash,
                      "input_hash": input_hash, "source_hash": source_hash}.items():
            db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", (k, v))

    seeds = protocol["design"]["paired_seed_ids"]
    steps = protocol["design"]["attempts_per_replicate_condition"]
    capacity = protocol["design"]["map_capacity"]
    for seed in seeds:
        for condition in CONDITIONS:
            run_id = f"{condition}/seed-{seed:02d}"
            prior = db.execute("SELECT payload FROM results WHERE run_id=?", (run_id,)).fetchone()
            if prior:
                stored = json.loads(prior[0])
                if stored["identity"] != identity:
                    raise ValueError("run identity mismatch")
                continue
            started_wall, started_cpu = time.monotonic(), time.process_time()
            population, archive, seen = [], {}, set()
            births = []
            for slot in range(protocol["design"]["starting_population_size"]):
                genome = founder_for(seed, slot, condition)
                result = phenotype(genome, computational, condition)
                descriptor = desc_for(result, condition)
                artifact_id = _artifact(db, genome, result, descriptor,
                                        "samo-morphogenesis-1" if condition == "v5-neutral" else v2.VERSION)
                item = {"id": f"{run_id}/founder-{slot}", "genome": genome,
                        "artifact": artifact_id, "phenotype_hash": result["phenotype_hash"],
                        "descriptor": descriptor, "parent": None}
                population.append(item)
                seen.add(result["phenotype_hash"])
                births.append(item["id"])
                if condition == "v6-map-elites":
                    archive.setdefault(v2.niche(descriptor), item)
                with db:
                    db.execute("INSERT OR REPLACE INTO founders VALUES(?,?,?)", (run_id, slot,
                               json.dumps({"id": item["id"], "artifact": artifact_id,
                                           "phenotype_hash": result["phenotype_hash"],
                                           "descriptor": descriptor, "genome": genome,
                                           "source": "registered_seeded_founder" if condition != "v5-neutral" else "registered_v5_founder"},
                                          sort_keys=True, separators=(",", ":"))))
            for attempt in range(1, steps + 1):
                selection_rng = random.Random(seed_for(seed, attempt, "selection"))
                mutation_rng = random.Random(seed_for(seed, attempt, "mutation"))
                if condition == "v6-map-elites" and archive:
                    parent = selection_rng.choice(list(archive.values()))
                else:
                    parent = selection_rng.choice(population)
                incumbent_slot = selection_rng.randrange(len(population))
                attempt_cpu = time.process_time()
                candidate_genome = result = descriptor = operator = candidate_artifact = None
                error = None
                try:
                    candidate_genome, operator = mutate_for(parent["genome"], mutation_rng, condition)
                    result = phenotype(candidate_genome, computational, condition)
                    descriptor = desc_for(result, condition)
                    changed = v1.digest(candidate_genome) != v1.digest(parent["genome"])
                    novel = result["phenotype_hash"] not in seen
                    accepted = changed and (condition != "v6-novelty" or novel)
                    interpreter = "samo-morphogenesis-1" if condition == "v5-neutral" else v2.VERSION
                    candidate_artifact = _artifact(db, candidate_genome, result, descriptor, interpreter)
                except Exception as exc:  # failed attempts are evidence, not dropped runs
                    changed = False
                    novel = False
                    accepted = False
                    interpreter = "samo-morphogenesis-1" if condition == "v5-neutral" else v2.VERSION
                    error = {"type": type(exc).__name__, "message": str(exc)[:240]}
                victim = population[incumbent_slot] if accepted else None
                event = {"run_id": run_id, "attempt": attempt,
                         "random_seed": seed_for(seed, attempt, "mutation"),
                         "selection_seed": seed_for(seed, attempt, "selection"),
                         "parent_id": parent["id"], "parent_artifact": parent["artifact"],
                         "candidate_artifact": candidate_artifact,
                         "phenotype_hash": result["phenotype_hash"] if result else None, "operator": operator,
                         "genotype_changed": changed, "phenotype_novel_to_replicate_history": novel,
                         "accepted": accepted,
                         "reason": "accepted" if accepted else "error" if error else "unchanged" if not changed else "phenotype_seen",
                         "victim_id": victim["id"] if victim else None,
                         "fuel": result["fuel"] if result else None, "truncated": result["truncated"] if result else None,
                         "descriptor": descriptor,
                         "interpreter": interpreter,
                         "cpu_seconds": time.process_time() - attempt_cpu,
                         "error": error,
                         "organism_birth": False}
                with db:
                    db.execute("INSERT OR REPLACE INTO events VALUES(?,?,?)", (run_id, attempt,
                               json.dumps(event, sort_keys=True, separators=(",", ":"))))
                if result:
                    seen.add(result["phenotype_hash"])
                if accepted:
                    child = {"id": f"{run_id}/attempt-{attempt}", "genome": candidate_genome,
                             "artifact": candidate_artifact, "phenotype_hash": result["phenotype_hash"],
                             "descriptor": descriptor, "parent": parent["id"]}
                    population[incumbent_slot] = child
                    births.append(child["id"])
                    if condition == "v6-map-elites":
                        cell = v2.niche(descriptor)
                        if cell not in archive:
                            if len(archive) >= capacity:
                                evict = selection_rng.choice(list(archive))
                                archive.pop(evict)
                            archive[cell] = child
                        elif selection_rng.random() < .5:
                            archive[cell] = child
                if attempt in (64, 128, steps):
                    endpoint = {"run_id": run_id, "attempt": attempt,
                                "metrics": _population_metrics(population, archive, None)}
                    with db:
                        db.execute("INSERT OR REPLACE INTO endpoints VALUES(?,?,?)", (run_id, attempt,
                                   json.dumps(endpoint, sort_keys=True, separators=(",", ":"))))
            elapsed_wall = time.monotonic() - started_wall
            elapsed_cpu = time.process_time() - started_cpu
            final = _population_metrics(population, archive, None)
            summary = {"run_id": run_id, "seed": seed, "condition": condition,
                       "identity": identity, "attempts": steps, "accepted": len(births)-len(population),
                       "final": final, "events": steps,
                       "unique_observed_phenotypes": len(seen),
                       "rss_bytes_at_run_end": resident_bytes(),
                       "cpu_seconds": elapsed_cpu, "wall_seconds": elapsed_wall,
                       "sqlite_bytes": Path(db_path).stat().st_size,
                       "all_attempts_retained": True}
            with db:
                db.execute("INSERT OR REPLACE INTO results VALUES(?,?)", (run_id,
                           json.dumps(summary, sort_keys=True, separators=(",", ":"))))
    db.close()
    return analyze(db_path)


def _median(values):
    return statistics.median(values) if values else None


def _bootstrap_median_ci(values, seed, samples=10000):
    if not values:
        return None
    rng = random.Random(seed)
    medians = [statistics.median(rng.choices(values, k=len(values))) for _ in range(samples)]
    medians.sort()
    return [medians[int(.025*(samples-1))], medians[int(.975*(samples-1))]]


def _sign_test_p(values):
    nonzero = [x for x in values if x]
    n = len(nonzero)
    if n == 0:
        return 1.0
    positive = sum(x > 0 for x in nonzero)
    tail = sum(math.comb(n, k) for k in range(min(positive, n-positive)+1)) / (2**n)
    return min(1.0, 2*tail)


def _holm(pairs):
    ordered = sorted(enumerate(pairs), key=lambda x: x[1]["p_raw"])
    adjusted = [1.0]*len(pairs)
    running = 0.0
    for rank, (index, item) in enumerate(ordered):
        running = max(running, min(1.0, (len(pairs)-rank)*item["p_raw"]))
        adjusted[index] = running
    for i, item in enumerate(pairs):
        item["p_holm"] = adjusted[i]
    return pairs


def analyze(db_path):
    db = sqlite3.connect(db_path)
    rows = [json.loads(x[0]) for x in db.execute("SELECT payload FROM results ORDER BY run_id")]
    completed = {row["run_id"] for row in rows}
    planned_seeds = json.loads(PROTOCOL_PATH.read_text())["design"]["paired_seed_ids"]
    for seed in planned_seeds:
        for condition in CONDITIONS:
            run_id = f"{condition}/seed-{seed:02d}"
            if run_id in completed:
                continue
            attempted = db.execute("SELECT COUNT(*) FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
            rows.append({"run_id": run_id, "seed": seed, "condition": condition,
                         "status": "incomplete", "attempts_recorded": attempted,
                         "all_attempts_retained": attempted == 0})
    rows.sort(key=lambda row: row["run_id"])
    by_condition = {condition: {r["seed"]: r for r in rows if r["condition"] == condition and r.get("status") != "incomplete"}
                    for condition in CONDITIONS}
    outcomes = ("unique_phenotypes", "occupied_niches", "median_pairwise_descriptor_hamming")
    comparisons = []
    for treatment, control in (("v6-neutral", "v5-neutral"),
                               ("v6-novelty", "v6-neutral"),
                               ("v6-map-elites", "v6-neutral")):
        for metric in outcomes:
            paired = [by_condition[treatment][seed]["final"][metric] - by_condition[control][seed]["final"][metric]
                      for seed in sorted(set(by_condition[treatment]) & set(by_condition[control]))]
            comparisons.append({"treatment": treatment, "control": control, "metric": metric,
                                "independent_n": len(paired), "median_paired_difference": _median(paired),
                                "bootstrap_95_percent_ci": _bootstrap_median_ci(paired, seed_for(0, 0, metric+treatment)),
                                "p_raw": _sign_test_p(paired)})
    _holm(comparisons)
    group_summary = {}
    for condition, seeds in by_condition.items():
        group_summary[condition] = {metric: {
            "median": _median([r["final"][metric] for r in seeds.values()]),
            "runs": len(seeds)} for metric in outcomes}
        group_summary[condition].update({
            "median_accepted": _median([r["accepted"] for r in seeds.values()]),
            "median_cpu_seconds": _median([r["cpu_seconds"] for r in seeds.values()]),
            "max_rss_sampled_at_run_end_bytes": max([r["rss_bytes_at_run_end"] or 0 for r in seeds.values()], default=0),
            "all_attempts_retained": all(r["all_attempts_retained"] for r in seeds.values())})
    out = {"protocol": json.loads(PROTOCOL_PATH.read_text()),
           "identity": dict(db.execute("SELECT key,value FROM meta")),
           "group_summary": group_summary, "paired_comparisons": comparisons,
           "incomplete_runs": [row for row in rows if row.get("status") == "incomplete"],
           "completed_runs": len(completed), "planned_runs": len(planned_seeds) * len(CONDITIONS),
           "runs": rows,
           "limitations": ["Morphology-only simulated opportunity stream; no real computational births.",
                           "One frozen computational genome; no prediction effect can be inferred.",
                           "RSS is sampled at replicate end, not a per-replicate peak; VM RAM ceiling is the enforced memory bound.",
                           "Pilot results are exploratory until repeated with fresh paired seeds."]}
    db.close()
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="frozen computational genome JSON")
    parser.add_argument("--db", required=True, help="new SQLite evidence archive, <=100 MB")
    parser.add_argument("--output", required=True, help="summary JSON path")
    args = parser.parse_args()
    report = run(args.db, args.input)
    Path(args.output).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"runs": len(report["runs"]), "groups": report["group_summary"],
                      "database_bytes": Path(args.db).stat().st_size,
                      "identity": report["identity"]["identity"]}, sort_keys=True))


if __name__ == "__main__":
    main()
