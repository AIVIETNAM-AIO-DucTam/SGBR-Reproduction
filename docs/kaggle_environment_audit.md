# C-01 Kaggle environment audit

The pinned SGBR fork is a candidate for Kaggle CPU notebooks. Its Java CLI uses no GPU and the Python launcher uses only the standard library. A live Kaggle session still needs to confirm the toolchain, connectivity and resource limits. E1's 48 GiB maximum Java heap cannot be budgeted safely on a session with roughly 30 GB RAM, and three of its streams are missing upstream. These constraints limit a full reproduction even if the smoke test passes.

## Dependency inventory

Audited the authors' Git HEAD at [`f62f7b437512e020f57c4bcd03884c4724eda5b1`](https://github.com/nuwangunasekara/SGBR/tree/f62f7b437512e020f57c4bcd03884c4724eda5b1), the revision approved in H-01.

| Workflow | Requirements |
| --- | --- |
| Java CLI and benchmark runner | Authors' MOA `2023.04.1-SNAPSHOT` fat jar, Java on `PATH`, and Python 3.9 as documented upstream. `exp/benchmark_moa.py` imports only the standard library. Conda is the authors' environment recipe. Git fetches the source and `unzip` extracts HyperA, DemandF and NZEnergy. The runner expects `moa.jar` and relative dataset/output paths under `exp/`. |
| Build the MOA jar | Full JDK with a compiler, Apache Maven 3 (3.9.11 exercised locally), the `moa/` and parent POM, and access to Maven Central or a populated Maven cache. The child POM sets Java source/target 1.8 and overrides the parent's default of 11. The paper used JDK 8. The documented build skips tests, Javadoc and LaTeX. Maven is needed for the build, while a staged fat jar only needs Java to launch. |
| E3 bias–variance | CapyMOA and its JVM bridge JPype1, the authors' MOA jar in place of CapyMOA's bundled jar, NumPy, SciPy (`scipy.io.arff`), scikit-learn and mlxtend. The wrapper imports CapyMOA's private `capymoa.stream._stream.NumpyStream` and Java classes via JPype. The upstream E3 README gives no version pins. Current PyPI metadata observed for CapyMOA 0.15.1 and mlxtend 0.25.0 requires Python >=3.11, so a fresh install of those versions cannot use the README's Python 3.9. Resolve a compatible set and record it before E3, then verify imports and the actual loaded jar before JVM startup-dependent work. |
| Summary, plots and optional data preparation | pandas, NumPy, openpyxl (explicit XLSX writer and pandas XLSX reader), Matplotlib and mplcursors. The NZEnergy preparation script also imports scikit-learn; the DemandF preparation script uses the standard library. The repository provides the prepared streams, including the zipped files. |

Direct dependencies declared for the MOA module, including versions inherited from the parent POM:

- Core, utilities and UI: Weka `weka-dev` 3.9.6, `sizeofag` 1.1.0, Guava 29.0-jre, `jclasslocator` 0.0.19, `jshell-scripting` 0.1.2, MEKA 1.9.7, Commons Math 3.6.1, OpenCSV 4.0, Commons CLI 1.4, Commons IO 2.7, JFreeChart 1.0.19, Gson 2.8.9, SSJ 3.3.2, JMathPlot 1.0.1 and JMathIO 1.0.
- Engine, logging and native dependencies: DJL API, model-zoo and PyTorch engine 0.9.0, DJL PyTorch native-auto 1.7.0 (runtime), SLF4J Log4j binding 1.7.26, and `ml.dmlc:xgboost4j_2.13:2.1.1` for Axgb. Maven resolves the transitive graph. Java bytecode targeting 1.8 alone does not establish compatibility of the bundled dependencies and JNI libraries with JDK 8 or Kaggle.
- Test-only: JUnit 4.13.1 and diffutils 1.2.1. Surefire is skipped by the authors' build flags. Class discovery executes Java on `PATH` during `process-classes`, so align `PATH` and `JAVA_HOME`. Maven Assembly produces the fat jar. The sibling Weka integration and Kafka modules are outside the documented `moa/` build.

