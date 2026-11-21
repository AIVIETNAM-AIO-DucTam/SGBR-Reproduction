#!/usr/bin/env python3
"""Run SGBR experiment cells (E1, E2, E4, E5) with the authors' exact MOA commands.

One JVM per (experiment, dataset, learner, seed) cell. The learner and evaluator strings and the
JVM options come verbatim from the authors' JSON config at the pinned commit. Only the maximum heap
(-Xmx) is replaced, and it is recorded per cell. Cells run in parallel up to --jobs. Finished cells
are skipped on rerun when the command is unchanged.

Usage (Linux/WSL):
  python3 scripts/run_matrix.py --upstream <authors checkout> --java <java11> --jar <moa fat jar> \
      --exp E1 --datasets abalone bike --jobs 4 [--methods ...] [--seeds 1 2] [--xmx default=3g,NZEnergy=10g]
"""

import argparse
import concurrent.futures as futures
import csv
import datetime
import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True
import e1_memory_feasibility as e1  # noqa: E402
from kaggle_environment_smoke import UPSTREAM_COMMIT  # noqa: E402

CONFIGS = {
    "E1": "exp/exp_config.json",
    "E2": "exp/exp_config_overTime.json",
    "E4": "exp/exp_config_SGBT_OZA_parameter_search_LR_FP.json",
    "E5": "exp/exp_config_SGBT_OZA_parameter_search.json",
}
R2 = "adjusted coefficient of determination"
WALL = "evaluation time (wall) (seconds)"
CLASSIFIED = "classified instances"
PRINT_LOCK = threading.Lock()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log(message):
    with PRINT_LOCK:
        print(f"[{datetime.datetime.now():%H:%M:%S}] {message}", flush=True)


def load_config(upstream, exp):
    raw = e1.git_bytes(upstream, CONFIGS[exp])
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def parse_xmx(spec):
    mapping = {}
    for part in spec.split(","):
        key, value = part.split("=")
        mapping[key.strip()] = value.strip()
    if "default" not in mapping:
        raise ValueError("--xmx needs a default=<size> entry")
    return mapping


def heap_bytes(size):
    units = {"k": 2**10, "m": 2**20, "g": 2**30}
    return int(size[:-1]) * units[size[-1].lower()] if size[-1].lower() in units else int(size)


def build_command(config, learner, seed_flag, seed, java, jar, xmx, exit_on_oom=False):
    if seed_flag and seed is not None:
        learner = f"{learner} -{seed_flag} {seed}"
    jvm = config["java_options"].split()
    heap = [i for i, option in enumerate(jvm) if option.startswith("-Xmx")]
    if len(heap) != 1:
        raise ValueError("Expected exactly one -Xmx option in the authors' java_options")
    paper_xmx = jvm[heap[0]]
    jvm[heap[0]] = f"-Xmx{xmx}"
    if exit_on_oom:
        # Operational flag only: stop the JVM at the first OutOfMemoryError instead of letting MOA
        # catch it and keep thrashing the garbage collector for hours.
        jvm.insert(heap[0] + 1, "-XX:+ExitOnOutOfMemoryError")
    task = f'{config["evaluator"]} -s (ArffFileStream -f stream.arff) -l ({learner}) -d evaluation.csv'
    return [java, "-classpath", str(jar), *jvm, task], paper_xmx


def final_row(csv_path):
    if not csv_path.is_file():
        return None
    last = None
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            last = row
    return last


class DataCache:
    """Materialise each pinned ARFF once and remember its digest and row count."""

    def __init__(self, upstream, root):
        self.upstream, self.root, self.lock, self.items = upstream, root, threading.Lock(), {}

    def get(self, dataset):
        with self.lock:
            if dataset in self.items:
                return self.items[dataset]
            folder = self.root / dataset
            folder.mkdir(parents=True, exist_ok=True)
            meta = folder / "evidence.json"
            path = folder / "stream.arff"
            if meta.is_file() and path.is_file():
                evidence = json.loads(meta.read_text())
            else:
                e1.stream_bytes(self.upstream, dataset, folder)
                evidence = e1.dataset_evidence(path)
                meta.write_text(json.dumps(evidence))
            self.items[dataset] = (path, evidence)
            return self.items[dataset]


