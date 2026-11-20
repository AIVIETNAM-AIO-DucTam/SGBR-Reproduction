"""Provision, verify and run the single-notebook Kaggle workflow."""

import csv
import datetime
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import e1_memory_feasibility as e1
import kaggle_environment_smoke as c01


REFERENCE_MOA_SHA256 = "9be332b07354c13237ead9a88d431a855ada14003395bb70386efc5f56ac4216"
FAT_JAR_NAME = "moa-2023.04.1-SNAPSHOT-jar-with-dependencies.jar"
JDK_DIRECTORY = "jdk-11.0.29+7"
MAVEN_DIRECTORY = "apache-maven-3.9.11"
JAVA_SELECTION_NOTE = "MEKA 1.9.7 in the pinned MOA fork requires at least Java 11."


JDK_NAME = "OpenJDK11U-jdk_x64_linux_hotspot_11.0.29_7.tar.gz"
JDK_URL = f"https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.29%2B7/{JDK_NAME}"
JDK_SHA256 = "3c8f2b53dd137cd86e54f40df96fd0fc56df72c749c06469e7eab216503bc7cf"
MAVEN_NAME = "apache-maven-3.9.11-bin.tar.gz"
MAVEN_URL = f"https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/{MAVEN_NAME}"
MAVEN_SHA512 = (
    "bcfe4fe305c962ace56ac7b5fc7a08b87d5abd8b7e89027ab251069faebee516b0"
    "ded8961445d6d91ec1985dfe30f8153268843c89aa392733d1a3ec956c9978"
)


def command(args, cwd, timeout=120):
    result = subprocess.run(
        args, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=timeout, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}\n{result.stdout[-5000:]}")
    return result.stdout


def digest(path, algorithm="sha256"):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def unpack_tool(work, directory, url, expected, algorithm):
    with tempfile.TemporaryDirectory(prefix=".download-", dir=work) as temporary:
        staging = Path(temporary)
        archive = staging / url.rsplit("/", 1)[1]
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if digest(archive, algorithm) != expected:
            raise RuntimeError(f"Checksum mismatch for {archive.name}")
        command(["tar", "-xzf", str(archive), "-C", str(staging)], staging)
        (staging / directory).rename(work / directory)


