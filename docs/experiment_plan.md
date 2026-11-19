# SGBR Experiment Plan (Kaggle Reproduction)

Companion to `docs/paper_spec.md`. Uses the same tags:
**[P p.N]** = paper fact (journal page N of 37); **[INF]** = inference; **[ASSUME]** = assumption to confirm; **[EXT]** = external or general knowledge to verify; **[ADAPT]** = a Kaggle adaptation proposed here, which is **not** part of the original methodology and needs human approval (task H-01). Q-nn refers to `docs/tasks.md` §Open Questions.

---

## 1. Experimental objectives

The paper runs three experiment families **[P p.11, §4]**. Table 1 and Fig. 6 are reported separately. This plan gives each one an ID:

| ID | Objective | Paper artefacts | Priority |
|---|---|---|---|
| **E0** | Motivation: vanilla Sgbt (100 FIRT-DD steps) vs single-tree regressors | Tab.1 (p.7) | Low |
| **E1** | Main comparison: 5 SGBR variants vs 8 baselines; R̄² and wall time; average rank; Shaffer post-hoc test | Tabs.3, 4, 8, 9 (pp.15, 17, 25–28); Figs.4, 5 (p.18) | **High** |
| **E2** | Behaviour over time on HyperA (abrupt drifts): windowed R̄² and wall time | Fig.6 (p.18) | Medium |
| **E3** | Bias–variance decomposition vs boosting iterations for Sgbt, Sgb(Oza), Oza(Sgbt) | Figs.2, 7, 8 (pp.9, 19, 20) | Medium |
| **E4** | Learning rate × feature % for Sgb(Oza)(10,10) | Fig.9 (p.20) | Medium |
| **E5** | Boosting steps × bag size (product 100) for Sgb(Oza) | Tabs.5, 6, 10, 11; Fig.10 (pp.21–23, 29–30) | Medium |
| **E6** | Best Sgb(Oza) configs (5,20), (10,10) vs SOKNL, OzaReg, ArfReg | Tabs.7, 12 (pp.24, 31–32) | Low (mostly reuses E1/E5) |

**Claims to test** (each must be judged reproduced / partly reproduced / not reproduced):

| ID | Claim | Source |
|---|---|---|
| C1 | Vanilla Sgbt has the worst predictive performance among ensembles (avg R̄² 0.32, avgRank 11.9) | **[P p.14, Tab.3]** |
| C2 | Each SGB(Bag) variant beats its bagging counterpart: Sgb(Oza) > OzaReg, Sgb(Arf) > ArfReg, Sgb(Srp) > SrpReg (avg R̄²) | **[P p.14]** |
| C3 | Sgb(Oza) and Oza(Sgbt) significantly beat SOKNL on R̄² (Shaffer, p = 0.05); no significant difference between the two | **[P p.16, Fig.4]** |
| C4 | Sgb(Oza) is significantly faster than Oza(Sgbt) and SOKNL | **[P p.16, Fig.5]** |
| C5 | Bag(Sgbt) ≈ SGB(Bag) on accuracy but costs more | **[P p.14–16, Tabs.3–4]** |
| C6 | Sgbt variance grows with boosting iterations at roughly constant bias; Sgb(Oza) has lower variance; Oza(Sgbt) lowest | **[P p.19, Figs.7–8]** |
| C7 | lr = 1.0 is consistently strong; lr 1.0 + 75 % features is the best accuracy/cost balance | **[P p.21, Fig.9]** |
| C8 | (10,10) and (5,20) are the best (S, E) splits; (100,1) collapses (avg R̄² 0.10) | **[P p.21, p.33, Tab.5]** |
| C9 | Sgb(Oza) runs about 2× faster than SOKNL with higher avg R̄² | **[P p.33, Tab.7]** |
| C10 | Sgb(Oza) is hit less around drift points on HyperA | **[P p.16, Fig.6]** |

## 2. Datasets and availability

### 2.1 Dataset table (paper facts from Tab.2, p.13; descriptions pp.11–12)

