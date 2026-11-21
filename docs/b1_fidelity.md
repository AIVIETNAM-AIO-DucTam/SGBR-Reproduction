# C-21 B1 fidelity gate

**Launch is pending human approval.** Generating the manifest and report does not start MOA. The approved scope comes from [reproduction plan §§12–13](reproduction_plan.md#12-next-batch-b1-fidelity-gate-smallest-scientifically-meaningful-batch).

## Plan and evidence

The [generated manifest](../results/manifest/b1_cells.json) contains 90 B1-a original-seed comparisons, 18 B1-b seed-1 repeats and 12 B1-c unseeded runs. Each dataset is read directly from the pinned authors' Git blob and checked against its SHA-256 and approved row count. The upstream E1 JSON supplies learner and evaluator strings, including their spacing and outermost seed flag. The runner uses JDK 11 and `-Xmx16g -Xms50m -Xss1g` with the JVM's default GC. B1-a, B1-b and B1-c all use one JVM at a time. B1-b stays serial while Q-37 is open.

The `exp` identity is `B1-a`, `B1-b`, `B1-c-r1` or `B1-c-r2`. The last two IDs preserve the two unseeded attempts in distinct paths with `seed=none`. B1-d compares existing B0 evidence and schedules no JVM. Supply the original NZEnergy `evaluation.csv` from the completed Kaggle B0 run via `--b0-csv`. The committed B0 manifest verifies the run identity and completion, but does not contain the evaluator row. The runner leaves B1-d pending without that CSV. The approved B0 closeout remains recorded in the reproduction plan.

The [comparison CSV](../results/summary/B1_parity.csv) and [gate summary](../results/summary/B1_gate.json) are currently reference-only. The CSV leaves observed values blank until it has a successful, validated evaluator CSV. A run that exits before processing all expected rows cannot contribute result values.

## Kaggle preparation

1. Use a private Kaggle notebook with **Accelerator → None**. Make the project checkout available in the notebook. If checking out the private repository online, use the existing private-checkout flow in the [integrated notebook](../notebooks/SGBR_C01_E1_Integrated.ipynb) with the Kaggle Secret `GITHUB_TOKEN`, scoped **Contents: Read**. Running the integrated pipeline itself would start E1, so stage the existing B0 jar and its `moa_build.json` or environment manifest for B1.
2. Stage the JDK 11 runtime, fat jar, corresponding build provenance, and B0 evaluator CSV. Prefer the B0 jar. If a rebuild is necessary, use the pinned source and authors' Maven build documented in the [C-01 audit](kaggle_environment_audit.md). Keep the same jar digest, build and runtime JDK, and default GC across resumed B1 sessions. The runner verifies the pinned source revision and recorded jar SHA-256 before launching a cell. Kaggle CPU models are recorded separately.
3. Enable Internet to fetch the public upstream commit, or stage a Git checkout already containing that commit. Use a writable results directory. Before resuming in a new session, restore the same results directory, including completed records and their adjacent CSVs, and use the same executable and jar paths to retain matching command hashes. Run one B1 session against a given results directory. Avoid other active workloads during B1-a wall-time measurement.

In a Kaggle shell cell, set paths to your staged inputs. The commands below only prepare or report evidence.

```bash
PROJECT=/kaggle/working/SGBR-Reproduction
UPSTREAM=/kaggle/working/sgbr-authors
OUT=/kaggle/working/results
PIN=f62f7b437512e020f57c4bcd03884c4724eda5b1

# Omit these two Git commands if a staged checkout already contains PIN.
git init -q "$UPSTREAM"
git -C "$UPSTREAM" fetch --depth=1 https://github.com/nuwangunasekara/SGBR.git "$PIN"

python "$PROJECT/scripts/b1_fidelity.py" --upstream-checkout "$UPSTREAM" --results "$OUT" manifest
python "$PROJECT/scripts/b1_fidelity.py" --upstream-checkout "$UPSTREAM" --results "$OUT" report
```

### Launch command for use after approval

Set `JAVA11`, `MOA_JAR` and `MOA_PROVENANCE` to the staged files. Set `B0_CSV` to the completed B0 evaluator CSV. Set `SESSION_ID` to a distinct, non-secret label for the Kaggle session. Choose `SESSION_BUDGET_SECONDS` below the remaining time to leave room for output export. Keep this cell unexecuted until launch is approved.

```bash
python "$PROJECT/scripts/b1_fidelity.py" --upstream-checkout "$UPSTREAM" \
  --results "$OUT" --b0-csv "$B0_CSV" run --approved \
  --java "$JAVA11" --moa-jar "$MOA_JAR" --jar-provenance "$MOA_PROVENANCE" \
  --session-id "$SESSION_ID" --session-budget-seconds "$SESSION_BUDGET_SECONDS"
```

If the B0 CSV is still unavailable, omit `--b0-csv` and supply it when generating the report later. Use **Save Version → Run All** only after approval and export the results directory. Resume with the same launch command and a new session ID. The per-cell hash binds the exact command, JVM and jar identity, and pinned dataset and config digests. The runner skips a completed cell only with matching evidence. Incomplete cells restart at the beginning, with previous attempt files retained. The lock prevents another invocation from starting cells in the same results directory.

## Review outputs

- `results/raw/<exp>/<dataset>/<method_key>/seed=<k>.json` contains the exact command and hash, provenance, session and CPU information, row counts, final metric and timings, peak Java RSS, exit status and signal. The evaluator CSV is adjacent. Each attempt has its own Java log, resource samples and checkpoint.
- `results/logs/B1/*.jsonl` records session, cell, skip and stop events.
- `results/summary/B1_parity.csv` shows per-cell R̄² delta and σ (MOA internal wall time divided by the authors' MOA wall time). It retains CPU model, concurrency and peak RSS. For seed-1 repeats, the numerical reference is the B1-a result and the wall reference remains the authors' seed-1 CSV.
- `results/summary/B1_gate.json` records the §12 verdict, B1-a median and inclusive-quartile IQR by CPU model and concurrency, and observed versus reference pairwise seed differences. Fewer than two ratios in a group leave its IQR blank. The report compares seed contrasts at 1e-6 for diagnosis.
- Determinism compares the IEEE-754 bits of the final evaluator's predictive fields and classified count. Wall time, CPU time and resource measurements are excluded. The paper's rounded Table 3 values for B1-c are reported separately and are informative.
- A numerical failure, confirmed row-count mismatch or non-determinism stops further launches. Missing evidence leaves the gate incomplete. OOM, timeout and interruption preserve evidence and stop the current invocation. Review the attempt before retrying. A tolerance pass requires opening a question on the environment difference. Q-37, Q-38 and Q-39 remain open.

## Local validation

The fixture `tests/fixtures/b1_moa_evaluator.csv` was emitted by the pinned Java evaluator for eight synthetic target/prediction pairs with three attributes including the target. The Python running-mean implementation matches its adjusted R̄² bit-for-bit. This fixture never enters the B1 result set.
