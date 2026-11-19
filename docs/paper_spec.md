# SGBR Paper Specification

**Paper:** N. Gunasekara, B. Pfahringer, H. M. Gomes, A. Bifet. *Gradient boosted bagging for evolving data stream regression.* Data Mining and Knowledge Discovery (2025) 39:65. DOI: 10.1007/s10618-025-01147-x. Source file: `papers/sgbr_paper.pdf` (37 pages).

**Authors' code (stated in paper):** `https://github.com/nuwangunasekara/SGBR.git` — "contains the code, the datasets used, and instructions on how to run the experiments" (App. A.1, p. 34). **Inspected read-only on 2026-11-19 at commit `f62f7b437512e020f57c4bcd03884c4724eda5b1` (2025-09-13).** Code facts are tagged **[CODE path:line]** and collected in §11. Where code and paper disagree, the paper text is kept as written and the conflict is recorded in §11.3.

---

## 0. Conventions used in this document

| Tag | Meaning |
|---|---|
| **[P p.N]** | Fact stated in the paper on journal page N (pagination "Page N of 37"). |
| **[P Eq.k]** / **[P Tab.k]** / **[P Fig.k]** | Numbered equation / table / figure in the paper. |
| **[P Eq.U-x]** | Unnumbered equation in the paper; label assigned by this spec. |
| **[INF]** | Our inference from paper text. Plausible but not stated verbatim. |
| **[ASSUME]** | Assumption needed to implement; not in the paper. Must be confirmed (authors' code or human approval). |
| **[EXT]** | Comes from a cited external work or general knowledge, *not* from this paper. Must be verified. |
| **[CODE path:line]** | Read directly in the authors' repo (commit `f62f7b4`). Paths are relative to the repo root; `SGBT.java` = `moa/src/main/java/moa/classifiers/meta/StreamingGradientBoostedTrees.java`. |
| **[CODE-INF]** | Our reading of how the code behaves when run. Not executed yet; confirm empirically (task C-07). |
| **Q-nn** | Open question, tracked in `docs/tasks.md` §Open Questions. |

Only items tagged **[P …]** are paper facts. Everything else is a proposal.

Page-to-section map (for citation lookup): §1 Introduction p.2; §2 Related work pp.3–4; §3 SGBR p.5; §3.1 Bias and variance p.8; §3.2 Addressing high variance pp.9–11; §4 Experiments pp.11–14; §4.1 Comparison against baselines pp.14–16; §4.2 Bias-variance decomposition pp.16–19; §4.3 Parameter exploration pp.19–33; §5 Limitations p.33; §6 Conclusions p.33; App. A Experimental setup p.34; App. B Additional results (Tables 8–12, pp.25–32).

---

## 1. Research problem and motivation

1. **Problem.** Regression on evolving data streams: instances arrive sequentially, the distribution may change (concept drift), and memory/processing are limited **[P p.2, §1]**.
2. **State of the art before this paper.** Ensembles dominate streaming regression: ArfReg (Adaptive Random Forest Regressor) and SOKNL (Self-Optimising k-Nearest Leaves) are the leading methods **[P p.2]**. Boosting has been "relatively unexplored" for streaming regression **[P p.2]**.
3. **Trigger.** Streaming Gradient Boosted Trees (Sgbt, Gunasekara et al. 2024) surpassed bagging/random-forest methods in streaming *classification* **[P p.2]**. The natural move is vanilla Sgbt with squared loss for regression.
4. **Observed failure.** Vanilla Sgbt with 100 boosting steps of FIRT-DD performs *worse* than most single-tree regressors (avg R̄² 0.3 vs 0.4 for FIRT-DD/HTR on 11 datasets) **[P p.6–8, Tab.1]**.
5. **Diagnosis.** Sgbt shows high variance in regression; on Ailerons, √variance grows with boosting iterations (≈0.047 → ≈0.066 over 5–100 iterations) while √bias stays ≈0.049–0.051 **[P p.8, Fig.2; values read from plot]**. Boosting overfits sequentially, and regression (squared loss) tolerates variance less than zero–one loss **[P p.9, §3.2]**.
6. **Idea.** Batch gradient boosting once used bagged base learners to cut variance (Friedman et al. 2000) **[P p.2, p.9]**. The paper carries this over to streams. The authors say no earlier work has placed bagging-based streaming regressors inside a streaming gradient-boosting framework **[P p.3, p.9]**.

## 2. Main contributions

As stated by the authors **[P pp.2–3, §1; p.33, §6]**:

1. **SGBR** (Streaming Gradient Boosted Regression), which combines streaming bagging regressors with Sgbt in two ways:
   - **SGB(Bag)** — *Streaming Gradient Boosted Bags*: a bagging-type streaming regressor is the **base learner of Sgbt**. Variants: Sgb(Oza), Sgb(Arf), Sgb(Srp).
   - **Bag(Sgbt)** — *Bagged Streaming Gradient Boosted Trees*: a bagging-type ensemble **whose members are Sgbt models**. Variants: Oza(Sgbt), Srp(Sgbt).
2. An empirical study on streaming regression benchmarks with several drift scenarios. Headline result: **Sgb(Oza) beats SOKNL** on predictive power (R̄²) **and** computational cost **[P p.1 Abstract; p.16; Fig.4, Fig.5]**.
3. A bias–variance analysis showing SGBR lowers Sgbt's variance while bias stays about the same **[P p.19, §4.2, Figs.7–8]**.
4. A parameter study covering learning rate, feature percentage and the boosting-steps × bag-size trade-off **[P pp.19–33, §4.3]**.

> ⚠ **Dataset-count inconsistency.** The abstract (p.1), introduction (p.3) and §4 opening (p.11) say "11 datasets … four real-world and seven synthetic", but Table 2 (p.13) and Tables 3–4 (pp.15, 17) list **16 datasets (10 synthetic, 6 real)**. See Q-01.

## 3. Detailed model architecture

### 3.1 Building block: Sgbt (Streaming Gradient Boosted Trees)

What this paper says about Sgbt:

- An additive model of S streaming regressors, $\hat y = \sum_{s=1}^{S} f_s(x)$ **[P p.6, Eq.U-1]**.
- At each step the base learner is trained on a **weighted squared loss**: weight $h_i$ (hessian), target derived from $g_i/h_i$ (gradient/hessian) **[P p.6, Eq.2]**. That is why any streaming regressor can serve as the base learner **[P p.6]**.
- Base learners are streaming regressors with an **internal Base Learner Replacement strategy** for adapting to drift **[P p.6]**.
- **Each base learner is trained on a random subset of features (random subspace)** to add diversity **[P p.6]**.
- For regression, number of classes **C = 1**: each boosting step's regressor improves on the cumulative prediction of the earlier steps **[P p.11]**.
- Hyperparameters this paper names for Sgbt-based models: number of boosting steps S, **learning rate**, **feature percentage** **[P p.13; p.19 §4.3]**.

What this paper does **not** say about Sgbt (deferred to Gunasekara et al. 2024, *Mach Learn*, DOI 10.1007/s10994-024-06517-y) **[EXT]**: how and when base learners are replaced; whether the feature subspace is drawn once per boosting step or redrawn at replacement; the initial prediction $\hat y^{(0)}$; where the learning rate is applied; whether $f_s(x)$ used to update $\hat y^{(s)}$ is computed before or after $f_s$ trains on the current instance. → Q-05, Q-06, Q-07, Q-08.

### 3.2 Bagging-type streaming regressors used as components

| Name | Type | Facts from this paper |
|---|---|---|
| **OzaReg** | Streaming bagging regressor (Oza Bag adapted to regression, Gomes et al. 2020) | OzaBag approximates bootstrap sampling with Poisson(1) **[P p.4]**. OzaReg has a λ parameter that causes "per-instance multiple training iterations" **[P p.14]**. Aggregation = **mean** of member predictions **[P p.10, Fig.3 caption]**. |
| **ArfReg** | Streaming random-subspace / random-forest regressor (Gomes et al. 2018) | Uses a specific FIRT-DD base learner **[P p.10]**. Mean aggregation **[P p.10]**. Default MOA configuration = FIRT-DD with VarianceReductionSplitCriterion, grace period 50, split confidence 0.01, 100 trees **[P p.13]**. |
| **SrpReg** | Streaming Random Patches regressor (Gomes et al. 2020) | Random patches = instance subsets + feature subsets **[P p.4]**. Has a λ parameter **[P p.14]**. Mean aggregation **[P p.10]**. |

The λ values for OzaReg and SrpReg, the subspace sizes for ArfReg and SrpReg, and the drift detectors and their parameters are **not stated** → Q-09, Q-10.

### 3.3 Leaf-level base learner: FIRT-DD

- FIRT-DD = Fast Incremental Regression Tree with Drift Detection (Ikonomovska et al. 2011) **[P p.4]**.
- Configuration used everywhere in SGBR and in the baselines: **VarianceReductionSplitCriterion, grace period = 50, split confidence = 0.01** **[P p.13; p.14 "All inner ensembles and FIRT-DD used the same FIRT-DD configurations"]**.
- Leaf prediction model, tie threshold, drift-detector parameters and other settings: not stated → Q-11.

### 3.4 SGBR variants

Naming rule: **the outermost ensemble is written first** **[P p.10]**.

| Variant | Family | Outer structure | Inner structure | Source |
|---|---|---|---|---|
| **Sgb(Oza)** | SGB(Bag) | Sgbt, S boosting steps | each step = OzaReg with E FIRT-DD members | **[P p.10, Fig.3a-i]** |
| **Sgb(Arf)** | SGB(Bag) | Sgbt | each step = ArfReg (E trees) | **[P p.10, Fig.3a-ii]** |
| **Sgb(Srp)** | SGB(Bag) | Sgbt | each step = SrpReg (E trees) | **[P p.10, Fig.3a-iii]** |
| **Oza(Sgbt)** | Bag(Sgbt) | OzaReg with E members, mean aggregation | each member = Sgbt with S FIRT-DD steps | **[P p.10, Fig.3b-i]** |
| **Srp(Sgbt)** | Bag(Sgbt) | SrpReg with E members, mean aggregation | each member = Sgbt with S FIRT-DD steps | **[P p.10, Fig.3b-ii]** |

Variants the paper excludes on purpose **[P p.10]**:
- **Sgb(Soknl)** — feasible, but worse than SOKNL in early experiments.
- **Arf(Sgbt)** — ArfReg needs its own FIRT-DD base learner.
- **Soknl(Sgbt)** — not possible because of SOKNL's special base learner.

**Tree budget.** Main experiments: E = 10 ensemble items × S = 10 boosting steps = **100 trees** per SGBR model **[P p.13]**.

### 3.5 Complexity (as stated)

- Original Sgbt: time O(C·S·f), memory O(C·S·f), where f is the base learner's cost **[P p.11]**.
- SGB(Bag) with C = 1: O(S · f_SGBag), with f_SGBag the cost of the bagging/subspace/patches base learner **[P p.11]**.
- Bag(Sgbt): O(com_Bag/SRP(S·f)) **[P p.11]**.

---

## 4. Mathematical equations

All formulas are as printed. Where we see a problem, it is flagged and a correction is proposed separately.

**Eq.U-1 — additive model** **[P p.6]**
$$\hat y_i = \phi(x_i) = \sum_{s=1}^{S} f_s(x_i),\quad f_s \in \mathcal F$$
$\mathcal F$ = space of regressors.

**Eq.(1) — regularised objective** **[P p.6]**
$$\mathcal L(\phi) = \sum_{i=1}^{n} l(y_i, \hat y_i) + \sum_{s=1}^{S} \Omega(f_s)$$
$l$: differentiable convex loss; $\Omega$: complexity penalty.

**Eq.U-2 — loss at step s** **[P p.6]**
$$\mathcal L^{(s)} = \sum_{i=1}^{n} l\big(y_i, \hat y^{(s-1)} + f_s(x_i)\big) + \Omega(f_s)$$

**Eq.U-3 — second-order Taylor approximation** **[P p.6]**
$$\mathcal L^{(s)} \simeq \sum_{i=1}^{n}\Big[l(y_i,\hat y^{(s-1)}) + g_i f_s(x_i) + \tfrac12 h_i f_s^2(x_i)\Big] + \Omega(f_s)$$
$$g_i = \partial_{\hat y^{(s-1)}} l(y_i,\hat y^{(s-1)}),\qquad h_i = \partial^2_{\hat y^{(s-1)}} l(y_i,\hat y^{(s-1)})$$

**Eq.(2) — weighted squared loss** **[P p.6]**
$$\sum_{i=1}^{n} \tfrac12 h_i\big(f_t(x_i) - g_i/h_i\big)^2 + \Omega(f_s) + \text{constant}$$
"…with *hessian* as the *weight* and *gradient* over *hessian* as the *target*" **[P p.6]**.

> ⚠ **Sign/index issue in Eq.(2) [INF].** Completing the square in Eq.U-3 gives $g f + \tfrac12 h f^2 = \tfrac12 h\,(f + g/h)^2 - g^2/(2h)$, so the minimising target is **$-g_i/h_i$**, not $+g_i/h_i$. The subscript also switches from $f_s$ to $f_t$. Proposed reading (Friedman et al. 2000; Chen & Guestrin 2016 **[EXT]**): base learner $s$ fits **target $-g_i/h_i$ with instance weight $h_i$**. The authors' code must confirm this → Q-04.

**Squared loss specialisation [INF].** The paper says only "squared loss" **[P p.6, p.13]**. With $l = \tfrac12(y-\hat y)^2$: $g = \hat y - y$, $h = 1$, so target $-g/h = y - \hat y^{(s-1)}$ (the residual) and weight 1. With $l=(y-\hat y)^2$: $h = 2$ and the target is unchanged. The weights still differ, and that can matter because Hoeffding-type trees count weighted instances against the grace period → Q-04.

**Eq.U-4 — optimal prediction (Domingos 2000)** **[P p.8]**: $y_* = \arg\min_{y'} E_y[L(y, y')]$.