| Dataset | # features | # instances | Type | Drift | Paper description / origin | In which experiments |
|---|---|---|---|---|---|---|
| Ailerons | 40 | 13,750 | Synthetic | – | F16 aileron control | E0, E1, E3, E4, E5 |
| Elevators | 18 | 16,599 | Synthetic | – | F16 elevator control | E0, E1, E3, E4, E5 |
| Fried | 10 | 40,768 | Synthetic | – | Friedman (1991), 5 irrelevant features | E0, E1, E3, E4, E5 |
| HyperA | 10 | 500,000 | Synthetic | 3 abrupt (125k, 250k, 375k; width 1) | CapyMOA HyperPlaneRegression + DriftStream (fn.1, p.12) | E0, E1, E2, E4, E5 |
| FriedmanLea | 10 | 100,000 | Synthetic | local expanding abrupt at 25k, 50k, 75k | River FriedmanDrift (fn.2, p.12) | E0, E1, E3, E4, E5 |
| FriedmanGra | 10 | 100,000 | Synthetic | global recurring abrupt at 35k, 75k | River FriedmanDrift | E0, E1, E3, E4, E5 |
| FriedmanGsg | 10 | 100,000 | Synthetic | global slow gradual at 35k, 75k | River FriedmanDrift | E0, E1, E3, E4, E5 |
| SUP2I | 80 | 100,000 | Synthetic (GAN) | 2 incremental, width 20k | Sun et al. 2025 | E1 |
| SUP3A | 81 | 200,000 | Synthetic (GAN) | 4 × 50k concepts, abrupt | Sun et al. 2025 | E1 |
| SUP3G | 81 | 200,000 | Synthetic (GAN) | 4 × 50k concepts, 10k gradual | Sun et al. 2025 | E1 |
| Abalone | 8 | 4,977 | Real | – | UCI (Nash et al. 1995) | E0, E1, E3, E4, E5 |
| Bike | 12 | 17,379 | Real | – | Fanaee-T & Gama 2014 (hourly) | E0, E1, E3, E4, E5 |
| House8L | 8 | 22,784 | Real | – | 1990 US census | E0, E1, E3, E4, E5 |
| MetroTraffic | 7 | 48,204 | Real | – | traffic volume from weather | E0, E1, E3, E4, E5 |
| DemandF | 8 | 150,150 | Real | seasonal recurrent (possible) | Kaggle "Demand Forecasting" (paper ref., accessed 31-10-2024) | E1 |
| NZEnergy | 12 | 3,100,660 | Real | seasonal recurrent | Sun et al. 2024; NZ energy prices, 1/11/2022–15/10/2024 | E1 |

Dataset subsets used in the paper:
- **"Core-11"** = first 11 rows (no SUP*, DemandF, NZEnergy). Used for Tab.1 and E4/E5/E6 **[P Fig.9, Fig.10 captions; Tabs.1, 5–7]**.
- **"BV-10"** = Core-11 minus HyperA. Used for E3 **[P p.16]**.
- **"All-16"**: used for Tabs.3–4 **[P pp.15, 17]**.

### 2.2 Availability

**Repo check (R-03, commit `f62f7b4`; details in `paper_spec.md` §11.6):** 13 of 16 datasets are in `exp/RDatasets/`; HyperA, DemandF and NZEnergy are zipped. **SUP2I, SUP3A and SUP3G are not included** (README: "contact authors") → Q-30. Row and attribute counts match Tab.2, with small differences for NZEnergy (MOA classified 3,100,666 vs 3,100,660). Abalone's 4,977 rows are the repo file's real count (Q-02 resolved).

| Source | Status |
|---|---|
| Authors' repo `github.com/nuwangunasekara/SGBR` | **Primary source, verified** for 13 datasets (as above). |
| Ailerons, Elevators, Fried, House8L, Abalone, Bike, MetroTraffic | Also public via UCI / OpenML / Torgo's regression collection **[EXT]**. Use only if the repo files are missing, and check counts against Tab.2. |
| HyperA, FriedmanLea/Gra/Gsg | Can be regenerated with CapyMOA / River **[P fn.1–2]**. Generator parameters and seeds are **not** in the paper (Q-19), so prefer the repo files. |
| SUP2I/3A/3G | From Sun et al. 2025 (arXiv 2502.07213) **[P p.12]**; repo copy preferred. |
| DemandF | Kaggle dataset `aswathrao/demand-forecasting` **[P reference list, p.36]**. The streaming conversion (feature set, order) is from Gunasekara et al. 2025, not described here → use the repo copy. |
| NZEnergy | Sun et al. 2024 **[P p.12]**; repo copy preferred. |

**Known data issues to check during acquisition:** Q-02 (Abalone count 4,977 vs the usual 4,177 **[EXT]**), Q-03 (HyperA values differ between Tab.1 and Tab.3), Q-14 (nominal attributes and target column).

