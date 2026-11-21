#!/usr/bin/env python3
"""Generate, run, or report the approved C-21 fidelity gate."""

import argparse
import csv
import datetime
import fcntl
import hashlib
import io
import itertools
import json
import math
import os
import re
import shlex
import shutil
import signal
import statistics
import struct
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import e1_memory_feasibility as e1
from kaggle_environment_smoke import UPSTREAM_COMMIT, cgroup_limits, cpu_info

COUNTS = {"abalone": 4977, "bike": 17379, "elevators": 16599}
METHOD_FILES = {
    "Oza(SGBT(FIRTDD))": "Oza(SGBT)",
    "SGBT(Oza(FIRTDD))": "SGBT(Oza)",
    "SGBT(ARFReg(FIRTDD))": "SGBT(ARF)",
    "Oza(FIRTDD)": "OzaReg",
    "ARFReg(FIRTDD)": "ARFReg",
    "SOKNL(FIRTDD)": "SOKNL",
}
TABLE3 = {
    "FIRTDD": dict(zip(COUNTS, ("0.16", "0.75", "0.24"))),
    "HT": dict(zip(COUNTS, ("0.14", "0.56", "0.25"))),
}
B0_REF = "exp/post_hoc_new/NZEnergy_1/SGBT(ARF).csv"
B0_MANIFEST = Path(__file__).resolve().parents[1] / "results/manifest/e1_memory_feasibility.json"
CLASSIFIED = "classified instances"
R2 = "adjusted coefficient of determination"
WALL = "evaluation time (wall) (seconds)"
PREDICTIVE_COLUMNS = (
    CLASSIFIED, "mean absolute error", "root mean squared error", "relative mean absolute error",
    "relative root mean squared error", "coefficient of determination", R2,
)
STATUSES = {
    "completed", "oom", "timeout", "session_limit", "failed", "not_run_data", "not_run_compute",
}
REQUIRED_RECORD = {
    "command", "command_line", "command_hash", "jar_sha256", "build_jdk", "java_version", "gc",
    "xmx", "cpu_model", "concurrency", "session_id", "dataset_sha256", "expected_instances",
    "processed_instances", "r2", "moa_wall_seconds", "external_wall_seconds", "peak_rss_bytes",
    "exit_code", "status", "attempt", "termination_signal", "upstream_commit",
}
EXACT = Decimal("0.000001")
TOLERANCE = Decimal("0.005")
CONFIG_PATH = "exp/exp_config.json"


@dataclass(frozen=True)
class Cell:
    exp: str
    dataset: str
    method_key: str
    seed: int | None
    ref_source: str | None

    @property
    def path(self):
        seed = "none" if self.seed is None else self.seed
        return Path(self.exp, self.dataset, self.method_key, f"seed={seed}.json")

    @property
    def counterpart(self):
        if self.exp == "B1-b":
            return Cell("B1-a", self.dataset, self.method_key, self.seed, None).path
        if self.exp.startswith("B1-c-"):
            other = "B1-c-r2" if self.exp == "B1-c-r1" else "B1-c-r1"
            return Cell(other, self.dataset, self.method_key, None, None).path
        return None


def author_path(dataset, seed, method):
    return f"exp/post_hoc_new/{dataset}_{seed}/{METHOD_FILES[method]}.csv"


def matrix(config):
    flags = {name: flag for name, flag, _ in config["learners"]}
    if (config["random_seeds"] != [1, 2, 3, 4, 5]
            or not COUNTS.keys() <= set(config["datasets"])
            or any(flags.get(name) != "Z" for name in METHOD_FILES)
            or any(flags.get(name) != "" for name in TABLE3)):
        raise ValueError("Pinned E1 configuration does not match the approved §12 matrix.")
    cells = []
    for dataset, method, seed in itertools.product(COUNTS, METHOD_FILES, config["random_seeds"]):
        cells.append(Cell("B1-a", dataset, method, seed, author_path(dataset, seed, method)))
    for dataset, method in itertools.product(COUNTS, METHOD_FILES):
        peer = Cell("B1-a", dataset, method, 1, None)
        cells.append(Cell("B1-b", dataset, method, 1, f"results/raw/{peer.path.as_posix()}"))
    for repeat, dataset, method in itertools.product((1, 2), COUNTS, TABLE3):
        cell = Cell(f"B1-c-r{repeat}", dataset, method, None, None)
        cells.append(Cell(cell.exp, dataset, method, None, f"results/raw/{cell.counterpart.as_posix()}"))
    if len(cells) != 120 or len({cell.path for cell in cells}) != 120:
        raise ValueError("B1 requires exactly 120 unique executable cell IDs.")
    return cells


