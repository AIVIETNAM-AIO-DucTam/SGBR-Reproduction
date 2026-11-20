# E1 memory feasibility on Kaggle

The Kaggle CPU notebooks run one E1 cell under `-Xmx16g`. The default is **NZEnergy × Sgb(Arf) × seed 1**, a large E1 cell with a published output of 3,100,666 evaluated instances. The authors reported about 2.06 hours for that run. Kaggle runtime is unknown. A successful run establishes feasibility for that cell under the recorded limits. The C-01 eight-row smoke test only checks that the toolchain runs.

## Integrated Kaggle workflow

Use [SGBR_C01_E1_Integrated.ipynb](../notebooks/SGBR_C01_E1_Integrated.ipynb) for a fresh session. Import it into a **private** Kaggle notebook, set **Accelerator → None**, enable **Internet**, and grant the notebook access to the Kaggle Secret `GITHUB_TOKEN`. Use a fine-grained GitHub token with **Contents: Read** for this project. Run All with `GITHUB_REF = "main"` after merge, or select the feature branch or exact SHA during review. There is no jar or checksum to supply.

The notebook records the project SHA, verifies the upstream commit, selects Java 11, and installs Maven if needed. It stores the fat jar and its verified SHA-256 under `/kaggle/working/results/artifacts/`. It checks the historical jar digest for comparison. A new build can have a different digest, so the C-01 smoke and E1 both use the bytes verified for the current run. A failed C-01 setup or smoke test prevents E1 from starting.

The default is one NZEnergy × Sgb(Arf) × seed 1 cell with `-Xmx16g`. If set, `SESSION_LIMIT_HOURS` and `SESSION_LIMIT_SOURCE` let the notebook warn about time remaining. `TIMEOUT_SECONDS` is optional and has no default cap. Leave time to export results. The notebook prints timestamps and flushes one E1 progress line per minute by default.

| Output under `/kaggle/working/results/` | Contents |
| --- | --- |
| `manifest/environment.json` | C-01 probes, toolchain versions, smoke result, source commits, and jar provenance |
| `manifest/e1_memory_feasibility.json` | Status, elapsed time, peak memory, exit or signal, OOM evidence, latest MOA percentage, estimated rows, and evaluator-verified rows |
| `manifest/e1_memory_feasibility.files/` | Raw Java log, evaluator CSV if written, and periodic `resource_monitor.jsonl` |
| `artifacts/` | Verified jar, build metadata, and Maven build log |
| `previous_runs/` | Earlier manifests and E1 log directories when rerunning in the same session |

A manual interrupt or the runner timeout keeps the latest observations and records the stop. A hard Kaggle session kill can leave only the last periodic checkpoint. MOA learner state is not saved. Reruns start the stream from the beginning. Download the results directory or use **Save Version → Run All** to retain Kaggle outputs.

## Standalone run

Use the [standalone notebook](../notebooks/e1_memory_feasibility.ipynb) when you already have a verified jar and want to select a different E1 cell.


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