def smoke(work, jar, java):
    (work / "smoke.csv").unlink(missing_ok=True)
    fixture = "@relation probe\n@attribute x numeric\n@attribute z numeric\n@attribute y numeric\n@data\n"
    fixture += "".join(f"{i},{i % 2},{i * 2}\n" for i in range(1, 9))
    (work / "probe.arff").write_text(fixture, encoding="utf-8")
    task = (
        "EvaluatePrequentialRegression -s (ArffFileStream -f probe.arff) "
        "-l (meta.StreamingGradientBoostedTrees -t -L 1.0 -m 75 -s 10 "
        "-l (meta.OzaBag -s 10 -l (trees.FIMTDD -s VarianceReductionSplitCriterion "
        "-g 50 -c 0.01 -e)) -Z 1) -i 8 -f 8 -d smoke.csv"
    )
    log = command([str(java), "-Xmx256m", "-cp", str(jar), "moa.DoTask", task], work, timeout=60)
    (work / "java.log").write_text(log, encoding="utf-8")
    with (work / "smoke.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1 or float(rows[0]["learning evaluation instances"]) != 8:
        raise RuntimeError(f"Expected one MOA CSV row with eight processed instances, got {rows}")
    return {"passed": True, "processed_instances": 8, "seed": 1, "heap": "256m", "task": task}


def stage(message):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def tool_versions():
    return {tool: c01.run([tool, flag]) for tool, flag in (
        ("python", "--version"), ("java", "-version"), ("javac", "-version"), ("mvn", "-version"),
    )}


def select_jdk(cache):
    cached = cache / JDK_DIRECTORY
    candidates = [cached]
    javac = shutil.which("javac")
    if javac:
        candidates.append(Path(javac).resolve().parent.parent)
    candidates.extend(sorted(Path("/usr/lib/jvm").glob("*11*")))
    for home in candidates:
        compiler = c01.run([str(home / "bin/javac"), "-version"])
        java = c01.run([str(home / "bin/java"), "-version"])
        if (compiler["exit_code"] == java["exit_code"] == 0
                and re.search(r"\bjavac 11\.", compiler["output"])
                and 'version "11.' in java["output"]):
            return home.resolve()
    if platform.machine() != "x86_64":
        raise RuntimeError("No usable JDK 11 found. The verified Temurin download requires x86_64.")
    if cached.exists():
        raise RuntimeError(f"Cached JDK at {cached} failed verification. Remove it and rerun.")
    unpack_tool(cache, JDK_DIRECTORY, JDK_URL, JDK_SHA256, "sha256")
    return cached.resolve()


def select_maven(cache):
    bundled = cache / MAVEN_DIRECTORY / "bin/mvn"
    if bundled.is_file():
        return bundled
    maven = shutil.which("mvn")
    if maven is None:
        stage("Installing Maven with apt-get")
        try:
            subprocess.run(["apt-get", "update", "-qq"], check=True, timeout=300)
            subprocess.run(["apt-get", "install", "-y", "maven"], check=True, timeout=600)
        except (OSError, subprocess.SubprocessError):
            stage("apt-get could not install Maven. Using the checksum-verified Maven archive.")
        maven = shutil.which("mvn")
    if maven and c01.run([maven, "-version"])["exit_code"] == 0:
        return Path(maven)
    unpack_tool(cache, MAVEN_DIRECTORY, MAVEN_URL, MAVEN_SHA512, "sha512")
    return bundled


def provision(cache):
    jdk = select_jdk(cache)
    java = jdk / "bin/java"
    os.environ["JAVA_HOME"] = str(jdk)
    os.environ["PATH"] = f"{java.parent}{os.pathsep}{os.environ['PATH']}"
    java_version = command([str(java), "-version"], cache).strip()
    javac_version = command([str(jdk / "bin/javac"), "-version"], cache).strip()
    stage(f"Java selected: {java_version.splitlines()[0]}")
    mvn = select_maven(cache)
    os.environ["PATH"] = f"{mvn.parent}{os.pathsep}{os.environ['PATH']}"
    maven_version = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", command([str(mvn), "-version"], cache)).strip()
    runtime = re.search(r"runtime:\s*(.+)", maven_version)
    if runtime is None or Path(runtime[1].strip()).resolve() != jdk:
        raise RuntimeError("Maven did not select the notebook's JAVA_HOME.")
    stage(f"Maven verified: {maven_version.splitlines()[0]}")
    return java, mvn, {
        "java_home": str(jdk), "java_executable": str(java), "java_version": java_version,
        "javac_version": javac_version, "maven_executable": str(mvn), "maven_version": maven_version,
    }


def upstream_checkout(cache):
    source = cache / "upstream"
    if not source.exists():
        source.mkdir()
        command(["git", "init", "-q"], source)
    present = c01.run(["git", "-C", str(source), "cat-file", "-e", f"{c01.UPSTREAM_COMMIT}^{{commit}}"])
    if present["exit_code"] != 0:
        command(["git", "fetch", "--depth=1", c01.UPSTREAM, c01.UPSTREAM_COMMIT], source, timeout=300)
    actual = command(["git", "rev-parse", "--verify", f"{c01.UPSTREAM_COMMIT}^{{commit}}"], source).strip()
    if actual != c01.UPSTREAM_COMMIT:
        raise RuntimeError(f"Expected pinned MOA revision {c01.UPSTREAM_COMMIT}, found {actual}.")
    command(["git", "checkout", "--detach", actual], source)
    command(["git", "diff", "--quiet", "HEAD", "--"], source)
    return source, actual


def verified_jar(path):
    if not path.is_file():
        return False
    try:
        with zipfile.ZipFile(path) as jar:
            return {"moa/DoTask.class", "moa/classifiers/meta/StreamingGradientBoostedTrees.class"} <= set(jar.namelist())
    except zipfile.BadZipFile:
        return False


def build_or_reuse(source, artifacts, mvn, tools, actual):
    jar = artifacts / FAT_JAR_NAME
    provenance = artifacts / "moa_build.json"
    build_identity = {
        "upstream_commit": actual, "build_java_version": tools["java_version"],
        "build_maven_version": tools["maven_version"],
    }
    try:
        cached = json.loads(provenance.read_text()) if provenance.is_file() else {}
    except (OSError, ValueError):
        cached = {}
    reuse = (
        isinstance(cached, dict)
        and all(cached.get(key) == value for key, value in build_identity.items())
        and verified_jar(jar) and cached.get("sha256") == digest(jar)
    )
    if not reuse:
        log = artifacts / "moa_build.log"
        with log.open("wb") as output:
            result = subprocess.run(
                [str(mvn), "-B", "-ntp", "-C", "clean", "install", "-DskipTests=true",
                 "-Dmaven.javadoc.skip=true", "-Dlatex.skipBuild=true"],
                cwd=source / "moa", stdout=output, stderr=subprocess.STDOUT, timeout=1800, check=False,
            )
        if result.returncode:
            raise RuntimeError(f"MOA build failed with exit {result.returncode}. See {log}.")
        built = source / "moa/target" / FAT_JAR_NAME
        if not verified_jar(built):
            raise RuntimeError(f"The MOA build did not produce a usable fat jar at {built}.")
        staged = jar.with_suffix(".jar.tmp")
        shutil.copyfile(built, staged)
        staged.replace(jar)
    checksum = cached["sha256"] if reuse else digest(jar)
    details = {
        **build_identity, "path": str(jar), "sha256": checksum, "size_bytes": jar.stat().st_size,
        "reference_sha256": REFERENCE_MOA_SHA256, "matches_reference_sha256": checksum == REFERENCE_MOA_SHA256,
    }
    e1.save_manifest(provenance, details)
    return jar, {**details, "reused": reuse}


def archive_previous(manifests, results):
    names = ("environment.json", "e1_memory_feasibility.json", "e1_memory_feasibility.files")
    previous = [manifests / name for name in names if (manifests / name).exists()]
    if previous:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        archive = results / "previous_runs" / stamp
        archive.mkdir(parents=True)
        for item in previous:
            item.rename(archive / item.name)
        stage(f"Previous run files preserved in {archive}")


def warn_budget(session_limit_hours, started, timeout_seconds):
    if session_limit_hours is None:
        stage("Session budget is unknown. Allow at least 3.5 hours remaining for E1 and output export.")
        return
    remaining = session_limit_hours - (time.monotonic() - started) / 3600
    if remaining < 3.5:
        stage(f"Warning: only {remaining:.2f} hours of the configured session budget remain. E1 may be interrupted.")
    if timeout_seconds is not None and timeout_seconds / 3600 >= remaining:
        stage("Warning: the configured E1 timeout leaves no margin for Kaggle output export.")


def run_pipeline(working, project_commit, *, timeout_seconds=None, progress_interval=60,
                 session_limit_hours=None, session_limit_source=None, started=None, local=False):
    started = time.monotonic() if started is None else started
    if session_limit_hours is not None and (
        not math.isfinite(session_limit_hours) or session_limit_hours <= 0 or not session_limit_source
    ):
        raise ValueError("Supply a positive session limit and its source, or leave it unset.")
    if progress_interval <= 0 or (timeout_seconds is not None and timeout_seconds <= 0):
        raise ValueError("Progress interval and any configured timeout must be positive.")
    results = working / "results"
    manifests = results / "manifest"
    artifacts = results / "artifacts"
    cache = working / ".sgbr-cache"
    smoke_dir = results / "c01_smoke"
    for directory in (manifests, artifacts, cache, smoke_dir):
        directory.mkdir(parents=True, exist_ok=True)
    archive_previous(manifests, results)
    environment = manifests / "environment.json"
    metadata = {
        "project_git_commit": project_commit, "pipeline_status": "preparing",
        "notebook_smoke_passed": False,
        "ignored_java_option_variables": sorted(e1.JAVA_OPTION_VARIABLES & os.environ.keys()),
    }
    for name in metadata["ignored_java_option_variables"]:
        os.environ.pop(name)
    try:
        stage("Checking CPU, RAM, cgroup limits and installed tools")
        metadata["initial_tools"] = tool_versions()
        metadata["initial_cgroup"] = c01.cgroup_limits()
        stage(
            f"Python {platform.python_version()} | CPU affinity {len(os.sched_getaffinity(0))} | "
            f"cgroup RAM cap: {metadata['initial_cgroup']['memory_limit_bytes']} bytes"
        )
        java, mvn, tools = provision(cache)
        metadata["selected_tools"] = tools
        probe_args = [
            "--output", str(environment), "--allow-unknown-session-limit",
            "--java-selection-note", JAVA_SELECTION_NOTE,
        ]
        if local:
            probe_args.append("--local")
        if session_limit_hours is not None:
            probe_args.extend([
                "--session-limit-hours", str(session_limit_hours), "--session-limit-source", session_limit_source,
            ])
        if c01.main(probe_args):
            raise RuntimeError(f"C-01 toolchain probe failed. See {environment}.")

        stage("Verifying the pinned MOA source revision")
        source, actual = upstream_checkout(cache)
        stage("Preparing the MOA fat jar")
        jar, moa = build_or_reuse(source, artifacts, mvn, tools, actual)
        metadata["moa"] = moa
        stage(f"MOA jar {'reused' if moa['reused'] else 'built'} | SHA-256 {moa['sha256']}")
        if not moa["matches_reference_sha256"]:
            stage("Jar digest differs from the historical build. This run records the hash of its verified artifact.")

        stage("Running the C-01 eight-row smoke test")
        metadata["synthetic_smoke"] = smoke(smoke_dir, jar, java)
        metadata["notebook_smoke_passed"] = True
        metadata["pipeline_status"] = "c01_passed"
    except KeyboardInterrupt:
        metadata["pipeline_status"] = "interrupted"
        raise
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        metadata.update(pipeline_status="setup_failed", error=str(error))
        raise
    finally:
        observed = json.loads(environment.read_text()) if environment.is_file() else {}
        e1.save_manifest(environment, {**observed, **metadata})

    stage(f"C-01 smoke passed | {environment}")
    warn_budget(session_limit_hours, started, timeout_seconds)
    target = manifests / "e1_memory_feasibility.json"
    args = [
        "--upstream-checkout", str(source), "--moa-jar", str(jar), "--moa-sha256", moa["sha256"],
        "--java", str(java), "--manifest", str(target), "--dataset", "NZEnergy",
        "--learner", "SGBT(ARFReg(FIRTDD))", "--seed", "1", "--expected-instances", "3100666",
        "--progress-interval", str(progress_interval), "--project-git-commit", project_commit,
    ]
    if timeout_seconds is not None:
        args.extend(["--timeout-seconds", str(timeout_seconds)])
    if local:
        args.append("--local")
    stage("Starting E1 | NZEnergy | Sgb(Arf) | seed 1 | 16 GiB maximum heap")

    def interrupt_on_term(signum, frame):
        raise KeyboardInterrupt

    previous_term = signal.signal(signal.SIGTERM, interrupt_on_term)
    try:
        returncode = e1.main(args)
    finally:
        signal.signal(signal.SIGTERM, previous_term)
    manifest = json.loads(target.read_text())
    manifest.update(project_git_commit=project_commit, build_tools=tools, environment_manifest=environment.name)
    e1.save_manifest(target, manifest)
    stage(f"E1 {manifest['status']} | {target}")
    return returncode