def final_metrics(stream):
    reader = csv.DictReader(stream)
    fields = {header.strip(): header for header in reader.fieldnames or ()}
    last = None
    for line in reader:
        last = line
    if last is None:
        raise ValueError("MOA CSV has no evaluator rows.")
    try:
        metrics = {name: last[fields[name]].strip() for name in (*PREDICTIVE_COLUMNS, WALL)}
        values = [Decimal(value) for value in metrics.values()]
    except (KeyError, AttributeError, InvalidOperation) as error:
        raise ValueError("MOA CSV is missing valid evaluator fields.") from error
    if any(not value.is_finite() for value in values):
        raise ValueError("MOA CSV contains a nonfinite evaluator value.")
    rows = Decimal(metrics[CLASSIFIED])
    if rows != rows.to_integral_value() or rows < 0 or Decimal(metrics[WALL]) < 0:
        raise ValueError("MOA CSV has an invalid classified count or timing.")
    return metrics


def bits_match(left, right):
    return all(struct.pack(">d", float(left[name])) == struct.pack(">d", float(right[name]))
               for name in PREDICTIVE_COLUMNS)


def adjusted_r2(observations, num_attributes):
    """Pinned MOA running-mean adjusted R² for unit-weight target/prediction pairs."""
    total = residual = target_sum = 0.0
    count = 0
    for target, prediction in observations:
        mean = target_sum / count if count else 0.0
        error = target - prediction
        baseline_error = target - mean
        residual += error * error
        total += baseline_error * baseline_error
        target_sum += target
        count += 1
    if total == 0 or count == num_attributes + 1:
        return math.nan
    r2 = 1 - residual / total
    return 1 - (1 - r2) * (count - 1) / (count - num_attributes - 1)


def parity(actual, reference):
    if actual is None or reference is None:
        return "Incomplete"
    if Decimal(actual[CLASSIFIED]) != Decimal(reference[CLASSIFIED]):
        return "Fail"
    delta = abs(Decimal(actual[R2]) - Decimal(reference[R2]))
    if delta <= EXACT:
        return "Exact"
    return "Tolerance pass" if delta <= TOLERANCE else "Fail"


def author_references(upstream, cells):
    refs = {}
    for cell in cells:
        if cell.exp != "B1-a":
            continue
        ref = final_metrics(io.StringIO(e1.git_bytes(upstream, cell.ref_source).decode("utf-8-sig")))
        if Decimal(ref[CLASSIFIED]) != COUNTS[cell.dataset]:
            raise ValueError(f"Unexpected authors' row count in {cell.ref_source}.")
        refs[cell.path] = ref
    refs[B0_REF] = final_metrics(io.StringIO(e1.git_bytes(upstream, B0_REF).decode("utf-8-sig")))
    if (Decimal(refs[B0_REF][CLASSIFIED]) != 3100666
            or Decimal(refs[B0_REF][R2]) != Decimal("0.9741708731300197")):
        raise ValueError("Unexpected pinned reference for B1-d.")
    return refs


def read_record(path, cell):
    if not path.is_file():
        return None
    record = json.loads(path.read_text())
    if not REQUIRED_RECORD <= record.keys() or record["status"] not in STATUSES:
        raise ValueError(f"Invalid B1 status or record schema: {path}")
    if (record.get("cell") != asdict(cell) or record["concurrency"] != 1
            or record["expected_instances"] != COUNTS[cell.dataset] or record["xmx"] != "16g"
            or record["upstream_commit"] != UPSTREAM_COMMIT):
        raise ValueError(f"Unexpected B1 identity, row count, heap, or concurrency: {path}")
    for field in ("command_hash", "dataset_sha256", "jar_sha256"):
        if not isinstance(record[field], str) or not re.fullmatch(r"[0-9a-f]{64}", record[field]):
            raise ValueError(f"Invalid {field} in B1 record: {path}")
    command = record["command"]
    if not isinstance(command, list) or len(command) != 8 or not all(isinstance(arg, str) for arg in command):
        raise ValueError(f"Invalid command in B1 record: {path}")
    if record["status"] == "completed" and (record["exit_code"] != 0 or not record.get("metrics")):
        raise ValueError(f"Completed cell lacks successful evaluator evidence: {path}")
    return record


