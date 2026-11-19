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
| Java and native libraries | Check the notebook's reported architecture, JDK availability and Maven's selected JVM. The pinned module failed to compile on JDK 8 because MEKA 1.9.7 contains Java 11 bytecode. The notebook defaults to JDK 11 and records the selected JVM and GC. Axgb still needs a targeted check of XGBoost's JNI loading, architecture and native library dependencies. A Java or SGBR smoke test cannot validate Axgb. |
| Data availability | Upstream ships 13 of 16 streams. SUP2I, SUP3A and SUP3G require access from the authors. H-04 tracks that separately. |

See [experiment plan §7](experiment_plan.md#7-kaggle-compatibility-and-resource-requirements) and [Kaggle notebook documentation](https://www.kaggle.com/docs/notebooks).

## Kaggle CPU notebook

Import [the C-01 notebook](../notebooks/c01_kaggle_cpu_smoke.ipynb), set Accelerator to **None**, and choose one project source in its configuration cell.

- **Automatic private GitHub checkout.** Leave `CHECKOUT` and `KAGGLE_DATASET_ROOT` unset. Enable Kaggle Internet and grant the notebook access to the Kaggle Secret `GITHUB_TOKEN`. Use a fine-grained GitHub token scoped to `AIVIETNAM-AIO-DucTam/SGBR-Reproduction` with **Contents: Read**. Set `GITHUB_REF` to a branch name or a full 40-character SHA. The notebook creates a shallow checkout at `/kaggle/working/SGBR-Reproduction`. It reuses a matching clean checkout without reading the secret again. Set `GITHUB_REFRESH = True` to fetch the branch again. Use an explicit `CHECKOUT` if you intend to use local edits.
- **Private Kaggle Dataset.** From an authorized local copy of the project, upload `scripts/kaggle_environment_smoke.py` to a private Kaggle Dataset, keeping the `scripts/` directory. Attach it with **Add Input**. Set `KAGGLE_DATASET_ROOT` to the mounted directory immediately above `scripts/`, as shown in the notebook's file pane. Leave `CHECKOUT` unset. The notebook can read the helper from the Dataset's read-only mount.
- **Existing local checkout.** Set `CHECKOUT` to a checkout already available to the notebook and leave `KAGGLE_DATASET_ROOT` unset.

Use the notebook and helper from the same project revision. A missing or unreadable helper stops initialization with the expected path and setup instructions. The authenticated project fetch uses a temporary Git askpass helper. The remote URL contains no credentials, and the notebook does not replay Git diagnostics from that fetch. The manifest records the resolved `project_git_commit` when Git metadata is available. The authors' public MOA revision is recorded separately; a Dataset without Git metadata has a null project SHA.

Fill in the session limit and its source, the execution mode, and the Kaggle image version if available. The notebook writes `/kaggle/working/results/manifest/environment.json` even when a provisioning, build or smoke step fails after initialization.

- **Online build.** Enable Internet. The notebook checks the published hashes for Temurin JDK 11.0.29+7 and Maven 3.9.11, fetches the exact upstream SHA, builds the `moa/` module with the authors' Maven goals and skip flags, and records the resulting jar SHA-256 and build JDK.
- **Staged jar.** Attach the trusted fat jar from the pinned fork and provide its recorded SHA-256 and build JDK. Use the staged Temurin 11 archive or point to a verified installed JDK. The probe records Maven presence, but the staged jar does not require Maven. Build a jar with the JDK you plan to run, or verify the staged jar explicitly on that JDK.
- **Evidence.** The probe records initial and selected tool versions, CPU model and sampled frequency, affinity, visible v1/v2 cgroup limits, the JVM's processor/heap view and GC flags, disk space, and GitHub/Maven Central/PyPI reachability. The smoke runs Sgb(Oza) with seed 1 and requires exactly eight processed instances in the MOA CSV. The 256 MiB heap applies only to this tiny environment check.

The notebook prints observed compatibility issues and saves them in the manifest. A staged jar can pass even when internet probes fail. Host memory and filesystem capacity do not establish a Kaggle session quota. The working-space quota and session limit should be reviewed against the Kaggle UI. C-02 covers Abalone parity separately.

## Executed checks

Checks in this section ran in Codex Cloud on 2026-11-19. Kaggle has not been probed.

- Cloned the authors' repository and verified its full commit SHA. Inspected the POMs, scripts and experiment configs at that revision.
- Ran the probe with `--local` under Python 3.12.14, OpenJDK 21.0.13 and Apache Maven 3.9.11. The local image had no standalone `javac` executable. The initial compiler check surfaced that, and the updated probe exercised Java 21 source-file mode, which compiled and printed `SGBR_JAVA_OK`. Git returned the expected HEAD and the Maven Central and PyPI probes returned HTTP 200. The local cgroup exposed a four-CPU quota and a 32 GiB memory cap, and local working disk free space was about 59 GiB. Those values describe Codex Cloud.
- The authors' Python launcher returned its help under Python 3.12.14. The probe also rejected an invocation outside Kaggle without `--local` and did not write a manifest for that invocation.
- Built the pinned MOA module with the authors' Maven goals and skip flags under OpenJDK 21.0.13 and Maven 3.9.11. Direct Maven dependency resolution failed on DNS in Codex Cloud. A temporary Maven settings file routed Maven through the existing cloud proxy and the build returned `BUILD SUCCESS`. Maven produced a 95,095,593-byte fat jar with SHA-256 `3f6e10b091387df94dbd9a773f69c1499aa0b6dae77ba65a3cd1d35ad24cbaf7`. The checkout, including build outputs, occupied about 440 MiB, and the separate Maven cache occupied about 465 MiB.
- Launched the resulting jar with OpenJDK 21, `-Xmx256m` and a 30-second timeout. `moa.DoTask` ran the Sgb(Oza) learner with seed 1 on a synthetic eight-row numeric ARFF. It exited successfully and its CSV had one row reporting eight processed instances. This check only exercised the CLI, learner construction and a tiny stream. It did not test Abalone parity, Axgb JNI, CapyMOA integration, JDK 8 or Kaggle execution.

### Notebook validation in Codex Cloud

- The pinned Maven build failed with Temurin 8u472. The module imports `meka.core.F`, whose MEKA 1.9.7 class has bytecode version 55 (Java 11). JDK 8 accepts class files through version 52.
- The notebook's online build path verified the Temurin 11 and Maven downloads, fetched the exact upstream commit, built the MOA jar with Temurin 11.0.29+7 and Maven 3.9.11, and processed all eight rows. This local run used the cloud Maven proxy and an existing dependency cache.
- The staged-jar path processed eight rows with the separately built Java 21 jar and Maven absent. An incorrect jar checksum failed and was recorded in its manifest. The live local cgroup v2 and a synthetic v1 fixture exercised resource detection.

## C-01 acceptance

C-01 remains In progress in [the task list](tasks.md). Its acceptance evidence is a real Kaggle `results/manifest/environment.json` with the Java version recorded, along with the requested resource and connectivity observations. Commit the manifest from the successful Kaggle run for review. Local validation manifests were written under `/tmp`. No reproduction experiments were run.