**Eq.U-5 — main prediction** **[P p.8]**
$$\hat y_m = y^{L,D}_m = \arg\min_{y'} E_D[L(\hat y, y')]$$
Under squared loss this is the mean of predictions over training sets $D$ **[P p.8]**.

**Eq.U-6 — bias** **[P p.8]**: $\mathrm{Bias}(x) = L(y_*, \hat y_m)$.

**Eq.U-7 — variance** **[P p.8]**: $\mathrm{Variance}(x) = E_D[L(\hat y_m, \hat y)]$. Both are averaged over examples **[P p.8]**. The figures plot $\sqrt{\text{bias}}$ and $\sqrt{\text{variance}}$ **[P Fig.2, Figs.7–8 legends]**.

**Eq.U-8 — coefficient of determination** **[P p.14]**
$$R^2 = 1 - \frac{\sum_{i=1}^{n}(m(x_i) - y_i)^2}{\sum_{i=1}^{n}(y_i - \bar y)^2}$$
$m(x_i)$ = model prediction; $\bar y$ = mean of all true values. Range $(-\infty, 1]$.

**Eq.U-9 — adjusted R²** **[P p.14]** (Yin & Fan 2001)
$$\bar R^2 = 1 - (1 - R^2)\,\frac{n-1}{n-p-1}$$
$n$ = sample size, $p$ = number of input dimensions.