def result_metrics(record):
    return record["metrics"] if record and record["status"] == "completed" else None


def report_row(cell, record, reference, ref_source, verdict, wall_reference=None, wall_ref_source=None):
    actual = result_metrics(record)
    wall_ref = wall_reference[WALL] if wall_reference else None
    return {
        "exp": cell.exp, "dataset": cell.dataset, "method_key": cell.method_key, "seed": cell.seed,
        "r2": actual[R2] if actual else None, "r2_ref": reference[R2] if reference else None,
        "delta": str(Decimal(actual[R2]) - Decimal(reference[R2])) if actual and reference else None,
        "ref_source": ref_source,
        "wall": actual[WALL] if actual else None, "wall_ref": wall_ref,
        "sigma": float(Decimal(actual[WALL]) / Decimal(wall_ref))
        if actual and wall_ref and Decimal(wall_ref) > 0 else None,
        "verdict": verdict, "status": record["status"] if record else "pending",
        "classified_instances": int(Decimal(actual[CLASSIFIED]))
        if actual else record.get("processed_instances") if record else None,
        "classified_instances_ref": int(Decimal(reference[CLASSIFIED])) if reference else None,
        "peak_rss_bytes": record["peak_rss_bytes"] if record else None,
        "cpu_model": record["cpu_model"] if record else None,
        "concurrency": record["concurrency"] if record else None,
        "wall_ref_source": wall_ref_source, "observed_source": None,
        "status_reason": record.get("reason") if record else None,
        "table3_r2_ref": None, "table3_source": None, "table3_rounded_match": None,
    }


