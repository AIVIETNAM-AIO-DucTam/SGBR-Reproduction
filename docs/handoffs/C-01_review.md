# C-01 Scientific Review — Kaggle environment audit

**Reviewer:** Claude (Research Scientist) · **Date:** 2026-11-19
**Reviewed:** PR #1 (`audit/c-01-kaggle-environment`, merge `dffa6ff`, commit `14bb8e2`). It adds `docs/kaggle_environment_audit.md` and `scripts/kaggle_environment_smoke.py`. Both were read against `docs/experiment_plan.md`, `docs/tasks.md`, `docs/paper_spec.md` §11 and the authors' repo at `f62f7b4`.
**Verdict:** **C-01 is NOT complete.** The audit is accurate and careful, but the acceptance evidence, a manifest from a real Kaggle session with the Java version recorded, does not exist yet (the audit says so itself, l.60, l.70). No implementation files were modified by this review.

---

## 1. Does the audit match the paper?

Mostly yes. Every environment claim I checked is consistent with the paper or the repo:

| Audit claim | Check | Result |
|---|---|---|
| E1 JVM `-Xmx48g -Xms50m -Xss1g`; other configs 12 GiB; Sgb(Oza) fit in 12 GiB | Paper App. A.1 p.34; `exp/exp_config.json:4` | ✔ |
| Paper used JDK 8 | Paper p.34 "JDK 1.8.0" | ✔ |
| Child POM targets 1.8 | `moa/pom.xml:221-226` | ✔ (see R-3: no `<release>`) |
| Runner is stdlib-only, Python 3.9 upstream | `exp/benchmark_moa.py`; README | ✔ |
| E3 needs CapyMOA + jar swap + mlxtend + sklearn + SciPy | `exp/Bias_Variance_Decomp/*` | ✔ |
| 13 of 16 streams shipped; SUP\* on request | README; `paper_spec.md` §11.6 | ✔ |
| CapyMOA 0.15.1 / mlxtend 0.25.0 require Python ≥ 3.11 | PyPI metadata, as observed by Codex | Not independently verified by me; plausible. Treat as Codex's observation |

Gaps against the paper:

- **G-1. The memory picture is more favourable than the audit suggests.** Only E1 needed `-Xmx48g`. Per App. A.1, E4/E5/E6 ran with `-Xmx12g` on a 16 GB Windows machine, and Fig.6 (E2) on a 16 GB MacBook. Of the planned experiments, only E1-large is memory-critical. E3 ran on a 1 TB machine and its real need is unknown. The audit should separate the experiments this way.
- **G-2. Hardware disclosure.** The paper reports CPU model, cores, RAM, OS and JVM per experiment (App. A.1). The probe does not record the **CPU model or frequency** (`/proc/cpuinfo`) or the **Kaggle Docker image / environment version**. The report needs both, and both are required to interpret wall time (V5).

## 2. Is the smoke test scientifically meaningful?

As an **environment probe**, which is what C-01 asks for, yes. It checks that a JDK compiles and runs code, records versions, resources and reachability, and refuses to run outside Kaggle without `--local`. As **scientific** evidence it validates nothing about SGBR. The audit is honest about this (l.66).

- The local 8-row ARFF run of Sgb(Oza) only exercises CLI wiring. It cannot detect numeric divergence.
- The first scientifically meaningful check is C-02's Abalone parity test (R̄² = 0.47689 to ≤ 1e-6 vs `exp/post_hoc_new/abalone_1/SGBT(Oza).csv`). Recommend running it **in the same Kaggle session** as the C-01 probe once a jar is available, so the environment and the parity result are tied together.
- `toolchain_smoke_passed` requires `mvn` (l.148). Under K-A we may build the jar once and upload it, in which case Kaggle needs only a JRE. Maven presence should be recorded, but making it a pass condition is stricter than the plan requires. Minor.

## 3. Overlooked dependencies or constraints

Ordered by impact on the reproduction.