---

## 5. Algorithm pseudocode

**Status:** The paper gives **no pseudocode**. §5.1–5.3 below are reconstructed from §3 (pp.5–11) and Fig.3 (p.10). **§5.0 is the code-confirmed version and takes precedence for reproduction.** This is a specification, not implementation code.

### 5.0 Sgbt as implemented (code-confirmed, regression)

```
SGBT(S, lr, feat_pct, base)                                            [CODE SGBT.java:73-89]
  INIT on first instance:                                              [CODE SGBT.java:429-504]
    n ← #input attributes; k ← round(n·feat_pct/100); if round(..) < 2: k ← round(..)+1
    if k < n:
       if n ≤ 20 (or k < 2): candidate subspaces ← all C(n,k) combinations (recycled if fewer than S)
       else:                candidate subspaces ← S random k-combinations
    else (k = n): every step uses all features
    F_s ← S distinct candidates drawn with the SGBT RNG; fixed for the whole stream (never redrawn)
    B_s ← copy of base learner (created lazily at the first training call)

  TRAIN(x, y):                                                         [CODE SGBT.java:506-553]
    raw ← 0                                                            # initial prediction 0
    for s in 1..S:
      g' ← y − raw ; h ← 1                                             # SquaredError, computeNegativeResidual=false [CODE SGBT.java:659-675]
      x_s ← one-hot(x[F_s]) for nominal attrs with >2 values; weight = 1.0   # incoming instance weight is DISCARDED [CODE SGBT.java:242-298, 529]
      B_s.train(x_s, target = g'/h = y − raw)                          # trained once (M = 1 ⇒ ceil(h·M) = 1) [CODE SGBT.java:687-692]
      raw ← raw + lr · B_s.predict(x_s)                                # predicted AFTER training on this instance [CODE SGBT.java:546-551]

  PREDICT(x):                                                          [CODE SGBT.java:554-587]
    return Σ_s B_s.predict(one-hot(x[F_s]))                            # NOTE: no learning-rate factor at prediction
```

There is **no Sgbt-level learner replacement**. Drift adaptation lives entirely inside the base learner (FIMTDD's Page-Hinkley-triggered alternate trees, or the ensembles' ADWIN detectors) [CODE SGBT.java, whole class].

### 5.1 Sgbt (regression, C = 1) — reconstruction from paper text only

```
SGBT(S, lr, feat_pct, make_base, loss)
  state:
    for s in 1..S:
      F_s  ← random subset of ceil/floor(feat_pct · p) features        [P p.6 random subspace; rounding ASSUME Q-07]
      B_s  ← make_base()                                               [P p.6]

  PREDICT(x):
    ŷ ← ŷ0                                                             [ASSUME ŷ0 = 0, Q-06]
    for s in 1..S: ŷ ← ŷ + lr · B_s.predict(x[F_s])                    [ASSUME lr placement, Q-08]
    return ŷ

  TRAIN(x, y):                                                         # one stream instance
    ŷ ← ŷ0
    for s in 1..S:
      g ← ∂l(y, ŷ)/∂ŷ ;  h ← ∂²l(y, ŷ)/∂ŷ²                             [P Eq.U-3]
      B_s.train(x[F_s], target = −g/h, weight = h)                     [P Eq.2; sign per §4 note, Q-04]
      ŷ ← ŷ + lr · B_s.predict(x[F_s])                                 [ASSUME: predict before/after train? Q-08]
    (base-learner replacement on drift happens inside B_s)             [P p.6 "internal"; details EXT, Q-05]
```

### 5.2 OzaReg (bagging regressor component)

```
OZAREG(E, λ, make_member)
  members M_1..M_E ← make_member()
  PREDICT(x): return mean_j M_j.predict(x)                             [P p.10]
  TRAIN(x, t, w):
    for j in 1..E:
      k ← Poisson(λ)                                                   [P p.4 Poisson(1) for OzaBag; λ value Q-09]
      if k > 0: train M_j on (x, t) with weight w·k  OR  k repeated calls   [ASSUME; p.14 suggests repeats; Q-12]
```

### 5.3 SGBR variants as compositions

