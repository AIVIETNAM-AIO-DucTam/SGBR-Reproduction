# SGBR Reproduction — Task Checklist

Agents: **Claude** = research spec, experiment design, scientific review. **Codex** = source code, tests, Kaggle notebooks. **Human** = approvals, execution decisions, final evaluation.
Status values: `Done` · `Ready` (dependencies met) · `Blocked` (waiting on dependencies or questions) · `In progress`.
Priority: **P0** = blocks everything · **P1** = environment & harness · **P2** = minimal reproduction · **P3** = full reproduction · **P4** = reporting.

References: `docs/paper_spec.md` (spec; §11 = authors' code findings), `docs/experiment_plan.md` (plan), `docs/reproduction_plan.md` (cell-level matrix, batches B0–B1), Q-nn = Open Questions below. Authors' repo pinned at commit `f62f7b437512e020f57c4bcd03884c4724eda5b1`.

---

## P0 — Research foundations and approvals

| ID | Description | Agent | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|---|
| R-01 | Analyse paper; write `docs/paper_spec.md` | Claude | – | All 10 required sections present; every claim tagged with page/eq/table; facts kept separate from assumptions | Done |
| R-02 | Write `docs/experiment_plan.md` | Claude | R-01 | All 10 required sections; paper vs [ADAPT] items labelled; compute budget derived from Tab.4 | Done |
| R-03 | Inspect authors' repo read-only; answer Q-nn from code; add [CODE] findings to spec | Claude | R-01 | Each Q-04…Q-22 marked resolved / partly / open with file:line evidence (spec §11.4); no paper facts overwritten | Done (2026-11-19) |
| R-04 | Cross-check Sgbt paper (Gunasekara et al. 2024) against the code's SGBT (§5.0), esp. the learning-rate-at-prediction behaviour (Q-28) | Claude | R-03 | Note in spec saying whether the 2024 paper describes lr at prediction; no change to reproduction protocol unless the human approves | Ready (low priority) |
| R-05 | Ensemble defaults and MOA R̄² evaluator | Claude | R-01 | Answered from code (spec §11.2) | Done (via R-03) |
| H-01 | Approve methodology: (a) execution option K-A (build repo jar) vs K-B/K-C; (b) faithful-to-code policy for code/paper conflicts K-1…K-10 (Q-28, Q-29, Q-35, Q-36); (c) validation tolerances (plan §10.3); (d) dataset scope given missing SUP\* (Q-01, Q-30); (e) minimal-tier subset; (f) Axgb inclusion | Human | R-02, R-03 | Decisions recorded in the Decisions log below | Done (2026-11-19) |
| R-10 | Reproduction plan and matrix (`docs/reproduction_plan.md`): experiments, datasets, exact commands, seeds, metrics, targets, compute, exact vs adapted, priorities | Claude | R-03, H-01, C-01 | Reviewed by the human; §9 statuses confirmed or edited | Done (2026-11-21), awaiting review |
| H-04 | Request SUP2I/SUP3A/SUP3G from the authors (repo README says to contact them) or obtain them via Sun et al. 2025 (arXiv 2502.07213) | Human | – | Files received and handed to C-03, or "unavailable" recorded | Done (2026-11-25): the authors sent SUP2I.arff (100,000 rows, 80 features + `critical_temp`; sha256 7f82ff52e68f6ea7…), SUP3A.arff (200,000 rows, 81 + target; 16754fee351024a7…), SUP3G.arff (200,000 rows, 81 + target; a208b10641c35f34…). Shapes match Tab. 2 [P p.13]; FIRT-DD and HTR R̄² on all three match Tab. 3 [P p.15] to 2 decimals |

## P1 — Environment, data, harness

| ID | Description | Agent | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|---|
| C-01 | Kaggle environment probe: vCPU, RAM, disk, session limit, internet, Java/Maven presence; install JDK 8 (or the closest available) | Codex | H-01 | `results/manifest/environment.json`; Java version recorded | Done (human-reported 2026-11-21: Kaggle CPU, Java 11). **Closeout pending (B0):** commit `environment.json` to the repo |
| C-02 | Build the repo's `moa/` module at commit `f62f7b4` (README Maven command) → `moa.jar`; upload as Kaggle Dataset; run one `moa.DoTask` command from spec §11.1 (Sgb(Oza), Abalone, `-Z 1`) | Codex | C-01 | Final adjusted R̄² equals `exp/post_hoc_new/abalone_1/SGBT(Oza).csv` (0.47689) to ≤ 1e-6; command line logged | Jar build done in C-01 notebook (JDK 11); parity check runs inside C-21 |
| C-03 | Dataset packaging: copy the 13 repo datasets (unzip HyperA, DemandF, NZEnergy) into a private Kaggle Dataset; manifest with sha256, rows, attributes; add SUP\* if H-04 delivers | Codex | R-03, H-01 | `results/manifest/datasets.csv`; counts match spec §11.6 | Ready for the 13 repo datasets; SUP\* waits on H-04 |
| C-04 | Bias–variance split files for FriedmanLea/Gra/Gsg (`_1…_10`, `_12`; 10 % scale): generate **only if** H-01 approves an [ADAPT] generator setting (River FriedmanDrift; parameters not in paper/repo) | Codex | H-01, Q-31 | Generator parameters and seeds documented and labelled [ADAPT] | Blocked |
| C-05 | Experiment runner around the authors' commands: (exp, method, dataset, seed) → one JVM process; `-Z` on the outermost learner only (as the authors do); parallel and resumable; parse MOA CSV (`adjusted coefficient of determination`, `evaluation time (wall) (seconds)`) | Codex | C-02 | Re-running skips finished cells; failed/OOM cells logged as status, never as results | Blocked |
| C-06 | Unit tests: (1) re-implementation of MOA's prequential R̄² (running-mean SS_tot, p incl. target; spec K-5/K-6) matches a MOA CSV; (2) textbook Eq.U-8 R² on hand cases; (3) avg-rank with ties; (4) aggregation mean/std; (5) schema validation | Codex | C-05 | Tests pass in `tests/` | Blocked |
| C-07 | Determinism/seed probe: run Sgb(Oza) and Oza(Sgbt) on Abalone with seeds 1 and 2, twice each; run FIRT-DD and HTR twice each (no seed). Confirm or refute spec K-9 (inner learners share RNG state; seed affects outer learner only) and the one-run rule (H-01(f)) | Codex | C-02 | Report: run-to-run identical? seed-to-seed differences? Matches `post_hoc_new` per seed? FIRT-DD/HTR repeat runs identical in R̄²? | Runs inside C-21 |
| E1F | E1 memory feasibility: NZEnergy × Sgb(Arf) × seed 1, `-Xmx16g` | Codex | C-01 | `results/manifest/e1_memory_feasibility.json` committed; final R̄² compared with 0.9741708731 (`post_hoc_new/NZEnergy_1/SGBT(ARF).csv`); σ = wall ÷ 7,408.09 s reported | Run completed (human-reported 2026-11-21); **manifest not yet committed (B0)** |
| C-21 | **B1 fidelity gate** (`reproduction_plan.md` §12): 6 `post_hoc_new` methods × {abalone, bike, elevators} × seeds 1–5 (90 runs), seed-1 repeat (18), FIRT-DD/HTR × 2 (12); E1 strings; `-Xmx16g`; B1-a serial | Codex | B0 closeout (C-01, E1F manifests) | `results/summary/B1_parity.csv` with Δ per seed, σ per cell, peak RSS, cpu_model; verdict Exact / Tolerance pass / Fail per §12 | **Approved (2026-11-21)**; starts after B0 closeout |
| C-22 | E3 software stack: choose CapyMOA + mlxtend versions that load the pinned jar; reproduce one `RESULTS` point (Ailerons, `B`, b = 5: √bias 0.04988, √var 0.04697) | Codex | C-01 | Versions pinned in `requirements`; one-point check reported | Ready |
| R-06 | Scientific review of runner, metric code and transcribed targets against spec | Claude | C-05, C-06, C-07 | Review notes in `docs/handoffs/`; discrepancies logged | Blocked |

## P2 — Minimal reproduction

| ID | Description | Agent | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|---|
| C-08 | T0 smoke + Kaggle slowdown factor vs Tab.4 (σ now measured in C-21; C-08 reduces to V1 checks) | Codex | R-06, C-21 | Outputs exist; V1 passes; slowdown factor recorded | Blocked |
| C-09 | T1 minimal E1: {Sgb(Oza), Oza(Sgbt), Sgbt, OzaReg, ArfReg, SOKNL, FIRT-DD, HTR} × Core-10 × seeds 1–5 | Codex | C-08 | 320 cells (6 seeded methods × 10 × 5 seeds + FIRT-DD/HTR × 10 × 1 run, one-run rule) complete or status-logged; per-seed comparison to `post_hoc_new` for the 5 covered methods (Sgb(Oza), Oza(Sgbt), OzaReg, ArfReg, SOKNL) | Blocked |
| C-10 | T1b minimal E3: Sgbt bias/variance on Ailerons, iterations {5, 10, 25, 50, 100}, code protocol (plan §5.4) | Codex | C-22 | Compare to `BVDecompose_Results_ailerons.csv` method "B" | Blocked |
| C-11 | T1c minimal E5: Sgb(Oza) (S, E) ∈ {(1,100), (5,20), (10,10), (100,1)} × Core-10 × seeds 1–5 | Codex | C-08 | Summary vs Tabs.5–6 | Blocked |
| C-12 | Learning-rate check for Q-28: Sgb(Oza)(10,10) at lr 0.5 on two Core-10 datasets; log mean prediction / mean target ratio | Codex | C-08 | Ratio ≈ 2 at lr 0.5 confirms spec K-2; result reported either way | Blocked |
| R-07 | Validate minimal results (V1–V6); discrepancy analysis | Claude | C-09…C-12 | Verdict per claim C1–C4, C6–C8; each mismatch linked to a Q-nn | Blocked |
| H-02 | Go / no-go for the full reproduction | Human | R-07 | Decision recorded | Blocked |

## P3 — Full reproduction

| ID | Description | Agent | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|---|
| C-13 | E1-core: 12 methods (no Axgb) × Core-11 × 5 seeds (FIRT-DD/HTR one run) | Codex | H-02 | Tab.3/Tab.4 subset with mean ± std | Done (2026-11-25): all runs on the 13 repo datasets; vast.ai run, archive `sgbr_results_20261125_1805.tgz` |
| C-14 | E1-large (C-14a DemandF, then C-14b NZEnergy; NZEnergy ≈ 115 paper-speed CPU-h, needs Q-37/Q-39); SUP\* only if H-04 delivers, else "not run – data unavailable"; memory-capped scheduling. Full scope = 13 repo datasets (H-01(d)) | Codex | C-13 | All cells run or status-logged | Partly done: 13 repo datasets complete (686 E1 runs). SUP\* received (H-04) but **not run – compute** (decision 2026-11-26) |
| C-15 | Axgb baseline (`meta.AdaptiveXGBoostClassifier -s 10`; needs xgboost4j native libs): **one run per dataset on Core-10** (H-01(f)); HyperA, DemandF, NZEnergy, SUP\* reported as "not run – compute" | Codex | H-02 | 10 runs complete, or a documented failure | Done (2026-11-25): Core-10, one run each |
| C-16 | E4 lr × feature % grid (Fig.9) | Codex | H-02 | 9 configs × Core-11 × 5 seeds | Done (2026-11-25): 495 runs |
| C-17 | E5 full (S, E) grid + E6 table | Codex | H-02 | 9 configs × Core-11 × 5 seeds; Tab.7 from one hardware run | Partly done: E5 grid 495 runs; E6 / Tab.7 not run |
| C-18 | E2 HyperA periodic (`exp_config_overTime.json` settings) | Codex | C-13 | Fig.6-style plot | Partly done: 3 of 4 methods. SOKNL seeds 1–3 OOM at `-Xmx12g` after ≈ 60 %, not retried (decision 2026-11-26) |
| C-19 | E3 full bias–variance (BV-7 non-drift datasets; Friedman* only if C-04 done) | Codex | C-10 | Curves vs `exp/Bias_Variance_Decomp/RESULTS/` | Stopped (decision 2026-11-26): 124 of 4,200 tasks; Friedman\* not run (Q-31) |
| C-20 | Statistics: Friedman + Shaffer (α = 0.05) for R̄² and wall time; blocks = (dataset, seed) as in `post_hoc_new` [CODE-INF], plus the per-dataset variant | Codex | C-13, C-14 | Unit-tested implementation; both variants reported | Blocked |
| R-08 | Full scientific review: claims C1–C10, code/paper conflicts K-1…K-10, threats to validity | Claude | C-13…C-20 | Review doc; every number traceable to `results/` | Blocked |

## P4 — Reporting

| ID | Description | Agent | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|---|
| R-09 | Draft methodology and results sections of the report (paper facts vs code facts vs adaptations kept separate) | Claude | R-08 | Draft; no fabricated results | Blocked |
| H-03 | Final evaluation and sign-off | Human | R-09 | Approved | Blocked |

---

## Open Questions

Evidence: `docs/paper_spec.md` §10 (paper-only) and §11 (code). "Resolve via" = the task most likely to answer it.

| ID | Question | Resolve via | Status |
|---|---|---|---|
| Q-01 | 11 vs 16 datasets — final configs use 16; which scope counts as "full"? | H-01 | **Decided**: full = 13 repo datasets (+SUP* if obtained) (H-01(d)) |
| Q-02 | Abalone 4,977 rows | R-03 | **Resolved**: repo file has 4,977 rows (not raw UCI) |
| Q-03 | HyperA values differ between Tab.1 and Tab.3 | — | Open (not explained by repo) |
| Q-04 | Eq.2 target sign | R-03 | **Resolved**: residual y − ŷ (K-1) |
| Q-05 | Sgbt replacement strategy | R-03 | **Resolved**: none at Sgbt level; inside base learner (K-7) |
| Q-06 | Initial prediction | R-03 | **Resolved**: 0 |
| Q-07 | Feature-subspace sampling | R-03 | **Resolved**: spec §5.0 |
| Q-08 | lr placement; predict before/after train | R-03 | **Resolved**: lr in training only; after train (K-2) |
| Q-09 | Poisson λ | R-03 | **Resolved**: OzaBag 1 (hard-coded), SRP/ARF/SOKNL 6 |
| Q-10 | Inner ensemble subspaces / detectors | R-03 | **Resolved**: spec §11.2 |
| Q-11 | Full FIRT-DD config | R-03 | **Resolved**: spec §11.2 |
| Q-12 | Poisson k as weight vs repeats | R-03 | **Resolved**: weight, single call (K-3) |
| Q-13 | Warm-up | R-03 | **Resolved**: none [CODE-INF] |
| Q-14 | Preprocessing / nominals | R-03, C-03 | Partly resolved (K-10; dataset build scripts not reviewed) |
| Q-15 | Sgbt baseline lr / feat % | R-03 | **Resolved**: 1.0 / 75 % / 100 steps |
| Q-16 | Axgb implementation | R-03 | **Resolved**: repo MOA `meta.AdaptiveXGBoostClassifier` |
| Q-17 | Bias–variance bag size | R-03 | **Resolved**: E = 5 (K-8) |
| Q-18 | Eval frequency; wall-time scope | R-03 | **Resolved**: MOA internal wall clock |
| Q-19 | Seeds and synthetic generators | R-03 | Partly resolved: fixed ARFF files; generator params unknown |
| Q-20 | Bias–variance protocol | R-03 | **Resolved**: spec §11.4 |
| Q-21 | Adjusted R² n, p | R-03 | **Resolved**: running-mean SS_tot, p incl. target (K-5, K-6) |
| Q-22 | Shaffer inputs and tool | R-03 | Partly resolved: 80 (dataset, seed) blocks [CODE-INF]; tool not in repo |
| Q-23 | Fig.9 lr 0.5 collapse | C-12 | Explained by K-2 [INF]; confirm in C-12 |
| Q-24 | Hardware/seeds for Fig.9 and Tab.1 | — | Open |
| Q-25 | Typos / cross-references | — | Note in report |
| Q-26 | Small main vs appendix table mismatches | — | Note in report |
| Q-27 | Tab.7 vs Tab.4 wall times (different hardware) | — | Handled by V5 |
| Q-28 | **New.** Learning rate is not applied at prediction (K-2). Reproduce as coded (faithful) and treat the "corrected" variant as an optional ablation? | H-01 | **Decided**: reproduce as coded (H-01(b)) |
| Q-29 | **New.** HTR ran with MOA defaults (grace 200, conf 1e-7), not the values in the text (K-4). Use the code's command? | H-01 | **Decided**: reproduce as coded (H-01(b)) |
| Q-30 | **New.** SUP2I/SUP3A/SUP3G not in repo | H-04 | Resolved 2026-11-25: files received from the authors (see H-04) |
| Q-31 | **New.** Bias–variance split files for Friedman\* (`_1…_10`, `_12`) and their generator settings not in repo. **2026-11-22 findings:** the full 100k files' `@relation` lines give the exact River calls (e.g. `synth.FriedmanDrift(drift_type='lea', position=(25000, 50000, 75000),seed=42)`; Gsg adds `transition_window=2000`). River 0.27 regenerates all three files exactly except the target's last bit (max rel. diff 3.6e-15, below the float32 the E3 script loads). Five guesses for the 10 % splits (10,000 instances; seeds i, 42+i or i−1; drift positions ×0.1 or unscaled) do **not** reproduce the authors' FriedmanLea B b=5 values (13.257 / √bias 2.378 / √var 2.757): scaled drifts give 14.55–15.01, unscaled 10.61–10.80. The split settings are not recoverable from the paper or repo; only the authors can supply them | H-01, C-04 | Open — ask the authors, or approve an [ADAPT] generator |
| Q-32 | **New.** Upstream MOA/CapyMOA SGBR (Aug–Sep 2025) may differ from commit `f62f7b4`; pin to the repo commit | H-01 | **Decided**: pinned to `f62f7b4` (H-01(a)) |
| Q-33 | **New.** Paper (p.14) attributes Bag(Sgbt) cost to "multiple training iterations" from λ, but the code uses weights, which SGBT discards (K-3). Report as a paper/code inconsistency | R-08 | Open |
| Q-34 | **New.** Seed reaches only the outermost learner; inner learners share an RNG state (K-9). Also check run-to-run determinism | C-07 | Open — verify empirically |
| Q-35 | **New.** MOA R̄² ≠ textbook Eq.U-8 (K-5). Report MOA's value as primary (comparable to paper) plus textbook value as secondary? | H-01 | **Decided**: reproduce as coded (H-01(b)) |
| Q-36 | **New.** Baselines ignore nominal attributes (FIMTDD) while Sgbt-based models one-hot encode them (K-10), which may favour SGBR on DemandF/NZEnergy | R-08 | Open — discuss in report |
| Q-37 | **New (C-01 review).** May per-process `-Xmx` go below the paper's 48g/12g for small datasets so parallel JVMs fit Kaggle RAM? (R̄² unaffected unless OOM; wall time may change) | Human | Decided for E1 (2026-11-21, see Decisions log): 6g × 4 JVMs per shard; heavy NZEnergy cells 26g × 1 JVM |
| Q-38 | **New (C-01 review).** If JDK 8 is unavailable, accept a newer JDK provided C-02 Abalone parity holds to 1e-6? (GC default differs → wall-time caveat) | Human, C-21 | Evidence: pinned module does not compile on JDK 8 (MEKA 1.9.7 bytecode 55; audit), so JDK 11 is forced. **Needs sign-off**, contingent on the C-21 parity verdict |
| Q-39 | **New (C-01 review).** Single runs that can't finish within a Kaggle session (MOA has no checkpointing; NZEnergy runs ≈ 6 h+ at paper speed): report as "not run – session limit", or allow a disclosed non-Kaggle machine? | Human, C-08 | Decided in practice: the full run used a rented vast.ai machine (2026-11-22 … 26); report it as a non-Kaggle run |
| Q-40 | **New (C-01 review).** E3 stack: which CapyMOA and mlxtend versions accept the repo's MOA jar and reproduce `BVDecompose_Results_ailerons.csv`? | C-22 | Open |
| Q-41 | **New (R-10).** Paper says JDK 1.8.0 [P p.34], but the pinned code needs Java ≥ 11 to build. How did the authors build and run it? | H-04 (ask authors) | Open |
| Q-42 | **New (R-10).** Tab.1 (E0) has no config in the repo; SGT command only from the runner help text (`trees.StreamingGradientTreePredictor`); seeds and hardware not stated | — | Open; E0 informative only |
| Q-43 | **New (R-10).** Tab.7 (E6) baseline commands, evaluator and hardware not in repo; inferred as E1 strings + E5 evaluator + `-Xmx12g` | — | Open; inference labelled [CODE-INF] |
| Q-44 | **New (R-10).** Shipped E3 script runs only `BagB`; the `B`/`BB` lines are commented out. Were `RESULTS` B/BB rows produced by enabling them verbatim? | — | Open; enable verbatim [CODE-INF] |
| Q-45 | **New (R-10).** Std estimator in Tabs.8–12 (population vs sample) | R-06 | Open; decide by recomputing Tab.8 from `post_hoc_new` |
| Q-46 | **New (R-10).** Paper p.16 says one bias–variance iteration per drift training file; code uses `num_rounds=10` bootstrap rounds per file | R-08 | Open; follow code (H-01(b)), report |

## Decisions log

| Date | Decision | By |
|---|---|---|
| 2026-11-19 | Authors' repo pinned at commit `f62f7b4` as the code reference | Human (approved in H-01) |
| 2026-11-19 | **H-01(a):** execution option **K-A**: build the repo's MOA jar at `f62f7b4` and run the authors' exact `moa.DoTask` commands (spec §11.1) on Kaggle. Upstream MOA/CapyMOA SGBR is not used for E1/E2/E4–E6 (resolves Q-32). CapyMOA is used only for E3, with the repo jar swapped in | Human |
| 2026-11-19 | **H-01(b):** **faithful-to-code** policy. Where code and paper conflict (spec K-1…K-10), reproduce what the code does and report the conflict. Specifically: learning rate as coded (Q-28; a "corrected" variant is at most an optional, labelled ablation); HTR with the code's command (Q-29); MOA's prequential R̄² as the primary metric (Q-35; textbook R² may appear only as a labelled secondary column); seeds passed only to the outermost learner, as in the authors' runner | Human |
| 2026-11-19 | **H-01(c):** two-tier validation. (1) Per seed, \|ΔR̄²\| ≤ 0.005 against the authors' raw results in `exp/post_hoc_new` for the 6 covered methods. (2) For all other method/dataset cells, \|Δ mean R̄²\| ≤ max(0.03, 2·paper std) = match, ≤ 0.10 = partial, else mismatch (plan §10.3 V2) | Human |
| 2026-11-19 | **H-01(d):** full reproduction = the **13 datasets in the repo**. SUP2I/SUP3A/SUP3G are added only if H-04 delivers them; otherwise they are reported as "not run – data unavailable" (resolves Q-01; Q-30 tracked via H-04) | Human |
| 2026-11-19 | **H-01(e):** minimal tier = **T1 + T1b + T1c** (plan §8): 8-method E1 on Core-10 × 5 seeds, Sgbt bias–variance on Ailerons, and the 4-config (S, E) sweep | Human |
| 2026-11-19 | **H-01(f):** Axgb is run **once per dataset on Core-10**. Larger datasets are reported as "not run – compute". **One-run rule:** learners the authors' runner gives no seed (Axgb, FIRT-DD, HTR) are run once per dataset and that result stands for all 5 seeds (std reported as 0, as in Tabs.8–9). Confirm determinism in C-07 | Human |
| 2026-11-21 | **B1 approved** (`reproduction_plan.md` §12, task C-21) as written: 120 runs, E1 learner and evaluator strings unchanged, JDK 11, `-Xmx16g`, B1-a serial. The approval covers B1 only. Q-37 (heap/concurrency for later batches), Q-38 (general JDK 11 sign-off, after the B1 verdict) and Q-39 stay open, so B1-b also runs serially | Human |
| 2026-11-21 | **E1 heap/concurrency (Q-37, this execution).** Shard sessions run 4 parallel JVMs with `-Xmx6g`. Shard 1 at 6g (Intel Xeon @ 2.20GHz) failed all four NZEnergy SGBT(SRP(FIRTDD)) seeds: seeds 3–4 OOM (peak RSS ≈ 6.8 GB; seed 3 MOA caught the error and exited 0 with an empty CSV), seeds 1–2 hit the 11 h budget at 38.4 % / 49.3 %. Human chose **1 JVM, `-Xmx26g`** for the 10 heavy cells (NZEnergy × {SGBT(SRP(FIRTDD)), SRP(SGBT(FIRTDD))} × seeds 1–5), one Kaggle session each (`notebooks/SGBR_E1_Heavy.ipynb`, HEAVY = 1..10). Shards 1–2 are superseded; shard 3 skips its two Srp(Sgbt) NZEnergy cells. Operational flag `-XX:+ExitOnOutOfMemoryError` added (excluded from the command hash); learner/evaluator strings unchanged. Adaptation vs paper: heap 6g/26g instead of 48g/12g; R̄² unaffected unless OOM, wall time not comparable to Tab. 4 under GC pressure | Human |
| 2026-11-25 | **E3 stopped** after 124 of 4,200 tasks (only BagB on fried and MetroTraffic). Measured cost ≈ 13,500 s per fried BagB b=85 task; the remaining 4,076 tasks were estimated at 970–2,060 CPU-h. Report E3 as partial: the 11 complete points match the authors' `RESULTS` to 9.3e-10, abalone (5 and 10 iterations, local check) to 2e-15; Figs. 2, 7, 8 are shown from the authors' committed curves | Human |
| 2026-11-26 | **SUP2I/SUP3A/SUP3G not run – compute.** Files received and checked (H-04). The run was stopped after ≈ 13.5 h: SUP3A Oza(SGBT(FIRTDD)) seed 2 OOM at `-Xmx16g` after > 80 %; SRP(SGBT(FIRTDD)) on SUP3A/SUP3G at 89–96 % and GC-bound at `-Xmx16g`. Only SUP2I SRP(SGBT(FIRTDD)) seeds 1–3 finished (seeds 1 and 3: R̄² 0.567, 0.566; Tab.3 [P p.15]: 0.57); these are not in the 2026-11-25 archive. A heap map for a later attempt (24–32g, retry 48g) is in the public repo README | Human |
| 2026-11-26 | **E2 SOKNL not retried.** Seeds 1–3 OOM at `-Xmx12g` (the authors' E2 heap) after ≈ 60 %, peak RSS ≈ 18 GB; Fig. 6 reported with 3 of 4 methods | Human |
| 2026-11-26 | **Resumability.** Public repo commit `97d2303` adds `bash exp/run_all.sh status`. Unpacking `sgbr_results_20261125_1805.tgz` into a fresh clone reuses all 1,685 finished MOA runs and 124 E3 tasks (checked locally 2026-11-26); a rerun only does what is listed as not done | Claude (verified) |
