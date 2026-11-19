# E1 memory feasibility on Kaggle

The [Kaggle CPU notebook](../notebooks/e1_memory_feasibility.ipynb) runs one E1 cell under `-Xmx16g`. The default is **NZEnergy × Sgb(Arf) × seed 1**, a large E1 cell with a published output of 3,100,666 evaluated instances. The authors reported about 2.06 hours for that run. Kaggle runtime is unknown. A successful run establishes feasibility for that cell under the recorded limits. The C-01 eight-row smoke test only checks that the toolchain runs.

## Run

1. Use a dedicated Kaggle CPU notebook with **Accelerator → None**. Set `PROJECT` to a checkout or Dataset containing `scripts/e1_memory_feasibility.py` and `scripts/kaggle_environment_smoke.py`.
2. Stage the fat jar built from authors' commit `f62f7b437512e020f57c4bcd03884c4724eda5b1`, its recorded SHA-256 and the build JDK. From the pinned checkout's `moa/` directory, the build is `mvn clean install -DskipTests=true -Dmaven.javadoc.skip=true -Dlatex.skipBuild=true`. The artifact is `target/moa-2023.04.1-SNAPSHOT-jar-with-dependencies.jar`. Use the same JDK to run the jar. The [C-01 audit](kaggle_environment_audit.md) documents the verified JDK 11 build and the JDK 8 failure.
3. Enable Internet to fetch the public upstream commit, or set `UPSTREAM_CHECKOUT` to a local Git checkout containing the pinned object. The runner reads the E1 configuration and ARFF bytes from that commit. It verifies the supplied jar digest and records the uncompressed dataset digest.
4. Keep the default cell or select a dataset, learner key and seed from the original E1 configuration. Choose an unused manifest path for each attempt. Optionally set `TIMEOUT_SECONDS` below the remaining Kaggle session time to leave time to export outputs. Use **Save Version → Run All** for a persisted notebook run.

The command preserves the original learner options, outermost seed flag, dataset row order, prequential regression evaluator, sampling and status frequency, initial heap and thread stack. It replaces only `-Xmx48g` with `-Xmx16g` and changes file locations. The runner removes Java option environment variables from the child so they cannot override the supplied flags. There is no synthetic stream or instance cap. The final evaluator row must report the complete original stream.

## Interpret the manifest

The default manifest is `/kaggle/working/results/manifest/e1_memory_feasibility.json`. The adjacent `.files` directory contains the Java log and MOA CSV, if produced.

| Field | Meaning |
| --- | --- |
| `peak_java_rss_bytes` | Linux `wait4` high-water RSS for the Java child after it exits. An in-progress checkpoint uses `VmHWM`. |
| `memory_cgroup_before`, `memory_cgroup_latest` | Visible memory cgroup high-water marks before and after the run. The readings use `memory.peak` for v2 and `memory.max_usage_in_bytes` for v1. A pre-existing peak may dominate, and a shared scope includes other processes and page cache. Unavailable counters are omitted and unavailable peak files have a null value. |
| `wall_clock_seconds`, `exit_code`, `termination_signal` | External elapsed time and Java's exit code or terminating signal. Time spent preparing inputs is excluded. |
| `oom` | JVM OOM diagnostics and cgroup OOM counter deltas during the observation window. A cgroup kill counter increasing alongside Java's SIGKILL is evidence of a possible cgroup OOM kill. A cgroup counter alone does not identify the killed process. A v1 `failcnt` increase indicates a limit was hit. |
| `status` | `completed` requires Java exit 0, no observed Java OOM and a final evaluator row covering the entire stream. OOM, incomplete output, timeout and other failures remain separate. |

A session-wide kill may prevent the final write. The runner saves an atomic manifest checkpoint every 30 seconds while Java is alive. Treat a leftover `running` record as incomplete, with unknown final exit status and peak. The 16 GiB measurement is a feasibility check, not a replacement for published runtime results or evidence that the full E1 matrix fits.