```
Sgb(Oza)  = SGBT(S=10, lr=1.0, feat_pct=0.75, make_base = λ: OZAREG(E=10, λ, FIRT-DD(cfg)))   [P p.13]
Sgb(Arf)  = SGBT(S=10, lr=1.0, feat_pct=0.75, make_base = λ: ARFREG(E=10, FIRT-DD(cfg)))      [P p.13]
Sgb(Srp)  = SGBT(S=10, lr=1.0, feat_pct=0.75, make_base = λ: SRPREG(E=10, FIRT-DD(cfg)))      [P p.13]
Oza(Sgbt) = OZAREG(E=10, λ, make_member = SGBT(S=10, lr=1.0, feat_pct=0.75, FIRT-DD(cfg)))    [P p.13]
Srp(Sgbt) = SRPREG(E=10, make_member = SGBT(S=10, lr=1.0, feat_pct=0.75, FIRT-DD(cfg)))       [P p.13]
FIRT-DD(cfg): split criterion = VarianceReduction, grace period = 50, split confidence = 0.01   [P p.13]
```
Open points: which level the 75 % feature percentage applies to in Sgb(Arf)/Sgb(Srp)/Srp(Sgbt), where ArfReg/SrpReg also subsample features (Q-10); whether the inner base learner of ArfReg/SrpReg inside Sgb(·) is FIRT-DD or ArfReg's own FIRT-DD variant (Q-11).

### 5.4 Prequential (test-then-train) loop

```
for each instance (x_t, y_t) in stream order:                          [P p.14 "test-then-train"]
   ŷ_t ← model.PREDICT(x_t)          # test first
   evaluator.add(y_t, ŷ_t)           # cumulative and windowed R̄²
   model.TRAIN(x_t, y_t)             # then train
   record wall-time                                                    [P p.14]
```

## 6. Training and prediction procedures

| Aspect | Paper fact | Gap |
|---|---|---|
| Training regime | Single pass, incremental, test-then-train **[P p.14]** | Warm-up period not stated (Q-13) |
| Boosting target | Weighted squared loss, weight h, target from g/h **[P p.6 Eq.2]** | Sign (Q-04) |
| Loss | Squared loss **[P p.6, p.13]** | ½ factor (Q-04) |
| Prediction aggregation (bagging layers) | Mean of member predictions **[P p.10]** | — |
| Prediction aggregation (boosting) | Additive sum of step outputs **[P p.6 Eq.U-1]** | Learning-rate placement, initial value (Q-06, Q-08) |
| Drift adaptation | Internal Base Learner Replacement in base learners **[P p.6]**; FIRT-DD has drift detection **[P p.4]**; ArfReg/SrpReg use drift detectors such as ADWIN **[P p.4]** | Detector parameters (Q-10, Q-11) |
| Diversity | Random subspace per Sgbt base learner **[P p.6]**; Poisson resampling in OzaReg/SrpReg **[P p.4, p.14]** | λ, subspace sampling (Q-07, Q-09) |
| Feature preprocessing | Not described | Normalisation, nominal attributes, missing values (Q-14) |

## 7. Base learners and ensemble variants

| Model | Role | Configuration as stated |
|---|---|---|
| FIRT-DD | Leaf learner for all SGBR variants and ensembles; single-tree baseline | VarianceReduction, GP 50, SC 0.01 **[P p.13]** |
| HTR (Hoeffding Tree Regressor) | Single-tree baseline | GP 50, SC 0.01 **[P p.13–14]** |
| SGT (Stochastic Gradient Trees, Gouk et al. 2019) | Baseline in Table 1 only | "default SGT parameters from Gouk et al. (2019)" **[P Tab.1 footnote, p.7]** |
| OzaReg | Baseline + SGBR component | 100 members as a baseline **[INF from p.13 "other baselines that used 100 trees"; Fig.6 caption "100 base learners"]**; λ not stated |
| ArfReg | Baseline + component | Default MOA config (100 trees, FIRT-DD GP 50, SC 0.01, VarianceReduction) **[P p.13]** |
| SOKNL | Baseline | Default MOA config (same tree settings, 100 trees) **[P p.13]**; k not stated |
| SrpReg | Baseline + component | 100 members **[INF, p.13]**; λ, subspace size not stated |
| Sgbt (vanilla) | Baseline | 100 boosting iterations of FIRT-DD **[P Tab.1 caption, p.7]**; learning rate and feature % for the Table 3 run not stated (Q-15) |
| Axgb (Adaptive XGBoost) | Baseline | Squared loss, mean vote aggregation, 10 boosting iterations × XGBoost with 10 trees, lr 0.3, max depth 6, max window 1000, min window 1, no drift detection, "replace" strategy **[P p.13]**. Implementation used for the regression extension not identified (Q-16) |

## 8. Hyperparameters and values

### 8.1 Main configuration (Tables 3–4)

| Hyperparameter | Value | Applies to | Source |
|---|---|---|---|
| Boosting steps S | 10 | All SGBR | **[P p.13]** |
| Ensemble size E | 10 | All SGBR | **[P p.13]** |
| Total trees | 100 | All SGBR & ensemble baselines | **[P p.13]** |
| Learning rate | 1.0 | All SGBR | **[P p.13]**, chosen in §4.3 |
| Feature percentage | 75 % | All SGBR | **[P p.13]**, chosen in §4.3 |
| Loss | Squared loss | Sgbt-based models, Axgb | **[P p.6, p.13]** |
| FIRT-DD split criterion | VarianceReductionSplitCriterion | All FIRT-DDs | **[P p.13]** |
| FIRT-DD grace period | 50 | FIRT-DD, HTR | **[P p.13]** |
| FIRT-DD split confidence | 0.01 | FIRT-DD, HTR | **[P p.13]** |
| Aggregation in OzaReg/ArfReg/SrpReg | Mean | — | **[P p.10]** |
| Axgb | see §7 | — | **[P p.13]** |
| Random seeds | 1, 2, 3, 4, 5 | Tables 3–7, Figs 4, 5, 10 | **[P p.34, App. A.1]** |
| Random seeds | 1, 2, 3 | Fig. 6 | **[P p.34]** |

### 8.2 Parameter-exploration grids (§4.3)

| Study | Grid | Fixed | Source |
|---|---|---|---|
| Learning rate × feature % | lr ∈ {0.5, 1.0, 1.5} × feat ∈ {25 %, 75 %, 100 %} | Sgb(Oza), S = 10, E = 10 | **[P pp.19–21, Fig.9]** |
| Boosting steps × bag size (product = 100) | (S, E) ∈ {(1,100), (2,50), (4,25), (5,20), (10,10), (20,5), (25,4), (50,2), (100,1)} | Sgb(Oza), lr 1.0, feat 75 % | **[P p.21, Tabs.5–6, Fig.10]** |
| Bias–variance | Boosting iterations 5…100 (step 5 from Fig.2 x-axis) | Sgbt / Sgb(Oza) / Oza(Sgbt) | **[P Fig.2, Figs.7–8]**; E for Sgb(Oza)/Oza(Sgbt) not stated (Q-17) |