Sources: [upstream README](https://github.com/nuwangunasekara/SGBR/blob/f62f7b4/README.md), [MOA module POM](https://github.com/nuwangunasekara/SGBR/blob/f62f7b4/moa/pom.xml), [parent POM](https://github.com/nuwangunasekara/SGBR/blob/f62f7b4/pom.xml), [E3 sources](https://github.com/nuwangunasekara/SGBR/tree/f62f7b4/exp/Bias_Variance_Decomp), [CapyMOA metadata](https://pypi.org/project/capymoa/), [mlxtend metadata](https://pypi.org/project/mlxtend/).

## Kaggle risks

| Constraint | Assessment |
| --- | --- |
| RAM and concurrency | The paper and `exp/exp_config.json` specify `-Xmx48g -Xms50m -Xss1g` for the main experiment. The other shipped configs use 12 GiB, and the paper reports that Sgb(Oza) fit in 12 GiB for E1. Reserve headroom for the JVM's native memory, thread stacks (up to 1 GiB per thread), the notebook kernel and the file cache. Determine the actual cgroup cap before scheduling any run. A smaller heap is neither proof of feasibility nor a change approved by this audit. |
| CPU, wall time and disk | The experiment plan's estimates of ~4 vCPU, ~30 GB RAM, ~12 hours per session and ~20 GB working storage are planning figures. Live quotas can vary. Capture CPU affinity, cgroup quota and memory, free space and the applicable session limit. Allow for checkout, compressed and extracted data, the Maven cache, jars and per-run outputs. A filesystem's reported total can exceed Kaggle's output quota. |
| Internet and offline use | Test GitHub, Maven Central and PyPI inside the notebook. A successful HTTPS request only verifies reachability at the sampled endpoint. A notebook with internet disabled needs staged, verified inputs, including the exact built jar and dataset archives. Use a writable workspace for builds and outputs. Kaggle Dataset inputs are normally read-only. |
| Java and native libraries | Check the notebook's reported architecture, JDK availability and Maven's selected JVM. Try JDK 8 first. Document the closest available newer JDK if needed and test the unchanged jar under that JDK. Axgb still needs a targeted check of XGBoost's JNI loading, architecture and native library dependencies. A Java or SGBR smoke test cannot validate Axgb. |
| Data availability | Upstream ships 13 of 16 streams. SUP2I, SUP3A and SUP3G require access from the authors. H-04 tracks that separately. |

See [experiment plan §7](experiment_plan.md#7-kaggle-compatibility-and-resource-requirements) and [Kaggle notebook documentation](https://www.kaggle.com/docs/notebooks).

## Proposed Kaggle smoke test

1. In a Kaggle **CPU** notebook, put this checkout under `/kaggle/working` and run from its root. Record the session maximum for that notebook from the Kaggle UI or applicable documentation and cite the source. Check what `java -version`, `javac -version` and `mvn -version` report before provisioning tools.
2. If needed, provision JDK 8 and Maven from trusted, verified artifacts. Set `JAVA_HOME` to the JDK directory and prepend its `bin` and Maven's `bin` to `PATH`. Use a verified newer JDK if 8 is unavailable and pass `--java-selection-note` with the reason and the version selected. In a notebook, set the environment for the same process or cell that runs the probe.
3. Run the probe, replacing the shell variables with the session limit and source recorded in step 1.

   ```bash
   python scripts/kaggle_environment_smoke.py \
     --session-limit-hours "$SESSION_LIMIT_HOURS" \
     --session-limit-source "$SESSION_LIMIT_SOURCE"
   ```

   The probe writes `results/manifest/environment.json`. It checks Java compilation and a launch marker, records Maven and tool versions, measures available resources, and captures endpoint outcomes. It reports host memory separately from cgroup v2 limits. For a notebook with v1 or a nonstandard mount, record the effective CPU and memory limits separately using the session's resolved cgroup paths. Review Maven's Java version, connectivity and the working storage quota before accepting the manifest. Keep the manifest as notebook output and attach the Kaggle evidence for C-01 review.

4. Once C-01 is accepted, C-02 owns the notebook build and Abalone parity check. The authors' build command, run from the pinned checkout's `moa/` directory, is:

   ```bash
   mvn clean install -DskipTests=true -Dmaven.javadoc.skip=true -Dlatex.skipBuild=true
   ```

   Expected artifact: `moa/target/moa-2023.04.1-SNAPSHOT-jar-with-dependencies.jar` relative to the upstream root.

## Executed checks

Checks in this section ran in Codex Cloud on 2026-11-19. Kaggle has not been probed.

- Cloned the authors' repository and verified its full commit SHA. Inspected the POMs, scripts and experiment configs at that revision.
- Ran the probe with `--local` under Python 3.12.14, OpenJDK 21.0.13 and Apache Maven 3.9.11. The local image had no standalone `javac` executable. The initial compiler check surfaced that, and the updated probe exercised Java 21 source-file mode, which compiled and printed `SGBR_JAVA_OK`. Git returned the expected HEAD and the Maven Central and PyPI probes returned HTTP 200. The local cgroup exposed a four-CPU quota and a 32 GiB memory cap, and local working disk free space was about 59 GiB. Those values describe Codex Cloud.
- The authors' Python launcher returned its help under Python 3.12.14. The probe also rejected an invocation outside Kaggle without `--local` and did not write a manifest for that invocation.
- Built the pinned MOA module with the authors' Maven goals and skip flags under OpenJDK 21.0.13 and Maven 3.9.11. Direct Maven dependency resolution failed on DNS in Codex Cloud. A temporary Maven settings file routed Maven through the existing cloud proxy and the build returned `BUILD SUCCESS`. Maven produced a 95,095,593-byte fat jar with SHA-256 `3f6e10b091387df94dbd9a773f69c1499aa0b6dae77ba65a3cd1d35ad24cbaf7`. The checkout, including build outputs, occupied about 440 MiB, and the separate Maven cache occupied about 465 MiB.
- Launched the resulting jar with OpenJDK 21, `-Xmx256m` and a 30-second timeout. `moa.DoTask` ran the Sgb(Oza) learner with seed 1 on a synthetic eight-row numeric ARFF. It exited successfully and its CSV had one row reporting eight processed instances. This check only exercised the CLI, learner construction and a tiny stream. It did not test Abalone parity, Axgb JNI, CapyMOA integration, JDK 8 or Kaggle execution.

## C-01 acceptance

C-01 remains Ready in [the task list](tasks.md). Its acceptance evidence is a real Kaggle `results/manifest/environment.json` with the Java version recorded, along with the requested resource and connectivity observations. The local manifest was written under `/tmp` and is not Kaggle evidence. No reproduction experiments were run.
