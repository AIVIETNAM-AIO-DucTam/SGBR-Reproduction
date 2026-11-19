#!/usr/bin/env python3
"""Run and measure one full E1 cell under a 16 GiB Java heap on Linux."""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
import zipfile
from pathlib import Path

from kaggle_environment_smoke import KAGGLE_WORKING, UPSTREAM_COMMIT, cgroup_limits


DEFAULT_DATASET = "NZEnergy"
DEFAULT_LEARNER = "SGBT(ARFReg(FIRTDD))"
JAVA_OPTION_VARIABLES = {"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"}
OOM_PATTERN = re.compile(
    rb"OutOfMemoryError|Native memory allocation.*failed|There is insufficient memory",
    re.IGNORECASE,
)


def git_bytes(repo, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{UPSTREAM_COMMIT}:{path}"])


def stream_bytes(repo, dataset, work):
    upstream = f"exp/RDatasets/{dataset}.arff"
    archive = work / "original.zip"
    dataset_path = work / "stream.arff"
    try:
        with dataset_path.open("wb") as stream:
            direct = subprocess.run(
                ["git", "-C", str(repo), "show", f"{UPSTREAM_COMMIT}:{upstream}"],
                stdout=stream, stderr=subprocess.PIPE, check=False,
            )
        if direct.returncode:
            with archive.open("wb") as file:
                zipped_input = subprocess.run(
                    ["git", "-C", str(repo), "show", f"{UPSTREAM_COMMIT}:{upstream}.zip"],
                    stdout=file, stderr=subprocess.PIPE, check=False,
                )
            if zipped_input.returncode:
                raise ValueError(f"The pinned upstream checkout does not contain an ARFF for {dataset}.")
            with zipfile.ZipFile(archive) as zipped:
                with zipped.open(f"{dataset}.arff") as source, dataset_path.open("wb") as stream:
                    shutil.copyfileobj(source, stream)
    finally:
        archive.unlink(missing_ok=True)
    return dataset_path


def dataset_evidence(path):
    digest = hashlib.sha256()
    in_data = False
    count = 0
    with path.open("rb") as stream:
        for line in stream:
            digest.update(line)
            value = line.strip()
            if in_data:
                count += bool(value and not value.startswith(b"%"))
            elif value.lower() == b"@data":
                in_data = True
    if not count:
        raise ValueError("The pinned ARFF has no data rows.")
    return {"sha256": digest.hexdigest(), "expected_instances": count}


def e1_command(config, dataset, learner_name, seed, java, jar):
    if dataset not in config["datasets"] or dataset in config["streams"]:
        raise ValueError("Select an original E1 dataset backed by a shipped ARFF.")
    if seed not in config["random_seeds"]:
        raise ValueError("Select an original E1 seed from 1 through 5.")
    for name, seed_flag, learner in config["learners"]:
        if name == learner_name:
            break
    else:
        raise ValueError("Select an exact learner name from exp/exp_config.json.")
    if learner_name == "AXGBr":
        raise ValueError("The approved E1 plan limits Axgb to its separate Core-10 runs.")
    if seed_flag:
        learner += f" -{seed_flag} {seed}"
    elif seed != config["random_seeds"][0]:
        raise ValueError("This learner has no seed flag. Select 1 to follow the one-run rule.")

    jvm = config["java_options"].split()
    jvm[jvm.index("-Xmx48g")] = "-Xmx16g"
    task = (
        f'{config["evaluator"]} -s (ArffFileStream -f stream.arff) '
        f"-l ({learner}) -d evaluation.csv"
    )
    return [java, "-classpath", str(jar), *jvm, task]


def read_text(path):
    try:
        return path.read_text()
    except OSError:
        return ""


def read_counter(path):
    value = read_text(path).strip()
    return int(value) if value.isdecimal() else None


def memory_snapshot(groups):
    snapshots = {}
    for entry in groups["limits"]:
        path = Path(entry["path"])
        if "memory.max" in entry:
            peak, event_file = "memory.peak", "memory.events"
        elif "memory.limit_in_bytes" in entry:
            peak, event_file = "memory.max_usage_in_bytes", "memory.oom_control"
        else:
            continue
        counters = {}
        for line in read_text(path / event_file).splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1].isdecimal():
                counters[fields[0]] = int(fields[1])
        if event_file == "memory.oom_control":
            failures = read_counter(path / "memory.failcnt")
            if failures is not None:
                counters["failcnt"] = failures
        snapshots[str(path)] = {
            "peak_bytes": read_counter(path / peak),
            "counter_source": event_file,
            "counters": counters,
        }
    return snapshots


def memory_deltas(before, after):
    result = {}
    for path in before.keys() & after.keys():
        initial = before[path]["counters"]
        final = after[path]["counters"]
        result[path] = {
            name: final[name] - initial[name]
            for name in ("oom", "oom_kill", "oom_group_kill", "failcnt")
            if name in initial and name in final and final[name] >= initial[name]
        }
    return result


def save_manifest(path, result):
    staged = path.with_suffix(".json.tmp")
    staged.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    staged.replace(path)


def java_oom(work):
    files = [work / "java.log", *work.glob("hs_err_pid*.log")]
    for path in files:
        with path.open("rb") as handle:
            if any(OOM_PATTERN.search(line) for line in handle):
                return True
    return False


def processed_instances(csv_path):
    if not csv_path.is_file():
        return None
    last = None
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            last = row
    if last is None:
        return None
    try:
        count = float(last["learning evaluation instances"])
    except (KeyError, TypeError, ValueError):
        return None
    return int(count) if count.is_integer() else None