def run_cell(cell, args, config, config_hash, data, jar_sha):
    exp, dataset, method, seed_flag, learner, seed = cell
    seed_label = "none" if seed is None else str(seed)
    folder = args.results / "raw" / exp / dataset / method / f"seed={seed_label}"
    record_path = folder / "record.json"
    xmx = args.xmx.get(dataset, args.xmx["default"])
    command, paper_xmx = build_command(config, learner, seed_flag, seed, args.java, args.jar, xmx,
                                       args.exit_on_oom)
    stream, evidence = data.get(dataset)
    # The jar digest is recorded but not hashed: Maven builds of the same pinned source are not
    # byte-reproducible, and every Kaggle session rebuilds the jar.
    # The operational OOM flag is left out too, so resumed runs keep matching earlier records.
    identity = [part for part in command if part != "-XX:+ExitOnOutOfMemoryError"]
    command_hash = hashlib.sha256(json.dumps([identity, evidence["sha256"], config_hash]).encode()).hexdigest()
    if record_path.is_file():
        old = json.loads(record_path.read_text())
        if old.get("status") == "completed" and old.get("command_hash") == command_hash:
            return old, True
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("evaluation.csv", "java.log", "stream.arff"):
        (folder / name).unlink(missing_ok=True)
    os.symlink(stream, folder / "stream.arff")
    env = {k: v for k, v in os.environ.items() if k not in e1.JAVA_OPTION_VARIABLES}
    record = {
        "exp": exp, "dataset": dataset, "method_key": method, "seed": seed, "command": command,
        "command_line": shlex.join(command), "command_hash": command_hash, "config": CONFIGS[exp],
        "config_sha256": config_hash, "upstream_commit": UPSTREAM_COMMIT, "jar_sha256": jar_sha,
        "xmx": f"-Xmx{xmx}", "paper_xmx": paper_xmx, "dataset_sha256": evidence["sha256"],
        "expected_instances": evidence["expected_instances"], "concurrency": args.jobs,
        "host": os.uname().nodename, "cpu_model": args.cpu_model, "started_at": now(),
    }
    log(f"start  {exp} {dataset} {method} seed={seed_label} ({record['xmx']})")
    started = time.monotonic()
    with (folder / "java.log").open("wb") as out:
        process = subprocess.Popen(command, cwd=folder, stdout=out, stderr=subprocess.STDOUT, env=env)
        try:
            _, status, usage = os.wait4(process.pid, 0)
            process.returncode = os.waitstatus_to_exitcode(status)
            peak = usage.ru_maxrss * 1024
        except ChildProcessError:
            process.wait()
            peak = None
    elapsed = time.monotonic() - started
    (folder / "stream.arff").unlink(missing_ok=True)
    row = final_row(folder / "evaluation.csv")
    processed = None
    if row is not None:
        try:
            processed = int(float(row[CLASSIFIED]))
        except (KeyError, ValueError):
            processed = None
    oom = e1.java_oom(folder)
    if (not oom and process.returncode == 0 and processed is None
            and peak is not None and peak >= 0.9 * heap_bytes(xmx)):
        # MOA can catch OutOfMemoryError, print "null" and exit 0 without writing its CSV
        # (observed for NZEnergy Sgb(Srp) at -Xmx6g). A heap-sized RSS with no output is an OOM.
        oom = True
    if process.returncode == 0 and processed == evidence["expected_instances"] and not oom:
        status = "completed"
    elif oom:
        status = "oom"
    else:
        status = "failed"
    with (folder / "java.log").open("rb") as handle:
        handle.seek(max(0, (folder / "java.log").stat().st_size - 65536))
        progress = e1.PROGRESS_PERCENT.findall(handle.read())
    record.update({
        "last_progress_percent": float(progress[-1]) if progress else None,
        "finished_at": now(), "exit_code": process.returncode, "external_wall_seconds": elapsed,
        "peak_rss_bytes": peak, "processed_instances": processed, "status": status,
        "r2": float(row[R2]) if row and status == "completed" else None,
        "moa_wall_seconds": float(row[WALL]) if row and status == "completed" else None,
    })
    record_path.write_text(json.dumps(record, indent=1))
    log(f"{status:9s}{exp} {dataset} {method} seed={seed_label} R2={record['r2']} "
        f"wall={record['moa_wall_seconds']} rss={peak and round(peak / 2**30, 2)}GiB")
    return record, False


CORE10 = ["fried", "House8L", "abalone", "bike", "elevators", "MetroTraffic", "ailerons",
          "FriedmanLea", "FriedmanGra", "FriedmanGsg"]


def estimated_seconds(method, dataset):
    """Paper Tab.4 mean wall time for one run (authors' E1 machine); 60 s if not tabulated."""
    from summarize_e1 import DATASETS, METHODS, TAB4
    names = {label: paper for paper, label, _ in METHODS}
    if method in names and dataset in DATASETS:
        return TAB4[names[method]][DATASETS.index(dataset)]
    return 60.0