def comparison_rows(cells, records, refs):
    rows = []
    for cell in cells:
        record = records.get(cell.path)
        actual = result_metrics(record)
        peer = records.get(cell.counterpart)
        reference = refs[cell.path] if cell.exp == "B1-a" else result_metrics(peer)
        if record and record["status"] == "failed" and record.get("reason") == "row_count_mismatch":
            verdict = "Fail"
        elif cell.exp == "B1-a":
            verdict = parity(actual, reference)
        elif actual and reference:
            verdict = "Exact" if bits_match(actual, reference) else "Fail"
        else:
            verdict = "Incomplete"
        if cell.exp in {"B1-a", "B1-b"}:
            author = Cell("B1-a", cell.dataset, cell.method_key, cell.seed, None)
            wall_ref = refs[author.path]
            wall_path = author_path(cell.dataset, cell.seed, cell.method_key)
        else:
            wall_ref = wall_path = None
        row = report_row(cell, record, reference, cell.ref_source, verdict, wall_ref, wall_path)
        if actual:
            row["observed_source"] = f"results/raw/{cell.path.with_suffix('.csv').as_posix()}"
        if cell.exp.startswith("B1-c-"):
            rounded = TABLE3[cell.method_key][cell.dataset]
            row.update(
                table3_r2_ref=rounded, table3_source="Paper Table 3, journal p. 15",
                table3_rounded_match=(
                    Decimal(actual[R2]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal(rounded)
                ) if actual else None,
            )
        rows.append(row)
    return rows


def b0_row(path, ref, manifest_path=B0_MANIFEST):
    cell = Cell("B1-d", "NZEnergy", "SGBT(ARFReg(FIRTDD))", 1, B0_REF)
    record = None
    if path:
        evidence = json.loads(manifest_path.read_text())
        if (evidence.get("status") != "completed" or evidence.get("exit_code") != 0
                or evidence.get("upstream_commit") != UPSTREAM_COMMIT
                or evidence.get("learner") != cell.method_key or evidence.get("seed") != cell.seed
                or evidence.get("dataset", {}).get("name") != cell.dataset
                or evidence.get("processed_instances") != 3100666):
            raise ValueError("B0 manifest does not identify the approved, completed NZEnergy run.")
        with path.open(newline="", encoding="utf-8-sig") as file:
            metrics = final_metrics(file)
        environment_path = manifest_path.with_name("environment.json")
        environment = json.loads(environment_path.read_text()) if environment_path.is_file() else {}
        models = environment.get("cpu", {}).get("models", [])
        record = {
            "status": "completed", "metrics": metrics, "peak_rss_bytes": evidence.get("peak_java_rss_bytes"),
            "cpu_model": " | ".join(models) or None, "concurrency": 1,
        }
    row = report_row(cell, record, ref, B0_REF, parity(result_metrics(record), ref), ref, B0_REF)
    row["observed_source"] = str(path) if record else None
    return row


def gate_verdict(rows):
    verdicts = {row["verdict"] for row in rows}
    if "Fail" in verdicts:
        return "Fail"
    if len(rows) != 121 or "Incomplete" in verdicts:
        return "Incomplete"
    return "Tolerance pass" if "Tolerance pass" in verdicts else "Exact"


def seed_differences(rows):
    groups = []
    for dataset, method in itertools.product(COUNTS, METHOD_FILES):
        present = [
            row for row in rows if row["exp"] == "B1-a" and row["dataset"] == dataset
            and row["method_key"] == method and row["r2"] is not None
        ]
        contrasts = []
        for left, right in itertools.combinations(present, 2):
            observed = Decimal(right["r2"]) - Decimal(left["r2"])
            expected = Decimal(right["r2_ref"]) - Decimal(left["r2_ref"])
            contrasts.append({
                "seeds": [left["seed"], right["seed"]], "observed_difference": str(observed),
                "reference_difference": str(expected), "difference_error": str(observed - expected),
                "matches_at_1e_6": abs(observed - expected) <= EXACT,
            })
        groups.append({"dataset": dataset, "method_key": method, "contrasts": contrasts,
                       "all_match_at_1e_6": all(row["matches_at_1e_6"] for row in contrasts)
                       if len(contrasts) == 10 else None})
    return groups


def slowdown_summary(rows):
    groups = {}
    for row in rows:
        if row["exp"] == "B1-a" and row["sigma"] is not None and row["cpu_model"]:
            groups.setdefault((row["cpu_model"], row["concurrency"]), []).append(row["sigma"])
    summary = []
    for (model, concurrency), values in sorted(groups.items()):
        quartiles = statistics.quantiles(values, n=4, method="inclusive") if len(values) > 1 else None
        summary.append({
            "cpu_model": model, "concurrency": concurrency, "cells": len(values),
            "median_sigma": statistics.median(values), "q1_sigma": quartiles[0] if quartiles else None,
            "q3_sigma": quartiles[2] if quartiles else None,
            "iqr_sigma": quartiles[2] - quartiles[0] if quartiles else None,
        })
    return summary


def batch_identity(record):
    return tuple(record[key] for key in ("jar_sha256", "build_jdk", "java_version", "gc", "xmx"))


def write_report(results, rows, records):
    summary = results / "summary"
    summary.mkdir(parents=True, exist_ok=True)
    with (summary / "B1_parity.csv.tmp").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (summary / "B1_parity.csv.tmp").replace(summary / "B1_parity.csv")
    outcome = gate_verdict(rows)
    identities = {batch_identity(record) for record in records.values() if result_metrics(record)}
    blockers = []
    if len(identities) > 1:
        blockers.append("B1 records mix JVM or jar identities. Regroup before interpreting the gate.")
        if outcome != "Fail":
            outcome = "Incomplete"
    if rows[-1]["status"] == "pending":
        blockers.append("B1-d needs the observed B0 evaluator CSV from the completed Kaggle run.")
    if outcome == "Tolerance pass":
        blockers.append("Open a question on the source of the observed environment difference before interpreting it.")
    data = {
        "verdict": outcome, "completed_b1_runs": sum(row["status"] == "completed" for row in rows[:-1]),
        "scheduled_b1_runs": 120, "blockers": blockers, "serial_slowdown_by_cpu": slowdown_summary(rows),
        "seed_differences": seed_differences(rows),
    }
    e1.save_manifest(summary / "B1_gate.json", data)
    print(f"B1 gate: {outcome} ({data['completed_b1_runs']}/120 runs complete)", flush=True)
    return outcome


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def digest_file(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def load_inputs(upstream):
    config_bytes = e1.git_bytes(upstream, CONFIG_PATH)
    config = json.loads(config_bytes)
    cells = matrix(config)
    data = {}
    with tempfile.TemporaryDirectory() as temporary:
        for dataset, count in COUNTS.items():
            contents = e1.git_bytes(upstream, f"exp/RDatasets/{dataset}.arff")
            file = Path(temporary) / f"{dataset}.arff"
            file.write_bytes(contents)
            evidence = e1.dataset_evidence(file)
            if evidence["expected_instances"] != count:
                raise ValueError(f"Pinned {dataset} ARFF count does not match §3.")
            data[dataset] = (contents, evidence)
    return config, config_bytes, cells, data


def cell_manifest(config_bytes, cells, data):
    return {
        "batch": "B1", "schema_version": 1, "upstream_commit": UPSTREAM_COMMIT,
        "config_path": CONFIG_PATH, "config_sha256": sha256(config_bytes),
        "scheduled_runs": len(cells), "concurrency": 1, "jvm": ["-Xmx16g", "-Xms50m", "-Xss1g"],
        "datasets": {name: evidence for name, (_, evidence) in data.items()},
        "cells": [{**asdict(cell), "record_path": f"results/raw/{cell.path.as_posix()}"} for cell in cells],
        "read_only_comparison": {"exp": "B1-d", "dataset": "NZEnergy", "seed": 1, "ref_source": B0_REF},
    }


def java_runtime(args):
    java = shutil.which(args.java)
    if java is None:
        raise ValueError("Select the JDK 11 executable with --java.")
    jar = args.moa_jar.resolve(strict=True)
    provenance = json.loads(args.jar_provenance.read_text())
    if "moa" in provenance:
        provenance = provenance["moa"]
    build_jdk = provenance.get("build_java_version", "")
    if (provenance.get("upstream_commit") != UPSTREAM_COMMIT
            or not re.search(r'version "11\.', build_jdk)):
        raise ValueError("MOA provenance must identify the pinned source and JDK 11 build.")
    jar_digest = digest_file(jar)
    if jar_digest != provenance.get("sha256"):
        raise ValueError("MOA jar SHA-256 differs from the build provenance.")
    env = {key: value for key, value in os.environ.items() if key not in e1.JAVA_OPTION_VARIABLES}
    java_version = subprocess.check_output(
        [java, "-XX:+PrintCommandLineFlags", "-Xmx16g", "-Xms50m", "-Xss1g", "-version"],
        text=True, stderr=subprocess.STDOUT, timeout=30, env=env,
    )
    gc = re.search(r"-XX:\+Use(\w+GC)\b", java_version)
    if not re.search(r'version "11\.', java_version) or gc is None:
        raise ValueError("B1 requires a verified JDK 11 runtime and its active default GC.")
    return java, jar, env, {
        "jar_sha256": jar_digest, "build_jdk": build_jdk,
        "java_version": "\n".join(line for line in java_version.splitlines() if not line.startswith("-XX:")),
        "gc": gc[1], "xmx": "16g", "cpu_model": " | ".join(cpu_info()["models"]) or None,
        "concurrency": 1, "session_id": args.session_id,
    }


def command_identity(command, runtime, dataset_sha256, config_sha256):
    facts = [command, *batch_identity(runtime), dataset_sha256, config_sha256]
    return sha256(json.dumps(facts, separators=(",", ":")).encode())


def event_log(path, session_id, event, **fields):
    with path.open("a", encoding="utf-8") as file:
        row = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "session_id": session_id, "event": event, **fields,
        }
        file.write(json.dumps(row) + "\n")
    cell = fields.get("cell")
    print(f"{event}: {cell or fields.get('reason', session_id)}", flush=True)


def check_completed_csv(path, record):
    source = path.with_suffix(".csv")
    if not source.is_file() or digest_file(source) != record.get("csv_sha256"):
        raise ValueError(f"Completed B1 cell lacks its verified evaluator CSV: {source}")
    with source.open(newline="", encoding="utf-8-sig") as file:
        metrics = final_metrics(file)
    if (metrics != record["metrics"] or int(Decimal(metrics[CLASSIFIED])) != record["expected_instances"]
            or record["processed_instances"] != record["expected_instances"]
            or record["r2"] != metrics[R2] or record["moa_wall_seconds"] != metrics[WALL]):
        raise ValueError(f"Evaluator CSV and completed record disagree: {source}")


def load_records(raw, cells, data, config, config_hash):
    records = {}
    for cell in cells:
        path = raw / cell.path
        record = read_record(path, cell)
        if record:
            if result_metrics(record) is not None:
                check_completed_csv(path, record)
                evidence = data[cell.dataset][1]
                command = record["command"]
                approved = e1.e1_command(
                    config, cell.dataset, cell.method_key, cell.seed or 1, command[0], command[2],
                )
                digest = command_identity(approved, record, evidence["sha256"], config_hash)
                if (command != approved or record["command_line"] != shlex.join(approved)
                        or record["dataset_sha256"] != evidence["sha256"] or digest != record["command_hash"]):
                    raise ValueError(f"Completed B1 evidence differs from the pinned command or dataset: {path}")
            records[cell.path] = record
    return records


def run_cell(path, cell, command, command_hash, contents, evidence, runtime, env, groups,
             timeout, deadline_limited, lock_fd):
    path.parent.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=path.parent))
    record = {
        **runtime, "cell": asdict(cell), "upstream_commit": UPSTREAM_COMMIT,
        "command": command, "command_line": shlex.join(command),
        "command_hash": command_hash, "dataset_sha256": evidence["sha256"],
        "expected_instances": evidence["expected_instances"], "processed_instances": None,
        "r2": None, "moa_wall_seconds": None, "external_wall_seconds": None,
        "peak_rss_bytes": None, "exit_code": None, "termination_signal": None,
        "status": "failed", "reason": "attempt_not_finalized", "attempt": attempt.name,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    e1.save_manifest(path, record)
    path.with_suffix(".csv").unlink(missing_ok=True)
    stream = attempt / "stream.arff"
    monitor = {"command": command, "dataset": evidence}
    try:
        stream.write_bytes(contents)
        e1.measure_java(
            attempt / "progress.json", monitor, attempt, groups, timeout, env,
            progress_label=cell.exp, pass_fds=(lock_fd,),
        )
        status = monitor["status"]
        record.update(
            exit_code=monitor["exit_code"], termination_signal=monitor["termination_signal"],
            peak_rss_bytes=monitor["peak_java_rss_bytes"], external_wall_seconds=monitor["wall_clock_seconds"],
            oom=monitor["oom"], status={
                "completed": "completed", "oom_observed": "oom",
                "timed_out": "session_limit" if deadline_limited else "timeout",
            }.get(status, "failed"), reason=status,
        )
        source = attempt / "evaluation.csv"
        if source.is_file():
            shutil.copyfile(source, path.with_suffix(".csv"))
            with source.open(newline="", encoding="utf-8-sig") as file:
                metrics = final_metrics(file)
            count = int(Decimal(metrics[CLASSIFIED]))
            record["processed_instances"] = count
            if status in {"completed", "incomplete_stream"}:
                if count != evidence["expected_instances"] or monitor["processed_instances"] != count:
                    record.update(status="failed", reason="row_count_mismatch")
                elif status == "completed":
                    record.update(
                        reason=None, metrics=metrics, r2=metrics[R2], moa_wall_seconds=metrics[WALL],
                        csv_sha256=digest_file(source),
                    )
        elif status == "completed":
            record.update(status="failed", reason="missing_evaluator_csv")
        elif status == "incomplete_stream":
            record.update(status="failed", reason="row_count_unverified")
    except KeyboardInterrupt:
        record.update(status="failed", reason="interrupted")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if record["status"] == "completed":
            record["status"] = "failed"
        record["error"] = str(error)
        if record["status"] == "failed":
            record["reason"] = "invalid_or_unavailable_evidence"
    finally:
        stream.unlink(missing_ok=True)
        record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        e1.save_manifest(attempt / "record.json", record)
        e1.save_manifest(path, record)
    return record


def fail_detected(rows):
    return any(row["verdict"] == "Fail" for row in rows)


def execute(args, config, config_bytes, cells, data, refs, b0, lock_fd):
    java, jar, env, runtime = java_runtime(args)
    raw = args.results / "raw"
    records = load_records(raw, cells, data, config, sha256(config_bytes))
    if any(batch_identity(record) != batch_identity(runtime)
           for record in records.values() if result_metrics(record) is not None):
        raise ValueError("B1 results contain a different JVM or jar. Use a separate results directory.")
    logs = args.results / "logs" / "B1"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{uuid.uuid4().hex}.jsonl"
    config_hash = sha256(config_bytes)
    groups = cgroup_limits()
    started = time.monotonic()
    limit = args.session_budget_seconds

    def rows():
        return [*comparison_rows(cells, records, refs), b0]

    event_log(log, args.session_id, "session_started", concurrency=1, cpu_model=runtime["cpu_model"])
    try:
        for cell in cells:
            if fail_detected(rows()):
                event_log(log, args.session_id, "gate_failed", reason="§12 failure; no further JVMs launched")
                break
            contents, evidence = data[cell.dataset]
            command = e1.e1_command(
                config, cell.dataset, cell.method_key, cell.seed if cell.seed is not None else 1, java, jar,
            )
            command_hash = command_identity(command, runtime, evidence["sha256"], config_hash)
            existing = records.get(cell.path)
            if result_metrics(existing) is not None and existing["command_hash"] == command_hash:
                event_log(log, args.session_id, "cell_skipped", cell=asdict(cell), command_hash=command_hash)
                continue
            remaining = None if limit is None else limit - (time.monotonic() - started)
            if remaining is not None and remaining <= 0:
                event_log(log, args.session_id, "session_limit", reason="Session budget exhausted before next cell")
                break
            timeout = args.cell_timeout_seconds
            deadline_limited = remaining is not None and (timeout is None or remaining <= timeout)
            if deadline_limited:
                timeout = remaining
            event_log(log, args.session_id, "cell_started", cell=asdict(cell), command_hash=command_hash)
            record = run_cell(
                raw / cell.path, cell, command, command_hash, contents, evidence, runtime, env,
                groups, timeout, deadline_limited, lock_fd,
            )
            records[cell.path] = record
            event_log(log, args.session_id, "cell_finished", cell=asdict(cell),
                      status=record["status"], reason=record["reason"])
            if record["status"] != "completed":
                break
    finally:
        outcome = write_report(args.results, rows(), records)
        event_log(log, args.session_id, "session_finished", verdict=outcome)
    return 0 if outcome in {"Exact", "Tolerance pass"} else 1


def interrupt(signum, frame):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-checkout", type=Path, required=True)
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--b0-csv", type=Path, help="Raw evaluator CSV from the completed B0 NZEnergy run")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("manifest", help="Generate the 120-cell plan with no Java execution")
    commands.add_parser("report", help="Compare saved evidence with pinned authors' CSVs without Java")
    run = commands.add_parser("run", help="Execute serially after the human explicitly approves launch")
    run.add_argument("--approved", action="store_true")
    run.add_argument("--java", required=True)
    run.add_argument("--moa-jar", type=Path, required=True)
    run.add_argument("--jar-provenance", type=Path, required=True)
    run.add_argument("--session-id", required=True)
    run.add_argument("--cell-timeout-seconds", type=int)
    run.add_argument("--session-budget-seconds", type=int)
    args = parser.parse_args(argv)
    if args.action == "run":
        if not args.approved:
            parser.error("B1 launch needs explicit human approval. Do not pass --approved until authorized.")
        for option in ("cell_timeout_seconds", "session_budget_seconds"):
            if getattr(args, option) is not None and getattr(args, option) <= 0:
                parser.error(f"--{option.replace('_', '-')} must be positive.")
    try:
        config, config_bytes, cells, data = load_inputs(args.upstream_checkout)
        refs = author_references(args.upstream_checkout, cells)
        args.results.mkdir(parents=True, exist_ok=True)
        with (args.results / ".B1.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("Another B1 process is using this results directory.") from error
            if args.action == "manifest":
                path = args.results / "manifest/b1_cells.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                e1.save_manifest(path, cell_manifest(config_bytes, cells, data))
                print(f"120 B1 cells: {path}")
                return 0
            b0 = b0_row(args.b0_csv, refs[B0_REF])
            if args.action == "report":
                records = load_records(args.results / "raw", cells, data, config, sha256(config_bytes))
                write_report(args.results, [*comparison_rows(cells, records, refs), b0], records)
                return 0
            previous_term = signal.signal(signal.SIGTERM, interrupt)
            try:
                return execute(args, config, config_bytes, cells, data, refs, b0, lock.fileno())
            finally:
                signal.signal(signal.SIGTERM, previous_term)
    except KeyboardInterrupt:
        print("B1 stopped. Review the saved attempt and gate report before resuming.", flush=True)
        return 130
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
