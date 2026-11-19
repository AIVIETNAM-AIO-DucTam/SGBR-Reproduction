#!/usr/bin/env python3
"""Measure a Linux notebook session and verify that its JDK can run code."""

import argparse
import datetime
import json
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


UPSTREAM = "https://github.com/nuwangunasekara/SGBR"
UPSTREAM_COMMIT = "f62f7b437512e020f57c4bcd03884c4724eda5b1"
MAVEN_ARTIFACT = (
    "https://repo.maven.apache.org/maven2/org/sonatype/oss/oss-parent/7/oss-parent-7.pom"
)
PYPI_METADATA = "https://pypi.org/pypi/capymoa/json"
KAGGLE_WORKING = Path("/kaggle/working")


def run(command, cwd=None):
    try:
        completed = subprocess.run(
            command, cwd=cwd, check=False, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"exit_code": None, "output": str(error)}
    return {
        "exit_code": completed.returncode,
        "output": (completed.stdout + completed.stderr).strip(),
    }


def https_probe(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return {"http_status": response.status}
    except urllib.error.HTTPError as error:
        return {"http_status": error.code}
    except (OSError, ValueError) as error:
        return {"http_status": None, "error": str(error)}


def cgroup_limits():
    """Read limits from conventional cgroup v2 mount paths and their parents."""
    root = Path("/sys/fs/cgroup")
    if not (root / "cgroup.controllers").exists():
        return {"version": None, "limits": []}
    member = next(
        line.partition("::")[2] for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    group = root / member.lstrip("/")
    limits = []
    for directory in (group, *group.parents):
        if not directory.is_relative_to(root):
            break
        entry = {"path": str(directory)}
        for filename in ("cpu.max", "memory.max"):
            try:
                entry[filename] = (directory / filename).read_text().strip()
            except FileNotFoundError:
                continue
        if len(entry) > 1:
            limits.append(entry)
    return {"version": 2, "limits": limits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/manifest/environment.json"))
    parser.add_argument("--local", action="store_true", help="Validate outside Kaggle")
    parser.add_argument("--session-limit-hours", type=float)
    parser.add_argument("--session-limit-source", help="Kaggle UI or documentation for this session")
    parser.add_argument("--java-selection-note", help="Reason for selecting a JDK newer than 8")
    args = parser.parse_args()
    if not args.local:
        if not KAGGLE_WORKING.is_dir():
            parser.error("run in Kaggle, or pass --local for a non-Kaggle validation")
        if (
            args.session_limit_hours is None
            or not math.isfinite(args.session_limit_hours)
            or args.session_limit_hours <= 0
            or not args.session_limit_source
        ):
            parser.error("record the Kaggle session limit and its source")

    working = KAGGLE_WORKING if not args.local else Path.cwd()
    tools = {tool: run([tool, flag]) for tool, flag in (
        ("python", "--version"), ("java", "-version"), ("javac", "-version"),
        ("mvn", "-version"), ("git", "--version"), ("unzip", "-v"),
    )}
    version = re.search(r'version "(?:1\.)?(\d+)', tools["java"]["output"])
    java_major = int(version[1]) if version else None
    with tempfile.TemporaryDirectory(prefix="sgbr-env-", dir=working) as directory:
        Path(directory, "Probe.java").write_text(
            'class Probe { public static void main(String[] args) { '
            'System.out.println("SGBR_JAVA_OK"); } }\n', encoding="utf-8"
        )
        compile_check = run(["javac", "Probe.java"], cwd=directory)
        launch_check = None
        if compile_check["exit_code"] == 0:
            launch_check = run(["java", "-cp", ".", "Probe"], cwd=directory)
        elif compile_check["exit_code"] is None and java_major is not None and java_major >= 11:
            # Source-file mode also exercises the bundled compiler on stripped JDK images.
            launch_check = run(["java", "Probe.java"], cwd=directory)

    java_ok = launch_check is not None and launch_check == {
        "exit_code": 0, "output": "SGBR_JAVA_OK"
    }
    selection_ok = args.local or java_major == 8 or (
        java_major is not None and java_major > 8 and bool(args.java_selection_note)
    )
    git_probe = run(["git", "ls-remote", "--exit-code", UPSTREAM, "HEAD"])
    memory = Path("/proc/meminfo").read_text()
    host_memory_kib = int(re.search(r"^MemTotal:\s+(\d+)", memory, re.MULTILINE)[1])
    disk = shutil.disk_usage(working)
    manifest = {
        "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "environment": "local" if args.local else "kaggle",
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "logical_cpus": os.cpu_count(),
        "affinity_cpus": len(os.sched_getaffinity(0)),
        "host_memory_kib": host_memory_kib,
        "cgroup": cgroup_limits(),
        "working_disk": {"path": str(working), "total_bytes": disk.total, "free_bytes": disk.free},
        "session_limit_hours": args.session_limit_hours,
        "session_limit_source": args.session_limit_source,
        "tools": tools,
        "java_major": java_major,
        "java_selection_note": args.java_selection_note,
        "java_compile": compile_check,
        "java_launch": launch_check,
        "network": {
            "upstream_git_head": git_probe,
            "maven_central": https_probe(MAVEN_ARTIFACT),
            "pypi": https_probe(PYPI_METADATA),
        },
        "expected_upstream_commit": UPSTREAM_COMMIT,
        "toolchain_smoke_passed": java_ok and selection_ok and tools["mvn"]["exit_code"] == 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if manifest["toolchain_smoke_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