| ID | Finding | Why it matters | Recommendation |
|---|---|---|---|
| **R-1** | **Single-run duration vs session limit.** MOA has no checkpointing. Per Tab.4/Tab.9, single NZEnergy runs take ≈ 6.1 h (Srp(Sgbt)) and ≈ 6.4 h ± 2.7 h (Sgb(Srp), std 9.8e3 s) **at paper speed** | With a Kaggle slowdown > ~1.8×, these cells can never finish inside a ~12 h session, whatever the parallelism | Measure the slowdown factor early (C-08) and pre-classify cells that can't fit as "not run – session limit". Record the limit precisely (the probe already asks for it) |
| **R-2** | **JDK choice affects wall time, not R̄².** JDK 8 defaults to Parallel GC; JDK 9+ defaults to G1. SGBT calls `System.gc()` every 1,000 training instances [CODE SGBT.java:393-395], so GC choice and heap size hit wall time directly. `java.util.Random` is specified identically across JDKs, and the configs run single-threaded (`-t`; no `-T`), so R̄² should not depend on the JDK. C-02 parity confirms it | Wall-time ratios (claims C4, C9) may shift if the JDK differs from the paper's | Prefer JDK 8. If a newer JDK is used, record the GC in effect (`-XX:+PrintCommandLineFlags`). Any `-XX:+UseParallelGC` override needs human approval as an [ADAPT] |
| **R-3** | **Jar built with JDK 21 is validated only for JDK 21.** `moa/pom.xml` sets `source/target 1.8` but no `<release>8</release>`. Bytecode compiled by JDK 21 against JDK 21's class library can fail on JDK 8 with `NoSuchMethodError` (javac warns "bootstrap class path not set") | The SHA-256 `3f6e…baf7` jar must not be assumed to run on JDK 8 | Build with the JDK you will run (JDK 8 if available). Use **one** jar artefact for every experiment and record its SHA-256 in the manifest. Maven builds are not byte-reproducible, so the hash identifies the artefact; it is not a rebuild check |
| **R-4** | **cgroup v1 not measured.** `cgroup_limits()` returns `version: None` for v1/hybrid hosts. The manifest then holds only `MemTotal`, which in a container usually shows **host** memory, and `os.cpu_count()` can likewise show host CPUs | Heap and concurrency budgets would be based on the wrong numbers | Also read the v1 files (`memory/memory.limit_in_bytes`, `cpu/cpu.cfs_quota_us` / `cpu.cfs_period_us`), and the JVM's own view: `java -XX:+PrintFlagsFinal -version` (MaxHeapSize, ActiveProcessorCount) |
| **R-5** | **Heap feasibility is never tested.** Nothing launches a JVM with the planned heap (`-Xmx12g -Xss1g`) inside the container cap | The binding constraint for E1-large stays unknown | Add `java -Xmx12g -Xms50m -Xss1g -version` (and the largest heap the cap allows). Record peak RSS of real runs in C-05. Any `-Xmx` below the paper's needs an approved [ADAPT]. Heap size does not change R̄² unless a run hits OOM, but it can change wall time |
| **R-6** | **Pinned commit is not actually checked.** The probe runs `git ls-remote … HEAD` and stores `expected_upstream_commit`, but never compares them. Upstream HEAD can move | "Reachable" is mistaken for "pinned revision available" | Fetch `f62f7b4` explicitly (or compare ls-remote output) and record `pinned_commit_available: true/false` |
| **R-7** | **E3 Python stack.** Codex observed that current CapyMOA/mlxtend versions need Python ≥ 3.11, while upstream says 3.9. There is a further risk: CapyMOA's JPype bridge expects MOA classes and APIs from its own bundled jar, and swapping in the 2023.04-snapshot jar may break newer CapyMOA. mlxtend's `bias_variance_decomp` bootstrap behaviour is version-dependent and affects Figs.2/7/8 | E3 fidelity | Separate task (proposed C-01b, below): pick a CapyMOA version contemporaneous with the authors' runs (~2024–Sep 2025) that accepts the repo jar; pin mlxtend; check against `BVDecompose_Results_ailerons.csv`. Not a C-01 blocker |
| **R-8** | **Axgb native libraries.** xgboost4j 2.1.1 JNI needs a compatible glibc/libgomp and architecture | Axgb's 10 planned runs (H-01(f)) | Add a one-line Axgb launch on a tiny ARFF to C-02, not C-01 |
| **R-9** | **Kaggle execution mode.** Interactive sessions have idle timeouts. Long runs should use "Save Version → Run All" (batch commit), whose outputs persist under `/kaggle/working` (≈ 20 GB output limit, per the audit) **[EXT, verify]** | Lost outputs; the C-05 resumability design | Record which mode the probe ran in. Plan long runs for batch mode |
| **R-10** | **Concurrency vs wall time.** All configured learners are single-threaded, so parallel JVMs scale well. But running 4 JVMs on 4 vCPUs (likely hyperthreads) slows each run compared with the paper's one-run-per-machine timings | V5 relies on within-run ratios, so ratios must come from runs at the **same** concurrency | Record the concurrency level per run in C-05. Compute wall-time ratios only within one concurrency setting |
| R-11 | Provisioning steps are prose. "Provision JDK 8 and Maven from trusted, verified artifacts" gives no commands or checksums | Reproducibility of the environment itself | A Kaggle notebook (`notebooks/`) with exact install commands and checksum verification. Codex owns notebooks per CLAUDE.md |