**[ADAPT] Kaggle packaging:** upload the verified files as one private Kaggle Dataset (`sgbr-streams`). Store SHA-256 checksums, instance counts and feature counts in a manifest, and fail fast if any count differs from Tab.2 (unless the human approves an explained deviation).

## 3. Evaluation metrics and formulas

| Metric | Formula | Where | Source |
|---|---|---|---|
| R² | $1 - \sum_i (m(x_i)-y_i)^2 / \sum_i (y_i-\bar y)^2$ | basis of R̄² | **[P p.14]** |
| **Adjusted R²** (R̄²) | $1 - (1-R^2)\frac{n-1}{n-p-1}$; n = sample size, p = input dimensions | primary accuracy metric | **[P p.14]** |
| Cumulative R̄² | R̄² over all prequential predictions at stream end | Tabs.1, 3, 5, 7 | **[P p.14]** |
| Windowed R̄² | R̄² over the last 10k predictions | Fig.6 | **[P p.14; Fig.6 caption]**; definition of n in window (Q-21) |
| Wall time | final test-then-train wall time (s) | Tabs.4, 6, 7 | **[P p.14]**; measurement scope (Q-18) |
| Average rank | per dataset, rank methods by mean metric (1 = best R̄² / fastest); average over datasets | all tables | **[P tables "avgRank"]**; tie handling **[ASSUME]** average ranks |
| Friedman + Shaffer post-hoc | α = 0.05 on per-dataset ranks | Figs.4, 5 | **[P p.16]**; inputs and software (Q-22) |
| Bias², variance (MSE) | mlxtend `bias_variance_decomp(loss='mse')`; for test point x over rounds r: $\text{bias}=(\bar{\hat y}(x)-y)^2$, $\text{var}=\overline{(\hat y_r(x)-\bar{\hat y}(x))^2}$, averaged over the test set **[EXT mlxtend docs]**; plotted as √bias, √variance | Figs.2, 7, 8 | **[P p.16, p.34]** |

Reporting: mean ± std over seeds (as in Tabs.8–12) **[P]**.

**MOA's R̄² is what the paper reports, and it differs from Eq.U-8 [CODE; `paper_spec.md` K-5, K-6]:**
- SS_tot uses the **running mean of targets seen before** each instance (0 for the first), not the global mean.
- p = number of attributes **including the target**.
- n = instances evaluated (weight 1 each).
- Windowed version: same, over the last 10,000 instances.

Any evaluator Codex writes must reproduce MOA's definition exactly (unit test against a MOA output CSV). It may also report the textbook Eq.U-8 value in a separate, clearly labelled column [ADAPT].

## 4. Baseline algorithms

| Baseline | Configuration | Source | Kaggle availability [EXT / to verify, C-01] |
|---|---|---|---|
| OzaReg | 100 FIRT-DD members [INF], mean aggregation | **[P p.10, p.13–14]** | MOA via authors' repo |
| ArfReg | MOA default: 100 FIRT-DD, VarianceReduction, GP 50, SC 0.01 | **[P p.13]** | MOA / CapyMOA |
| SOKNL | MOA default (same tree settings, 100 trees) | **[P p.13]** | MOA / CapyMOA |
| SrpReg | 100 members [INF] | **[P p.13]** | MOA / CapyMOA |
| Sgbt | 100 boosting steps of FIRT-DD; lr / feat % not stated (Q-15) | **[P Tab.1]** | MOA via authors' repo |
| Axgb | 10 boosting iterations × XGBoost(10 trees), lr 0.3, depth 6, window 1000/1, no drift detection, "replace" | **[P p.13]** | Implementation unknown (Q-16) |
| FIRT-DD | VarianceReduction, GP 50, SC 0.01 | **[P p.13]** | MOA |
| HTR | GP 50, SC 0.01 | **[P p.13–14]** | MOA |
| SGT (E0 only) | default from Gouk et al. 2019 | **[P Tab.1]** | MOA (to verify) |

SGBR variants under test: Sgb(Oza), Sgb(Arf), Sgb(Srp), Oza(Sgbt), Srp(Sgbt) with S = 10, E = 10, lr = 1.0, feat = 75 %, FIRT-DD as above **[P p.13]**.