### 8.3 Selected configurations
- lr = 1.0 with 75 % features gives the best balance of R̄² and wall time **[P p.21]**.
- (10,10) is best by average mean R̄² + wall time; (5,20) is best by average rank for both R̄² and wall time **[P p.21, p.33]**.

## 9. Data stream learning protocol

1. **Evaluation:** test-then-train (prequential) **[P p.14]**.
2. **Overall metric:** cumulative R̄² over the whole stream; final test-then-train wall time in seconds **[P p.14]**.
3. **Periodic metric:** windowed R̄² and wall time at each time point **[P p.14]**; window = 10k instances in Fig.6 **[P Fig.6 caption, p.18]**. Evaluation frequency not stated (Q-18).
4. **Ordering:** instances processed in stream order **[INF]**. Shuffling is only mentioned for bias–variance, where it is explicitly *not* done **[P p.16]**.
5. **Repetitions:** 5 runs with seeds 1–5 (Fig.6: 3 runs, seeds 1–3) **[P p.14, p.34]**. What the seed controls (learner randomness only, or also synthetic stream generation) is not stated (Q-19).
6. **Framework:** MOA (Java) for Tables 3–7, Figs 4–6, 10; CapyMOA + mlxtend for bias–variance (Figs 2, 7, 8) **[P p.34]**. JDK 1.8.0; JVM `-Xms50m -Xss1g`, `-Xmx48g` (Experiment 1) / `-Xmx12g` (others); in Experiment 1 Sgb(Oza) ran with 12 GB but the other algorithms needed 48 GB **[P p.34]**.
7. **Ranking & significance:** average rank across datasets; Shaffer post-hoc test, p = 0.05 **[P p.16, Figs.4–5]**.

### 9.1 Bias–variance protocol (§4.2, p.16)

- Methods: Sgbt, Sgb(Oza), Oza(Sgbt); FIRT-DD base learners with the main config **[P p.16]**.
- **Datasets without drift:** 10-fold CV without shuffling; bias and variance "calculated using 10 iterations of each split" **[P p.16]**.
- **Synthetic datasets with drift:** 11 scaled-down (10 %) datasets generated with different seeds; one kept as test set; bias/variance over 10 iterations, one per training set **[P p.16]**.
- Excluded: HyperA, SUP2I, SUP3A, SUP3G, DemandF, NZEnergy **[P p.16]**. Plotted: Ailerons, FriedmanLea, MetroTraffic, FriedmanGra, House8L, FriedmanGsg (Fig.7); Elevators, Abalone, Bike, Fried (Fig.8) **[P pp.19–20]**.
- Tool: `mlxtend.evaluate.bias_variance_decomp`, MSE loss; MOA regressors wrapped as sklearn regressors via CapyMOA and trained incrementally **[P p.16, p.34]**.
- Unclear: how 10-fold results are combined; whether mlxtend's internal bootstrap resampling was used (it would reorder instances) (Q-20).

## 10. Ambiguities and missing implementation details

IDs match `docs/tasks.md` §Open Questions. This table is the paper-only analysis. **What the authors' code resolves is in §11.4.**