def measure_java(manifest, result, work, groups, timeout, env):
    result["memory_cgroup_before"] = memory_snapshot(groups)
    started = time.monotonic()
    checkpoint = started
    interrupted = None
    with (work / "java.log").open("wb") as log:
        process = subprocess.Popen(
            result["command"], cwd=work, stdout=log, stderr=subprocess.STDOUT, env=env,
        )
        result.update(status="running", java_pid=process.pid)
        pid = 0
        try:
            while True:
                pid, wait_status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    break
                now = time.monotonic()
                if timeout is not None and now - started >= timeout:
                    interrupted = "timed_out"
                    break
                if now >= checkpoint:
                    rss = re.search(r"^VmHWM:\s+(\d+) kB", read_text(Path(f"/proc/{process.pid}/status")), re.M)
                    result.update(
                        wall_clock_seconds=now - started,
                        peak_java_rss_bytes=int(rss[1]) * 1024 if rss else None,
                        memory_cgroup_latest=memory_snapshot(groups),
                    )
                    save_manifest(manifest, result)
                    checkpoint = now + 30
                time.sleep(0.5)
        except KeyboardInterrupt:
            interrupted = "interrupted"
        finally:
            if not pid:
                try:
                    os.kill(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, wait_status, usage = os.wait4(process.pid, 0)
            process.returncode = os.waitstatus_to_exitcode(wait_status)

    result.update(
        wall_clock_seconds=time.monotonic() - started,
        peak_java_rss_bytes=usage.ru_maxrss * 1024,
        exit_code=process.returncode if process.returncode >= 0 else None,
        termination_signal=-process.returncode if process.returncode < 0 else None,
        memory_cgroup_latest=memory_snapshot(groups),
    )
    deltas = memory_deltas(result["memory_cgroup_before"], result["memory_cgroup_latest"])
    java_reported_oom = java_oom(work)
    cgroup_kill = any(
        counters.get("oom_kill", 0) or counters.get("oom_group_kill", 0) for counters in deltas.values()
    )
    result["oom"] = {
        "java_reported": java_reported_oom,
        "cgroup_counter_deltas": deltas,
        "sigkill_coincided_with_cgroup_oom_kill": result["termination_signal"] == signal.SIGKILL and cgroup_kill,
    }
    count = processed_instances(work / "evaluation.csv")
    result["processed_instances"] = count
    if interrupted:
        result["status"] = interrupted
    elif java_reported_oom or result["oom"]["sigkill_coincided_with_cgroup_oom_kill"]:
        result["status"] = "oom_observed"
    elif process.returncode:
        result["status"] = "java_failed"
    elif count != result["dataset"]["expected_instances"]:
        result["status"] = "incomplete_stream"
    else:
        result["status"] = "completed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-checkout", type=Path, required=True)
    parser.add_argument("--moa-jar", type=Path, required=True)
    parser.add_argument("--moa-sha256", required=True)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--learner", default=DEFAULT_LEARNER)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--java", default="java")
    parser.add_argument("--manifest", type=Path, default=Path("results/manifest/e1_memory_feasibility.json"))
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--local", action="store_true", help="Label validation outside Kaggle")
    args = parser.parse_args()
    if not args.local and not KAGGLE_WORKING.is_dir():
        parser.error("Run in a Kaggle CPU notebook, or pass --local for local validation.")
    if args.timeout_seconds is not None and args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive.")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.moa_sha256):
        parser.error("--moa-sha256 must be the recorded digest of the pinned MOA jar.")

    manifest = args.manifest.resolve()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    work = manifest.with_suffix(".files")
    if manifest.exists() or work.exists():
        parser.error("Choose a new manifest path to preserve prior evidence.")
    work.mkdir()
    result = {
        "status": "preparing",
        "environment": "local" if args.local else "kaggle",
        "scope": "one full E1 cell",
        "upstream_commit": UPSTREAM_COMMIT,
        "dataset": {"name": args.dataset},
        "learner": args.learner,
        "seed": args.seed,
        "java_max_heap_bytes": 16 * 1024**3,
        "java_log": f"{work.name}/java.log",
        "evaluation_csv": f"{work.name}/evaluation.csv",
        "exit_code": None,
        "termination_signal": None,
        "timeout_seconds": args.timeout_seconds,
    }
    save_manifest(manifest, result)
    try:
        config = json.loads(git_bytes(args.upstream_checkout, "exp/exp_config.json"))
        jar = args.moa_jar.resolve(strict=True)
        with jar.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != args.moa_sha256.lower():
            raise ValueError("MOA jar does not match the recorded SHA-256.")
        result["moa_jar_sha256"] = digest
        java = shutil.which(args.java)
        if java is None:
            raise ValueError("Java was not found. Set --java to the verified MOA build JDK.")
        result["command"] = e1_command(config, args.dataset, args.learner, args.seed, java, jar)
        env = {key: value for key, value in os.environ.items() if key not in JAVA_OPTION_VARIABLES}
        result["ignored_java_option_variables"] = sorted(JAVA_OPTION_VARIABLES & os.environ.keys())
        result["java_version"] = subprocess.check_output(
            [java, "-version"], stderr=subprocess.STDOUT, text=True, timeout=30, env=env,
        ).strip()
        stream = stream_bytes(args.upstream_checkout, args.dataset, work)
        result["dataset"].update(dataset_evidence(stream))
        groups = cgroup_limits()
        result["cgroup_limits"] = groups
        measure_java(manifest, result, work, groups, args.timeout_seconds, env)
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile, KeyError) as error:
        result.update(status="error", error=str(error))
    finally:
        (work / "stream.arff").unlink(missing_ok=True)
        save_manifest(manifest, result)
    print(f"{result['status']}: {manifest}")
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