**Use the exact MOA command strings in `paper_spec.md` §11.1** (from `exp/exp_config.json`); they are the ground truth for every method above. Known code-vs-paper differences that the reproduction keeps, as the code does, and flags in the report:
- HTR runs with grace 200 / confidence 1e-7 (K-4).
- ArfReg/SrpReg/SOKNL use their own 60 % feature subsets with λ = 6 (§11.2).
- Axgb is `meta.AdaptiveXGBoostClassifier -s 10` with no seed (Q-16 resolved).
- Baselines ignore nominal attributes while Sgbt-based models one-hot encode them (K-10).

## 5. Hyperparameter configurations

### 5.1 E1 / E2 (main)
As in `paper_spec.md` §8.1. All values are **[P p.13]**; unknowns are listed there (Q-09 – Q-11, Q-15).

### 5.2 E4 grid
lr ∈ {0.5, 1.0, 1.5} × feat ∈ {0.25, 0.75, 1.00}; Sgb(Oza) S = 10, E = 10; Core-11; 5 seeds **[P p.19–21]**.

Reference values (read from Fig.9 plot, average mean R̄²):

| lr \ feat | 25 % | 75 % | 100 % |
|---|---|---|---|
| 0.5 | −6.69 | −6.91 | −6.99 |
| 1.0 | 0.65 | 0.74 | 0.74 |
| 1.5 | −0.30 | −0.17 | −0.16 |

Wall time (avg, read from plot, approximate): about 27 s at 25 %, 54–57 s at 75 %, 65–71 s at 100 %.

### 5.3 E5 grid
(S, E) ∈ {(1,100), (2,50), (4,25), (5,20), (10,10), (20,5), (25,4), (50,2), (100,1)}; lr 1.0, feat 75 %; Core-11; 5 seeds **[P p.21, Tabs.5–6]**.

### 5.4 E3 grid
Boosting iterations 5, 10, …, 100 **[P Fig.2; CODE BVDecompSyntheticLatest.py:96]**; methods Sgbt, Sgb(Oza), Oza(Sgbt).

Code-confirmed protocol [CODE exp/Bias_Variance_Decomp/]:
- Bag size **E = 5** (`OzaBag -s 5`), not 10.
- 10-fold `KFold` without shuffling.
- Per fold: `mlxtend.bias_variance_decomp(loss='mse', num_rounds=10, random_seed=42)` on CapyMOA-wrapped MOA learners trained incrementally.
- Fold-averaged bias and variance, then square-rooted.
- Friedman* drift datasets use pre-generated split files `<name>_1…_10` (train) and `<name>_12` (test). **These files are not in the repo** (Q-31).
- Authors' raw curves are in `exp/Bias_Variance_Decomp/RESULTS/` and serve as targets.

## 6. Random seeds and repetition protocol

| Experiment | Seeds | Repetitions | Source |
|---|---|---|---|
| E1 (Tabs.3–4, Figs.4–5) | 1, 2, 3, 4, 5 | 5 | **[P p.34 item 1]** |
| E5, E6 (Tabs.5–7, Fig.10) | 1, 2, 3, 4, 5 | 5 | **[P p.34 item 2]** |
| E4 (Fig.9) | "five times with different random seeds", values not listed | 5 | **[P p.21]**; **[ASSUME]** 1–5 |
| E2 (Fig.6) | 1, 2, 3 | 3 | **[P p.34 item 3]** |
| E3 | 10 iterations per split; seeds for the 11 scaled-down drift datasets not given | – | **[P p.16]**; Q-19, Q-20 |
| E0 (Tab.1) | not stated | – | **[ASSUME]** same as E1 (values coincide with Tab.3 except HyperA) |

Protocol:
1. Each (experiment, method, dataset, seed) is one independent process. The authors' runner already works this way, sequentially [CODE exp/benchmark_moa.py]; we run the processes in parallel [ADAPT], so a crash costs only one cell.
2. As in the authors' runner, `-Z <seed>` is appended **only to the outermost learner**. FIRT-DD, HTR and Axgb get no seed [CODE; `paper_spec.md` K-9]. Stream order is never shuffled.
3. All E1–E6 streams are the fixed repo ARFF files, identical across seeds [CODE].
3a. **One-run rule (H-01(f), approved) [ADAPT]:** learners that the authors' runner gives no seed (Axgb, FIRT-DD, HTR) run once per dataset. That result stands for all 5 seeds, with std 0, matching the zero stds in Tabs.8–9. C-07 checks determinism before this is relied on.
4. Log per run: seed, Java version, MOA/CapyMOA version, authors' repo commit hash, CPU model, wall time, peak RSS, exit status.
5. Deterministic learners (FIRT-DD, HTR) should show std ≈ 0, as in Tabs.8–9 **[P]**. This is a sanity check of seed handling.

