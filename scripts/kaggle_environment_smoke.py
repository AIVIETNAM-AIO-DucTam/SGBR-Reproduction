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


def cgroup_limits(membership=None, mountinfo=None):
    """Read visible v1/v2 ancestor limits from the process's actual mounts."""
    if membership is None:
        membership = Path("/proc/self/cgroup").read_text()
    if mountinfo is None:
        mountinfo = Path("/proc/self/mountinfo").read_text()
    members = {}
    for line in membership.splitlines():
        _, controllers, member = line.split(":", 2)
        for controller in controllers.split(","):
            members[controller] = Path(member)

    limits = []
    cpu_quotas = []
    memory_caps = []
    versions = set()
    for line in mountinfo.splitlines():
        mount, filesystem = line.split(" - ", 1)
        kind, _, options = filesystem.split()[:3]
        if kind not in ("cgroup", "cgroup2"):
            continue
        mount_root, mount_path = (
            Path(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), field))
            for field in mount.split()[3:5]
        )
        v2 = kind == "cgroup2"
        controllers = {""} if v2 else set(options.split(",")) & {"cpu", "memory"}
        for controller in sorted(controllers & members.keys()):
            member = members[controller]
            if member == Path("/"):
                group = mount_path
            elif member.is_relative_to(mount_root):
                group = mount_path / member.relative_to(mount_root)
            else:
                continue
            files = {
                "": ("cpu.max", "memory.max"),
                "cpu": ("cpu.cfs_quota_us", "cpu.cfs_period_us"),
                "memory": ("memory.limit_in_bytes",),
            }[controller]
            for directory in (group, *group.parents):
                if not directory.is_relative_to(mount_path):
                    break
                values = {}
                for filename in files:
                    try:
                        values[filename] = (directory / filename).read_text().strip()
                    except OSError:
                        continue
                if values:
                    versions.add(2 if v2 else 1)
                    limits.append({"path": str(directory), **values})
                quota, period = values.get("cpu.max", "-1 1").split()
                quota = values.get("cpu.cfs_quota_us", quota)
                period = int(period if v2 else values.get("cpu.cfs_period_us", "0"))
                if quota != "max" and int(quota) > 0 and period > 0:
                    cpu_quotas.append(int(quota) / period)
                memory = values.get("memory.max", values.get("memory.limit_in_bytes", "max"))
                # cgroup v1 represents unlimited memory with a page-aligned LONG_MAX.
                if memory != "max" and int(memory) < 2**60:
                    memory_caps.append(int(memory))

    return {
        "version": "hybrid" if len(versions) > 1 else next(iter(versions), None),
        "limits": limits,
        "cpu_quota_cores": min(cpu_quotas, default=None),
        "memory_limit_bytes": min(memory_caps, default=None),
    }


def cpu_info():
    info = Path("/proc/cpuinfo").read_text()
    models = re.findall(r"^model name\s*:\s*(.+)$", info, re.MULTILINE)
    frequencies = re.findall(r"^cpu MHz\s*:\s*(.+)$", info, re.MULTILINE)
    return {"models": sorted(set(models)), "observed_mhz": sorted(set(map(float, frequencies)))}


def jvm_resources():
    flags = run(["java", "-XX:+PrintFlagsFinal", "-version"])
    selected = dict(re.findall(
        r"^\s*\w+\s+(ActiveProcessorCount|MaxHeapSize|Use\w+GC)\s*:?=\s*(\S+)",
        flags["output"], re.MULTILINE,
    ))
    return {
        "flags": selected,
        "settings": run(["java", "-XshowSettings:system", "-version"]),
        "defaults": run(["java", "-XX:+PrintCommandLineFlags", "-version"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/manifest/environment.json"))
    parser.add_argument("--local", action="store_true", help="Validate outside Kaggle")
    parser.add_argument("--session-limit-hours", type=float)
    parser.add_argument("--session-limit-source", help="Kaggle UI or documentation for this session")
    parser.add_argument("--java-selection-note", help="Reason for selecting a JDK newer than 8")
    parser.add_argument("--allow-missing-maven", action="store_true", help="For a staged MOA jar")
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
            'System.out.println("SGBR_JAVA_OK"); '
            'System.out.println(Runtime.getRuntime().availableProcessors()); '
            'System.out.println(Runtime.getRuntime().maxMemory()); } }\n', encoding="utf-8"
        )
        compile_check = run(["javac", "Probe.java"], cwd=directory)
        launch_check = None
        if compile_check["exit_code"] == 0:
            launch_check = run(["java", "-cp", ".", "Probe"], cwd=directory)
        elif compile_check["exit_code"] is None and java_major is not None and java_major >= 11:
            # Source-file mode also exercises the bundled compiler on stripped JDK images.
            launch_check = run(["java", "Probe.java"], cwd=directory)

    runtime = re.search(
        r"^SGBR_JAVA_OK\s*\n([1-9][0-9]*)\s*\n([1-9][0-9]*)$",
        launch_check["output"] if launch_check else "", re.MULTILINE,
    )
    java_ok = launch_check is not None and launch_check["exit_code"] == 0 and runtime is not None
    jvm = jvm_resources()
    if java_ok:
        jvm.update(available_processors=int(runtime[1]), max_memory_bytes=int(runtime[2]))
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
        "cpu": cpu_info(),
        "jvm_resources": jvm,
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
        "toolchain_smoke_passed": (
            java_ok and selection_ok and (args.allow_missing_maven or tools["mvn"]["exit_code"] == 0)
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if manifest["toolchain_smoke_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