## 4. Is the proposed Kaggle environment feasible?

| Scope | Assessment (paper-speed estimates from `experiment_plan.md` §7.4; Kaggle slowdown unknown) |
|---|---|
| **Minimal tier (T1 + T1b + T1c)** | **Feasible**, with one caveat. About 5.8 h of single-core work on small datasets (all ≤ 50k instances), so ~2 h wall time with 4 parallel JVMs if slowdown ≤ 2×. The caveat is memory: 4 × `-Xmx12g` exceeds ~30 GB. Small datasets almost certainly need far less than 12 GB, but lowering `-Xmx` is an [ADAPT] that needs approval (Q-37) |
| E2, E4, E5, E6 | Feasible. The paper itself ran them with 12 GB heaps on 16 GB machines (G-1) |
| E1-core (Core-11) | Feasible across a few sessions. The HyperA runs (≤ 1.4e3 s for Oza(Sgbt), ≤ 2.8e3 s for Srp(Sgbt)) fit |
| **E1-large (DemandF, NZEnergy)** | **At risk** for two reasons: the 48 GB heap (R-5) and single-run duration (R-1). NZEnergy is ≈ 116 h of the ≈ 232 h total and contains the longest individual runs. Feasibility is decided by the C-08 slowdown factor and a measured NZEnergy peak heap. Until then, plan for NZEnergy being partly "not run" |
| E3 | Unknown until R-7 is resolved |

## 5. What remains to satisfy C-01 acceptance

C-01 acceptance (`tasks.md`): *Kaggle environment probe: vCPU, RAM, disk, session limit, internet, Java/Maven presence; install JDK 8 (or the closest available) → `results/manifest/environment.json`; Java version recorded.*

| Criterion | Status |
|---|---|
| Probe executed **in Kaggle** | ✘ Not done (only Codex Cloud with `--local`) |
| JDK 8 installed (or closest, with justification) | ✘ Not done in Kaggle |
| vCPU, RAM (effective container limits), disk, session limit recorded | ✘ Kaggle values missing. Script support is partial: R-4 (v1), G-2 (CPU model) |
| Internet (GitHub, Maven Central, PyPI) recorded | ✘ Kaggle values missing; script support ✔ |
| Java / Maven presence and Java version recorded | ✘ Kaggle values missing; script support ✔ |
| `results/manifest/environment.json` committed to the repo | ✘ The audit keeps it as notebook output only. Plan §10.1 expects it in `results/manifest/` |

**Required before C-01 can be accepted (minimum):**
1. Run the probe in a Kaggle CPU notebook after provisioning a JDK (8 preferred). Commit the resulting `results/manifest/environment.json` together with the notebook that produced it.
2. Make the manifest hold the effective CPU and memory limits whatever the cgroup version, plus the JVM's view of them (R-4).

**Recommended additions to the probe (cheap; strengthen C-01 without changing scope):** CPU model/frequency and Kaggle image version (G-2); a pinned-commit check (R-6); `java -Xmx12g -Xss1g -version` heap launch (R-5); execution mode (R-9).

**Explicitly *not* C-01:** jar build, Abalone parity and the Axgb JNI check (C-02); E3 stack (proposed C-01b); slowdown factor (C-08).

## 6. Decisions requested from the human

- **Q-37:** May per-process `-Xmx` be lowered below the paper's values for small datasets (e.g. 6 GiB for Core-10, so 4 JVMs fit in the cap)? R̄² is unaffected unless a run hits OOM, which is logged as "not run"; wall time may be. The heap actually used is recorded.
- **Q-38:** If JDK 8 is unavailable on Kaggle, is a newer JDK acceptable provided C-02 Abalone parity holds to 1e-6? Wall-time ratios would then carry a JDK caveat (R-2).
- **Q-39:** Cells whose single-run time can't fit the session limit (likely some NZEnergy runs): report them as "not run – session limit"? Or allow an approved alternative (e.g. a longer-running environment outside Kaggle, disclosed as such)?