## 7. Kaggle compatibility and resource requirements

### 7.1 Original environment **[P p.34]**
- MOA (Java), JDK 1.8.0, JVM `-Xms50m -Xss1g`, heap `-Xmx48g` for E1 (`-Xmx12g` sufficed for Sgb(Oza)), `-Xmx12g` elsewhere.
- E1: Ubuntu 24.04.2, Intel Xeon 20-core 3.7 GHz, 62–125 GB RAM. E5/E6: Windows, Ryzen 7 3700X, 16 GB. E2: MacBook Pro i7 2.6 GHz, 16 GB. E3: Ubuntu 18.04, AMD EPYC 7702 64-core, 1000 GB RAM.

### 7.2 Kaggle environment **[EXT — verify in C-01]**
Commonly documented limits: CPU session about 4 vCPU and about 30 GB RAM; about 12 h maximum per session; about 20 GB persistent `/kaggle/working`; internet must be switched on to install packages or clone GitHub. A JDK may not be pre-installed. All values must be measured in task C-01 before scheduling.

### 7.3 Execution options [ADAPT] (human decision H-01)

> **Decision (H-01, 2026-11-19): option K-A approved.** Build the MOA jar at commit `f62f7b4` and run the authors' exact commands. Use CapyMOA (with the repo jar swapped in) only for E3. Where code and paper conflict, follow the code and report the conflict (`tasks.md` Decisions log).

| Option | Description | Fidelity | Risk |
|---|---|---|---|
| **K-A (recommended)** | Install a JDK in the notebook. Build the repo's `moa/` module at commit `f62f7b4` with Maven (`mvn clean install -DskipTests=true -Dmaven.javadoc.skip=true -Dlatex.skipBuild=true` → `moa-2023.04.1-SNAPSHOT-jar-with-dependencies.jar` [CODE README]). Run the exact `moa.DoTask` commands (§11.1 of spec) via subprocess; parse MOA CSV output. Building once offline and uploading the jar as a Kaggle Dataset avoids rebuilding every session | Highest: same code and commands as the paper | Java/Maven on Kaggle; module targets Java 1.8 (paper used JDK 1.8.0); Axgb needs native xgboost4j 2.1.1 libs |
| K-B | CapyMOA (Python API over MOA). **Required for E3 anyway [P p.34]**; the authors swap CapyMOA's bundled `moa.jar` for theirs [CODE exp/Bias_Variance_Decomp/README.md] | High **only** with the repo jar swapped in | Upstream MOA/CapyMOA SGBR (added Aug–Sep 2025) may differ from `f62f7b4` (Q-32) |
| K-C | Pure-Python re-implementation (e.g. River-based) by Codex | Low; FIRT-DD/OzaReg/SOKNL internals differ | Results not comparable. Use only for unit-level understanding, always labelled "re-implementation" |

### 7.4 Compute budget (derived from Tab.4 single-run wall times on the authors' E1 hardware) [INF]

Sum over datasets of per-run wall time × 5 seeds. Kaggle CPUs may be slower; apply a slowdown factor measured in C-07.

| Method | Core-10* (h) | All-16 (h) |
|---|---|---|
| Sgb(Oza) | 0.45 | 10.6 |
| Oza(Sgbt) | 0.97 | ≈ 29 |
| Srp(Sgbt) | 1.9 | ≈ 58 |
| Sgb(Arf) | 0.63 | ≈ 19 |
| Sgb(Srp) | 0.69 | ≈ 38 |
| Sgbt | 0.80 | ≈ 24 |
| OzaReg | 0.37 | ≈ 7.5 |
| ArfReg | 0.61 | ≈ 14 |
| SOKNL | 1.0 | ≈ 20 |
| SrpReg | 0.55 | ≈ 11 |
| FIRT-DD + HTR | 0.03 | 0.4 |
| **Subtotal (no Axgb)** | **≈ 8.0** | **≈ 232** |
| Axgb | (≈ 14.5; ≈ 2.9 with one run, as approved) | ≈ 244 (not planned) |

\*Core-10 = Core-11 minus HyperA (fastest meaningful subset). All-16 numbers use the rounded "avg" column (e.g. 1.3e+03) × 16 × 5 and are approximate. **NZEnergy alone is ≈ 50 % of the All-16 cost.**