| ID | Issue | Evidence | Impact |
|---|---|---|---|
| Q-01 | 11 vs 16 datasets | p.1, p.3, p.11 vs Tab.2 p.13, Tabs.3–4 | Scope of "full" reproduction |
| Q-02 | Table 2 counts disagree with common public versions (e.g. Abalone listed with 4977 instances; UCI Abalone is usually 4177 **[EXT]**) | Tab.2 p.13 | Dataset identity check |
| Q-03 | HyperA: Table 2 says 500,000 instances; text and Fig.6 agree (drifts at 125k/250k/375k). HyperA scores differ between Tab.1 and Tab.3 for FIRT-DD (0.42 vs 0.47), HTR (0.40 vs 0.35), Sgbt (0.22 vs 0.27) while the other 10 datasets match | Tab.1 p.7, Tab.3 p.15 | Which HyperA stream is canonical |
| Q-04 | Sign of target (g/h vs −g/h); ½ factor in squared loss; f_t vs f_s | Eq.2 p.6 | Core algorithm correctness |
| Q-05 | Sgbt base-learner replacement strategy | p.6 (deferred to Gunasekara et al. 2024) | Drift behaviour |
| Q-06 | Initial prediction ŷ⁽⁰⁾ | not stated | Early-stream R̄² |
| Q-07 | Feature-subspace sampling (per step? redrawn? rounding of 75 %) | p.6, p.13 | Diversity, wall time |
| Q-08 | Learning-rate placement and predict-before/after-train ordering inside TRAIN | not stated | Residual targets |
| Q-09 | Poisson λ for OzaReg / SrpReg (p.14 names "λ" without values) | p.4, p.14 | Variance, cost |
| Q-10 | ArfReg/SrpReg subspace sizes, drift detectors, background learners; which level the 75 % applies to in Sgb(Arf)/Sgb(Srp)/Srp(Sgbt) | p.13 | Variant fidelity |
| Q-11 | FIRT-DD settings beyond the 3 given (leaf model, tie threshold, Page-Hinkley parameters); exact MOA class names | p.13 | All results |
| Q-12 | OzaReg Poisson k as instance weight vs repeated training | p.14 ("per-instance multiple training iterations") | Cost and results of Oza(Sgbt) |
| Q-13 | Warm-up / initial instances excluded from evaluation | not stated | Cumulative R̄² |
| Q-14 | Preprocessing: nominal attributes (e.g. MetroTraffic weather, Bike season), normalisation, missing values, target column | not stated | Dataset loading |
| Q-15 | Vanilla Sgbt baseline learning rate and feature % | Tab.1, Tab.3 | Baseline fidelity |
| Q-16 | Implementation of Axgb for regression (MOA? scikit-multiflow? authors' fork?) | p.13 | Baseline availability |
| Q-17 | Ensemble size E and iteration grid used in bias–variance runs | Figs.2, 7, 8 | Fig. reproduction |
| Q-18 | Windowed-evaluation sampling frequency; how wall time is measured (CPU vs wall clock, includes I/O?) | p.14 | Plots, Table 4 |
| Q-19 | What the random seed controls; whether synthetic streams are regenerated per seed; generator parameters for HyperA (HyperPlaneRegression + DriftStream: noise, magnitude) and FriedmanDrift (Gsg transition width, seed) | p.12 footnotes 1–2 | Synthetic data identity |
| Q-20 | Bias–variance aggregation over folds; use of mlxtend bootstrap | p.16 | Figs.2, 7, 8 |
| Q-21 | Adjusted R² for windowed metric: n = window size or instances seen? p = raw feature count or after encoding? | p.14 | Metric values |
| Q-22 | Shaffer test inputs (per-dataset mean over seeds?), software used; Fig.5 "Higher is better" rank direction; Fig.4 includes Sgb(Arf) though text lists only 5 methods | p.16, p.18 | Figs.4–5 |
| Q-23 | Fig.9: avg R̄² ≈ −6.7 to −7.0 at lr = 0.5 (≈ 0.65–0.74 at lr = 1.0). Unexplained; may come from one diverging dataset or an implementation detail | Fig.9 p.20 | Validates lr handling |
| Q-24 | Hardware and seeds for Fig.9 and Table 1 not listed in App. A.1 | p.34 | Wall-time comparability |
| Q-25 | Typos/cross-references: "Sgb(Oza), Sgb(Arf), Sgb(Oza)" should probably be "…Sgb(Srp)" (p.13); "Sect. 1" refers to App. A; Fig.6 caption "ArfRegArfReg" and omits OzaReg, which is in the legend | pp.13, 18 | Clarity only |
| Q-26 | Minor numeric mismatches between main and appendix tables (e.g. Tab.5 (4,25) avgRank 2.6 vs Tab.10 2.5; Tab.7 ArfReg hyperA 0.58 vs Tab.3 0.61; Tab.7 ArfReg avgRank 4.6 vs Tab.12 4.5) | Tabs.3, 5, 7, 10, 12 | Validation tolerance |
| Q-27 | Table 7 wall times for the same methods differ from Table 4 (e.g. SOKNL Fried 51.0 vs 56.5) because Tables 5–7 ran on different hardware (App. A.1 items 1 vs 2) | p.34 | Use only within-table relative timing |

---

## 11. Findings from the authors' repository (commit `f62f7b4`)

Read-only inspection on 2026-11-19. Nothing was executed except counting ARFF data lines and summarising the result CSVs shipped in the repo. Repo layout used here: `moa/` = modified MOA source (Maven, Java 1.8 target, `xgboost4j_2.13` 2.1.1 dependency) [CODE moa/pom.xml:207-226]; `exp/` = experiment configs, runner, datasets, raw results, bias–variance scripts. License: GPL-3.0.

### 11.1 Exact experiment commands

The runner is `exp/benchmark_moa.py`. For each seed → dataset → learner it runs:
`java -classpath moa.jar <java_options> moa.DoTask "<evaluator> -s (ArffFileStream -f <dataset>.arff) -l (<learner> -Z <seed>) -d <out>.csv"` [CODE exp/benchmark_moa.py:121-160].
The seed is appended **only** when the learner's seed column is `"Z"`, and **only to the outermost learner** [CODE exp/benchmark_moa.py:137-140].

| Paper name | MOA learner string (config `exp/exp_config.json`) | Seed? |
|---|---|---|
| Oza(Sgbt) | `meta.OzaBag -s 10 -l (meta.StreamingGradientBoostedTrees -t -L 1.0 -m 75 -s 10 -l (trees.FIMTDD -s VarianceReductionSplitCriterion -g 50 -c 0.01 -e))` | -Z |
| Srp(Sgbt) | `meta.StreamingRandomPatches -s 10 -l (meta.StreamingGradientBoostedTrees -t -L 1.0 -m 75 -s 10 -l (trees.FIMTDD … -e))` | -Z |
| Sgb(Oza) | `meta.StreamingGradientBoostedTrees -t -L 1.0 -m 75 -s 10 -l (meta.OzaBag -s 10 -l (trees.FIMTDD … -e))` | -Z |
| Sgb(Arf) | `meta.StreamingGradientBoostedTrees -t -L 1.0 -m 75 -s 10 -l (meta.AdaptiveRandomForestRegressor -s 10 -x (ADWINChangeDetector -a 0.001) -p (ADWINChangeDetector -a 0.01))` | -Z |
| Sgb(Srp) | `meta.StreamingGradientBoostedTrees -t -L 1.0 -m 75 -s 10 -l (meta.StreamingRandomPatches -s 10 -l (trees.FIMTDD … -e))` | -Z |
| OzaReg | `meta.OzaBag -s 100 -l (trees.FIMTDD … -e)` | -Z |
| ArfReg | `meta.AdaptiveRandomForestRegressor -s 100 -x (ADWINChangeDetector -a 0.001) -p (ADWINChangeDetector -a 0.01)` | -Z |
| SOKNL | `meta.SelfOptimisingKNearestLeaves -s 100 -l (SelfOptimisingBaseTree -s VarianceReductionSplitCriterion -g 50 -c 0.01) -x (ADWINChangeDetector -a 0.001) -p (ADWINChangeDetector -a 0.01)` | -Z |
| SrpReg | `meta.StreamingRandomPatches -s 100 -l (trees.FIMTDD … -e)` | -Z |
| FIRT-DD | `trees.FIMTDD -s VarianceReductionSplitCriterion -g 50 -c 0.01 -e` | none |
| HTR | `trees.HoeffdingRegressionTree -k -n HoeffdingNumericAttributeClassObserver -d HoeffdingNominalAttributeClassObserver` | none |
| Sgbt | `meta.StreamingGradientBoostedTrees -t -L 1.0 -m 75 -s 100 -l (trees.FIMTDD … -e)` | -Z |
| Axgb | `meta.AdaptiveXGBoostClassifier -s 10` | **none** |

Evaluators:
- Main runs: `EvaluatePrequentialRegression -e BasicRegressionPerformanceEvaluator -f 10000000 -q 10000000`. JVM `-Xmx48g -Xms50m -Xss1g` [CODE exp/exp_config.json:3-4].
- Fig.6: `-e (WindowRegressionPerformanceEvaluator -w 10000) -f 10000 -q 10000`, `-Xmx12g`, seeds 1–3, HyperA only, 4 learners [CODE exp/exp_config_overTime.json].
- §4.3 grids: `exp/exp_config_SGBT_OZA_parameter_search.json` (Tabs.5–6) and `…_LR_FP.json` (Fig.9); same FIMTDD string, Core-11, seeds 1–5.
- `exp_config_OZA_SGBT_parameter_search.json` runs an Oza(Sgbt) (E, S) grid that **the paper does not report**.

Reported metrics are the MOA CSV columns `adjusted coefficient of determination` and `evaluation time (wall) (seconds)`, i.e. MOA's internal wall clock, not the Python wrapper's timer [CODE exp/generateSummaryXls.py:48-51; moa/…/tasks/EvaluatePrequentialRegression.java:236].

### 11.2 Component defaults (effective values)

| Component | Effective setting | Source |
|---|---|---|
| FIMTDD with `-e` | regression tree (mean leaves, **no** linear models); grace 50; split conf 0.01; tie threshold 0.05; Page-Hinkley α 0.005, threshold 50; alternate-tree fading 0.995, Tmin 150, time 1500. **Nominal attributes are ignored** ("At this stage all nominal attributes are ignored") | [CODE moa/…/trees/FIMTDD.java:75-123, 305] |
| OzaBag (OzaReg) | λ **= 1.0 hard-coded**; Poisson k applied as **instance weight** (single `trainOnInstance` call, weight × k); mean aggregation; seed option `-Z` (default 1); `-p` (top-p) = 1.0 so all members vote | [CODE moa/…/meta/OzaBag.java] |
| ArfReg | base learner `ARFFIMTDD -s VarianceReductionSplitCriterion -g 50 -c 0.01`; **m = 60 % of features per split** (mode Percentage); λ = 6; ADWIN drift 1e-3, warning 1e-2; background learners on | [CODE moa/…/meta/AdaptiveRandomForestRegressor.java:55-86] |
| SrpReg | training method **Random Patches**; subspace **60 %** (Percentage); λ = 6 (Poisson k as weight); ADWIN drift 1e-5, warning 1e-4; mean aggregation for regression | [CODE moa/…/meta/StreamingRandomPatches.java:80-125, 169-228] |
| SOKNL | base `SelfOptimisingBaseTree -s VarianceReductionSplitCriterion -g 50 -c 0.01`; self-optimising on; m = 60 %; λ = 6; ADWIN 1e-3 / 1e-2 | [CODE moa/…/meta/SelfOptimisingKNearestLeaves.java:41-77] |
| HTR | no `-g`/`-c` passed ⇒ HoeffdingTree defaults: **grace 200, split confidence 1e-7**, tie 0.05; `-k` = mean leaves | [CODE moa/…/trees/HoeffdingTree.java:137-155; exp_config.json] |
| Sgbt | `-t` = single-threaded prediction; `-L` lr; `-m` feature %; `-s` steps; `-M 1` (train once); `-S 1` (no skipping); one-hot encoding of nominals **on** by default | [CODE SGBT.java:73-89, 311-332] |
| Axgb | `nEstimators` (-s) = 10; each window trains `XGBoost.train(…, 10 rounds)` ⇒ 10 trees per member; eta 0.3; max depth 6; window 1–1000; drift detection off; update strategy Replace; objective `reg:squarederror` for numeric targets | [CODE moa/…/meta/AdaptiveXGBoostClassifier.java:24-40, 174, 189, 297-298] |
| Evaluator R² | SS_res = Σ(y−ŷ)²; **SS_tot = Σ(y_i − ȳ_{<i})², where ȳ_{<i} is the running mean of targets seen before i (0 for the first instance)** | [CODE moa/…/evaluation/BasicRegressionPerformanceEvaluator.java:69-117] |
| Evaluator adjusted R² | n = total weight observed; **p = `inst.numAttributes()`, which includes the target** (p = #features + 1) | [CODE BasicRegressionPerformanceEvaluator.java:81, 120-122] |
| Windowed adjusted R² | same formulas over a sliding window; n = window weight (≤ 10,000) | [CODE moa/…/evaluation/WindowRegressionPerformanceEvaluator.java:120-200] |

### 11.3 Conflicts between paper text and code

| # | Paper says | Code does | Consequence |
|---|---|---|---|
| K-1 | Eq.2: target g/h (p.6) | Target = (y − raw)/1, i.e. the residual = −∂l/∂ŷ for l = ½(y−ŷ)². The code's "gradient" field already stores the *negative* gradient | Resolves Q-04: the residual is the correct target; Eq.2's sign is a notation issue |
| K-2 | Learning rate is a boosting hyperparameter (p.13, §4.3) | lr scales the running score **during training only**; prediction sums unscaled step outputs | With lr = 1.0 (all main results) training and prediction agree. With lr ≠ 1 they don't. **[INF] Likely explains Fig.9 (Q-23):** if each step fitted its target perfectly, prediction ≈ y·Σ_{s<10}(1−lr)^s → ≈ 2.0·y at lr 0.5 and ≈ 0.67·y at lr 1.5. Over-prediction by 2× gives large negative R̄² on targets far from 0 |
| K-3 | Bagging "λ parameter" causes "per-instance multiple training iterations" (p.14) | OzaBag and SRP pass Poisson k as a **weight in one call**. SGBT then **discards the incoming weight** (sub-instances get weight 1.0) | In Oza(Sgbt)/Srp(Sgbt), bagging reduces to "skip if k = 0": P = e^{−1} ≈ 0.37 for OzaBag, e^{−6} ≈ 0.0025 for SRP. The extra cost of Bag(Sgbt) is not from repeated training |
| K-4 | HTR uses grace 50, split conf 0.01 (pp.13–14) | HTR command passes neither ⇒ 200 and 1e-7 | HTR baseline (Tabs.1, 3) used MOA defaults. Reproduce with the code's command and flag it |
| K-5 | R² with global mean ȳ (Eq.U-8, p.14) | Prequential running mean in SS_tot | Reported R̄² values are MOA's version. Our evaluator must copy it, or recompute both |
| K-6 | p = input dimensions (Eq.U-9) | p = numAttributes incl. target | Negligible for large n; matters slightly for Abalone (n = 4,977) |
| K-7 | Sgbt base learners use an "internal Base Learner Replacement strategy" (p.6) | No replacement logic in SGBT itself | "Internal" = inside the base learner (FIMTDD alternate trees; ARF/SRP ADWIN background learners). OzaBag has no detector, so Sgb(Oza) adapts only through FIMTDD |
| K-8 | Bias–variance with "Sgb(Oza)", "Oza(Sgbt)" (Figs.7–8) | Bias–variance used **OzaBag -s 5** (E = 5), not 10 | Resolves Q-17 |
| K-9 | One seed per run | Seed reaches only the outermost learner. **[CODE-INF]** Inner learners keep their default seed 1, and all copies of an inner learner start from the same RNG state. So in Sgb(Oza) every boosting step's OzaBag draws the same Poisson sequence, and in Oza(Sgbt) all 10 Sgbt members pick the same feature subspaces, identical across seeds. Axgb, FIRT-DD and HTR get no seed (zero std in Tabs.8–9 is consistent with this) | Diversity is lower than the paper text implies; seed-to-seed variance comes only from the outer learner. Verify empirically (C-07) |
| K-10 | — | FIMTDD ignores nominal attributes; SGBT one-hot encodes nominals before passing them to FIMTDD | On DemandF (store_id, sku_id) and NZEnergy (PoC), Sgbt-based models see features the FIMTDD/OzaReg/SrpReg baselines ignore. Reported, not corrected, in the paper |

### 11.4 Resolution status of §10 questions

| ID | Status | Answer (source) |
|---|---|---|
| Q-01 | Partly | Final configs use all 16 datasets (`exp_config.json`, `generateSummaryXls.py:23`). "11" is a leftover of an earlier version. Scope decision stays with the human (H-01) |
| Q-02 | Resolved | Repo `abalone.arff` (`@relation data_res_abalone`, 8 anonymised numeric features + target) has 4,977 rows, and MOA output reports 4,977 classified instances. Use the repo file; it is not the raw UCI file |
| Q-03 | Open | Repo has a single `hyperA.arff.zip` (500,000 rows, 10 features) matching Tab.3. The Tab.1 HyperA run is not explained |
| Q-04 | Resolved | K-1 |
| Q-05 | Resolved | K-7 |
| Q-06 | Resolved | Initial raw score 0 [CODE SGBT.java:520-521] |
| Q-07 | Resolved | §5.0: per-step subspace drawn once, k = round(n·pct), all-combinations path for n ≤ 20 |
| Q-08 | Resolved | §5.0 / K-2: lr at training only; step output computed after training on the current instance |
| Q-09 | Resolved | OzaBag λ = 1 (hard-coded); SRP λ = 6 |
| Q-10 | Resolved | ArfReg m = 60 %/split, SrpReg 60 % random patches, ADWIN settings §11.2. The 75 % applies only at the Sgbt level; inner ensembles keep their own 60 % |
| Q-11 | Resolved | §11.2 FIMTDD row; MOA class `trees.FIMTDD -e` |
| Q-12 | Resolved | K-3: weight, single call |
| Q-13 | Resolved | No warm-up; every instance is tested then trained (`EvaluatePrequentialRegression` defaults) [CODE-INF] |
| Q-14 | Partly | No normalisation in the experiment pipeline. Nominals: one-hot inside SGBT, ignored by FIMTDD (K-10). Target = last attribute. DemandF and NZEnergy were built by `DemandFCreate.py` / `NZ_energyCreate.py` (MinMaxScaler is imported; not reviewed in detail) |
| Q-15 | Resolved | Sgbt baseline: lr 1.0, 75 %, 100 steps |
| Q-16 | Resolved | `meta.AdaptiveXGBoostClassifier` in the repo's MOA via xgboost4j 2.1.1 (§11.2) |
| Q-17 | Resolved | K-8: E = 5; iterations 5…100 step 5 [CODE exp/Bias_Variance_Decomp/BVDecompSyntheticLatest.py:96] |
| Q-18 | Resolved | Main runs record only the final row (`-f 10000000`). Fig.6 samples every 10,000. Wall time = MOA's internal wall clock (JVM start-up excluded [CODE-INF]) |
| Q-19 | Partly | E1–E6 use fixed ARFF files; seeds affect learners only. Generator parameters for HyperA/Friedman* are not in the repo. Drift-split files for bias–variance (`<Friedman*>_1…_10`, test file `_12`) are **not** in the repo |
| Q-20 | Resolved | 10-fold `KFold` (no shuffle); per fold `bias_variance_decomp(loss='mse', num_rounds=10, random_seed=42)`, which bootstraps (and so reorders) training data; bias and variance averaged over folds, then square-rooted [CODE BVDecompSyntheticLatest.py:37-80] |
| Q-21 | Resolved | K-5, K-6 |
| Q-22 | Partly | Post-hoc inputs (`exp/post_hoc_new/`) hold 80 blocks = 16 datasets × 5 seeds for 6 methods (incl. Sgb(Arf)), so each (dataset, seed) is likely a separate block [CODE-INF]. The statistics tool itself is not in the repo |
| Q-23 | Explained [INF] | K-2 |
| Q-24 | Open | Not in repo |
| Q-25–27 | Unchanged | Editorial |

### 11.5 Reference results shipped in the repo

`exp/post_hoc_new/<dataset>_<seed>/<method>.csv` holds the **final MOA rows for 6 methods** — Oza(Sgbt), Sgb(Oza), Sgb(Arf), OzaReg, ArfReg, SOKNL — on all 16 datasets × seeds 1–5. Their means match Tab.3/Tab.4 after rounding (e.g. Sgb(Oza) Abalone R̄² 0.483 vs 0.48, wall 1.9 s vs 1.9 s; NZEnergy 0.977 vs 0.98). These are the authors' raw numbers and the best validation targets for those 6 methods. Bias–variance raw curves are in `exp/Bias_Variance_Decomp/RESULTS/*.csv`; Fig.2's Ailerons start point (√bias 0.0499, √var 0.0470 at 5 steps) matches `BVDecompose_Results_ailerons.csv`.

### 11.6 Datasets in the repo

| Dataset | In repo | Rows (data lines) | Attributes incl. target | Nominal attrs |
|---|---|---|---|---|
| Ailerons, Elevators, Fried, House8L, MetroTraffic, Abalone, Bike, FriedmanLea/Gra/Gsg | plain ARFF | match Tab.2 | match Tab.2 + 1 | 0 |
| HyperA | `hyperA.arff.zip` | 500,000 | 11 | 0 |
| DemandF | `DemandF.arff.zip` (+ `DemandFnotNull`, raw CSV, build script) | 150,151 lines; MOA classified 150,150 | 9 | 2 (store_id, sku_id) |
| NZEnergy | `NZEnergy.arff.zip` (+ raw CSV, build script) | 3,100,667 lines; MOA classified 3,100,666 (Tab.2: 3,100,660) | 13 | 1 (PoC) |
| SUP2I, SUP3A, SUP3G | **missing**. README: "please contact authors" | – | – | – |

The README also says SGBR is now in upstream MOA (2025-08-30) and CapyMOA (2025-09-13). Those versions **may differ** from commit `f62f7b4` (e.g. K-2, K-3). For fidelity, use the repo commit.