def shard_cells(cells, num_shards, slots):
    """Longest-processing-time-first assignment of cells to num_shards x slots workers."""
    loads = [0.0] * (num_shards * slots)
    shards = [[] for _ in range(num_shards)]
    for cell in sorted(cells, key=lambda c: (-estimated_seconds(c[2], c[1]), c[1], c[2], c[5] or 0)):
        worker = min(range(len(loads)), key=loads.__getitem__)
        loads[worker] += estimated_seconds(cell[2], cell[1])
        shards[worker // slots].append(cell)
    makespans = [max(loads[s * slots:(s + 1) * slots]) for s in range(num_shards)]
    return shards, makespans


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--java", required=True)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--data-cache", type=Path, default=Path.home() / "sgbr" / "data")
    parser.add_argument("--exp", choices=sorted(CONFIGS), default="E1")
    parser.add_argument("--datasets", nargs="+")
    parser.add_argument("--methods", nargs="+")
    parser.add_argument("--exclude-methods", nargs="+", default=[])
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--xmx", type=parse_xmx, default=parse_xmx("default=4g"))
    parser.add_argument("--exit-on-oom", action="store_true",
                        help="Add -XX:+ExitOnOutOfMemoryError so an OOM ends the run immediately")
    parser.add_argument("--plan", choices=["e1-approved"],
                        help="e1-approved: all 13 repo datasets, Axgb only on Core-10 (H-01(d), H-01(f))")
    parser.add_argument("--shard", type=int, help="1-based shard index to run")
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--list", action="store_true", help="Print the shard plan and exit without running")
    parser.add_argument("--skip-cells", nargs="+", default=[], metavar="DATASET:METHOD",
                        help="Drop these (dataset, method) cells after sharding; other shards are unchanged")
    args = parser.parse_args(argv)
    if args.shard is not None and not 1 <= args.shard <= args.num_shards:
        parser.error("--shard must be between 1 and --num-shards")

    config, config_hash = load_config(args.upstream, args.exp)
    available = [d for d in config["datasets"] if not d.startswith("SUP")]  # SUP* not shipped (Q-30)
    datasets = args.datasets or (available if args.plan else config["datasets"])
    unknown = set(datasets) - set(config["datasets"])
    if unknown:
        parser.error(f"Datasets not in {CONFIGS[args.exp]}: {sorted(unknown)}")
    learners = [entry for entry in config["learners"] if entry[0] not in args.exclude_methods]
    if args.methods:
        missing = set(args.methods) - {entry[0] for entry in learners}
        if missing:
            parser.error(f"Methods not in config: {sorted(missing)}")
        learners = [entry for entry in learners if entry[0] in args.methods]
    seeds = args.seeds or config["random_seeds"]

    cells = []
    for dataset in datasets:
        for name, seed_flag, learner in learners:
            if args.plan == "e1-approved" and name == "AXGBr" and dataset not in CORE10:
                continue  # H-01(f): Axgb only on Core-10
            # One-run rule (H-01(f)): learners without a seed flag run once per dataset.
            for seed in (seeds if seed_flag else [None]):
                cells.append((args.exp, dataset, name, seed_flag, learner, seed))
    if args.num_shards > 1 or args.list:
        shards, makespans = shard_cells(cells, args.num_shards, args.jobs)
        total = sum(estimated_seconds(c[2], c[1]) for c in cells) / 3600
        log(f"{len(cells)} cells, ≈{total:.1f} CPU-h at paper speed, {args.num_shards} shards x {args.jobs} slots")
        for index, (shard, span) in enumerate(zip(shards, makespans), 1):
            names = sorted({c[1] for c in shard})
            log(f"  shard {index}: {len(shard):3d} cells, est. makespan {span / 3600:5.2f} h, datasets {names}")
        if args.list:
            return 0
        cells = shards[args.shard - 1] if args.shard else cells
    skip = {tuple(item.split(":", 1)) for item in args.skip_cells}
    dropped = [c for c in cells if (c[1], c[2]) in skip]
    if dropped:
        log(f"Skipping {len(dropped)} cells run elsewhere: {sorted({(c[1], c[2]) for c in dropped})}")
        cells = [c for c in cells if (c[1], c[2]) not in skip]
    cells.sort(key=lambda c: -estimated_seconds(c[2], c[1]))  # longest first
    with open("/proc/cpuinfo") as info:
        args.cpu_model = next((line.split(":", 1)[1].strip() for line in info if line.startswith("model name")), None)
    jar_sha = hashlib.sha256(args.jar.read_bytes()).hexdigest()
    data = DataCache(args.upstream, args.data_cache)
    log(f"{len(cells)} cells, {args.jobs} parallel JVMs, heap map {args.xmx}")
    counts = {}
    with futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        jobs = [pool.submit(run_cell, cell, args, config, config_hash, data, jar_sha) for cell in cells]
        for job in futures.as_completed(jobs):
            record, skipped = job.result()
            key = "skipped" if skipped else record["status"]
            counts[key] = counts.get(key, 0) + 1
    log(f"done: {counts}")
    return 0 if set(counts) <= {"completed", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