Other experiments (approximate):
- **E5:** Tab.6 avgs × 11 datasets × 9 configs × 5 seeds ≈ **7.2 h** (Windows Ryzen hardware).
- **E4:** ≈ 6.8 h, using plot-read wall times.
- **E2:** (Sgb(Oza) + SOKNL + OzaReg + ArfReg on HyperA) × 3 seeds ≈ **2.3 h**.
- **E3:** unknown; it ran on a 64-core / 1 TB machine and is likely the most expensive per point.

**Memory risk:** the paper needed a 48 GB heap for non-Sgb(Oza) methods in E1 **[P p.34]**, which is more than Kaggle RAM **[EXT]**. Run large datasets (NZEnergy, SUP*, HyperA, DemandF) one process at a time with the heap capped below session RAM. Record any OOM as "not run", **never as a result**.

**Parallelism [ADAPT]:** run up to (vCPU count) single-run processes at once, keeping total heap under the RAM limit. Make each notebook resumable: skip cells whose output CSV already exists, and write output after every run.

## 8. Minimal reproduction strategy

Goal: test the headline claims (C1, C2-Oza, C3, C4, C6 on one dataset) within about 1–2 Kaggle sessions.

> **Approved scope (H-01(e), 2026-11-19): T0 + T1 + T1b + T1c.** With the one-run rule, T1 has 320 runs: 6 seeded methods × 10 datasets × 5 seeds, plus FIRT-DD and HTR × 10 datasets × 1 run.

| Tier | Scope | Est. cost (paper hw) |
|---|---|---|
| **T0 – smoke** | Sgb(Oza), OzaReg, FIRT-DD on Abalone, seed 1; also check that cumulative R̄² is computed exactly as Eq.U-9 by recomputing from saved predictions | minutes |
| **T1 – minimal E1** | Methods {Sgb(Oza), Oza(Sgbt), Sgbt, OzaReg, ArfReg, SOKNL, FIRT-DD, HTR} × Core-10 × seeds 1–5 | ≈ 4.2 h |
| **T1b – minimal E3** | Fig.2 only: Sgbt bias/variance on Ailerons for iterations {5, 10, 25, 50, 100} (subset of the paper's 5…100 grid) [ADAPT], using the code protocol (§5.4). Target: `BVDecompose_Results_ailerons.csv` rows, method "B" | to be measured |
| **T1c – minimal E5** | Sgb(Oza) (S, E) ∈ {(1,100), (10,10), (5,20), (100,1)} × Core-10 × seed 1–5 [ADAPT subset] | ≈ 1.6 h (Tab.6 hardware) |

Success for the minimal tier: §10 criteria applied to the T1 subset. In particular, Sgb(Oza) avgRank < SOKNL avgRank, Sgbt is last among ensembles, and the Ailerons Sgbt √variance rises with iterations while √bias stays flat.

## 9. Full reproduction strategy

> **Approved scope (H-01(d), (f), 2026-11-19):**
> - "Full" means the **13 datasets in the authors' repo**; SUP\* only if obtained (H-04).
> - **Axgb runs once per dataset on Core-10 only**, so step 3 below is replaced by about 2.9 h at paper speed instead of about 244 h.

Do these in order, and stop to review (R-07) after each step:

1. **E1-core:** all 13 methods (no Axgb) × Core-11 (adds HyperA) × 5 seeds.
2. **E1-large:** same methods on DemandF, SUP2I, SUP3A, SUP3G (**SUP\* only if obtained from the authors / Sun et al. 2025, Q-30**; otherwise report "not run – data unavailable"); then NZEnergy last (≈ 116 h alone at paper speed; split across sessions by method/seed).
3. **Axgb:** only after Q-16 is resolved. Core-11 first; large datasets optional (paper shows divergence: R̄² −7.7e+28 on NZEnergy).
4. **E4, E5** full grids on Core-11.
5. **E6:** assemble from E1 + E5 (re-run baselines only if the hardware differs, since wall time must come from one machine; Q-27).
6. **E2:** HyperA periodic, 3 seeds, window 10k.
7. **E3:** BV-10 with CapyMOA + mlxtend, after Q-17/Q-20 are resolved.
8. **Stats:** Friedman + Shaffer (α = 0.05) on E1 R̄² and wall time for {Oza(Sgbt), Sgb(Oza), Sgb(Arf), SOKNL, OzaReg, ArfReg} (methods shown in Fig.4). [ADAPT] Python has no standard Shaffer implementation; use R `scmamp` (if available) or a reviewed implementation with unit tests.
9. **E0:** reuse E1 FIRT-DD/HTR/Sgbt on Core-11; run SGT only if available.

## 10. Expected outputs and validation criteria

### 10.1 Output artefacts (spec for Codex)

```
results/
  manifest/environment.json            # java, moa/capymoa versions, repo commit, cpu, ram
  manifest/datasets.csv                # name, file, sha256, n_instances, n_features
  raw/<EXP>/<dataset>/<method>/seed=<k>.csv     # periodic rows: instances_seen, cum_adj_r2, win_adj_r2, wall_time_s
  raw/<EXP>/<dataset>/<method>/seed=<k>.json    # final: cum_adj_r2, wall_time_s, peak_mem, status
  summary/<EXP>_r2.csv  summary/<EXP>_time.csv   # mean, std, n_seeds, paper_mean, paper_std, delta, verdict
  figures/fig2.png fig4.png fig5.png fig6.png fig7.png fig8.png fig9.png fig10.png
```

### 10.2 Reference targets (paper Tab.3, R̄², mean over 5 seeds) **[P p.15]**

| Method | fried | House8L | abalone | bike | elevators | MetroTraffic | ailerons | FrLea | FrGra | FrGsg | hyperA | DemandF | NZEnergy | SUP2I | SUP3A | SUP3G | avg | avgRank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Oza(Sgbt) | 0.89 | 0.60 | 0.46 | 0.93 | 0.70 | 0.24 | 0.76 | 0.88 | 0.88 | 0.88 | 0.88 | 0.63 | 0.97 | 0.58 | 0.58 | 0.58 | 0.72 | 2.2 |
| Srp(Sgbt) | 0.67 | 0.56 | 0.49 | 0.85 | 0.73 | 0.36 | 0.76 | 0.63 | 0.64 | 0.66 | 0.69 | 0.55 | 0.98 | 0.57 | 0.57 | 0.57 | 0.64 | 4.5 |
| Sgb(Oza) | 0.89 | 0.58 | 0.48 | 0.93 | 0.71 | 0.28 | 0.75 | 0.88 | 0.88 | 0.87 | 0.87 | 0.66 | 0.98 | 0.57 | 0.58 | 0.57 | 0.72 | 2.4 |
| Sgb(Arf) | 0.72 | 0.55 | 0.53 | 0.81 | 0.52 | 0.51 | 0.68 | 0.73 | 0.71 | 0.69 | 0.63 | 0.57 | 0.98 | 0.55 | 0.56 | 0.56 | 0.65 | 5.1 |
| Sgb(Srp) | 0.67 | 0.55 | 0.48 | 0.79 | 0.51 | 0.31 | 0.66 | 0.63 | 0.60 | 0.60 | 0.49 | 0.60 | 0.97 | 0.54 | 0.56 | 0.55 | 0.59 | 6.9 |
| Sgbt | 0.46 | 0.18 | 0.08 | 0.80 | 0.19 | −0.05 | 0.38 | 0.49 | 0.42 | 0.42 | 0.27 | 0.29 | 0.95 | 0.11 | 0.09 | 0.10 | 0.32 | 11.9 |
| Axgb | 0.80 | −0.53 | −0.12 | 0.84 | 0.38 | −0.84 | 0.61 | 0.73 | 0.70 | 0.68 | 0.70 | −0.73 | −7.7e+28 | −4.16 | −19.07 | −22.33 | −4.8e+27 | 9.4 |
| OzaReg | 0.82 | 0.54 | 0.37 | 0.82 | 0.53 | 0.15 | 0.62 | 0.81 | 0.79 | 0.79 | 0.82 | 0.49 | 0.81 | 0.55 | 0.57 | 0.57 | 0.63 | 5.8 |
| ArfReg | 0.65 | 0.54 | 0.48 | 0.74 | 0.39 | 0.26 | 0.55 | 0.67 | 0.65 | 0.64 | 0.61 | 0.51 | 0.96 | 0.54 | 0.57 | 0.56 | 0.58 | 7.6 |
| SOKNL | 0.82 | 0.58 | 0.58 | 0.80 | 0.46 | 0.31 | 0.56 | 0.81 | 0.81 | 0.80 | 0.86 | 0.53 | 0.96 | 0.55 | 0.58 | 0.57 | 0.66 | 4.4 |
| SrpReg | 0.53 | 0.52 | 0.45 | 0.72 | 0.37 | 0.21 | 0.57 | 0.52 | 0.49 | 0.49 | 0.43 | 0.52 | 0.96 | 0.54 | 0.57 | 0.56 | 0.53 | 9.3 |
| FIRT-DD | 0.60 | 0.46 | 0.16 | 0.75 | 0.24 | 0.00 | 0.46 | 0.63 | 0.57 | 0.58 | 0.47 | 0.36 | 0.74 | 0.48 | 0.49 | 0.50 | 0.47 | 10.4 |
| HTR | 0.65 | 0.36 | 0.14 | 0.56 | 0.25 | 0.04 | 0.44 | 0.64 | 0.47 | 0.42 | 0.35 | 0.29 | 0.62 | 0.42 | 0.44 | 0.44 | 0.41 | 11.2 |

**Preferred targets for 6 methods:** the authors' raw per-seed final rows in `exp/post_hoc_new/<dataset>_<seed>/<method>.csv` (Oza(Sgbt), Sgb(Oza), Sgb(Arf), OzaReg, ArfReg, SOKNL × 16 datasets × seeds 1–5) [CODE]. They agree with the table above after rounding and allow **per-seed** comparison. With identical code, data and seeds, R̄² should match to ~1e-6 apart from multi-threading non-determinism (Q-34). For the other 7 methods, use the paper table.

Per-dataset std: Tab.8 (pp.25–26). Wall-time targets: Tab.4 (p.17) / Tab.9. E5 targets: Tabs.5–6 (pp.22–23). E6 targets: Tab.7 (p.24). These are transcribed into `results/summary` by Codex from the PDF and checked by Claude (R-06).

Selected E5 targets (avg over Core-11) **[P Tabs.5–6]**:

| (S,E) | 1,100 | 2,50 | 4,25 | 5,20 | 10,10 | 20,5 | 25,4 | 50,2 | 100,1 |
|---|---|---|---|---|---|---|---|---|---|
| avg R̄² | 0.55 | 0.69 | 0.74 | 0.74 | 0.74 | 0.70 | 0.67 | 0.51 | 0.10 |
| avgRank R̄² | 7.1 | 4.9 | 2.6 | 2.1 | 2.4 | 4.1 | 5.2 | 7.7 | 9.0 |
| avg wall (s) | 59.0 | 57.1 | 55.0 | 54.1 | 52.2 | 51.0 | 49.4 | 44.4 | 50.9 |

### 10.3 Validation criteria — **approved (H-01(c), 2026-11-19; two-tier V2 as written below)**

| Level | Criterion |
|---|---|
| **V1 Integrity** | Dataset manifest matches Tab.2 counts. Deterministic learners give std = 0. Metrics recomputed offline from predictions match the logged values to 1e-9. |
| **V2 Per-cell accuracy** | Per (method, dataset): \|mean R̄² − paper\| ≤ max(0.03, 2·paper_std) → *match*; ≤ 0.10 → *partial*; otherwise *mismatch*. Tolerance is a proposal; paper stds are mostly ≤ 0.02 (Tab.8). **Under option K-A** (same jar, data, seeds) also require per-seed \|Δ\| ≤ 0.005 against `exp/post_hoc_new` for the 6 methods it covers; a larger gap means the environment differs and must be explained. |
| **V3 Ranking** | Spearman ρ between reproduced and paper avgRank over methods ≥ 0.8; top-2 set = {Oza(Sgbt), Sgb(Oza)}; Sgbt last among ensembles. |
| **V4 Claims** | Each of C1–C10 marked reproduced / partly / not, with evidence links. |
| **V5 Wall time** | Compare **only ratios within one hardware run** (e.g. time / OzaReg time), never absolute seconds. Claims C4 and C9 are judged on ratios. |
| **V6 Bias–variance** | Qualitative: the √variance curve of Sgbt rises with iterations; Sgb(Oza) < Sgbt; Oza(Sgbt) ≤ Sgb(Oza). Absolute magnitudes are informative only (Fig.2: √bias ≈ 0.049–0.051, √variance ≈ 0.047–0.068 on Ailerons). |

**Reporting rule:** every number in the final report traces to a file under `results/`. Cells that were not run (OOM, timeout, unavailable method) appear as "not run" with the reason. They are never imputed and never copied from the paper.
