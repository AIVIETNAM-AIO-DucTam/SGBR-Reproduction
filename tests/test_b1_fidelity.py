import csv
import io
import json
import os
import shlex
import struct
import sys
import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
    import b1_fidelity as b1


def config():
    return {
        "datasets": list(b1.COUNTS), "random_seeds": [1, 2, 3, 4, 5], "streams": {},
        "learners": [
            [name, "Z", "meta.ExactOptions  -l (base.Exact -q 1)"] for name in b1.METHOD_FILES
        ] + [[name, "", f"trees.{name} -q 1"] for name in b1.TABLE3],
        "java_options": "-Xmx48g -Xms50m -Xss1g moa.DoTask",
        "evaluator": "EvaluatePrequentialRegression -e BasicRegressionPerformanceEvaluator  -f 10000000 -q 10000000",
    }


def metrics(r2="0.5", count=4977, wall="4"):
    return {**dict.fromkeys(b1.PREDICTIVE_COLUMNS, "0.5"), b1.R2: r2,
            b1.CLASSIFIED: str(count), b1.WALL: wall}


def evaluator_csv(file, row):
    with file.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["learning evaluation instances", *row])
        writer.writeheader()
        writer.writerow({"learning evaluation instances": row[b1.CLASSIFIED], **row})


class B1FidelityTest(unittest.TestCase):
    def test_approved_matrix_and_unique_repeat_ids(self):
        cells = b1.matrix(config())
        self.assertEqual(len({cell.path for cell in cells}), 120)
        self.assertEqual(Counter(cell.exp for cell in cells),
                         {"B1-a": 90, "B1-b": 18, "B1-c-r1": 6, "B1-c-r2": 6})
        self.assertEqual({cell.seed for cell in cells if cell.exp == "B1-a"}, {1, 2, 3, 4, 5})
        self.assertEqual({cell.seed for cell in cells if cell.exp == "B1-b"}, {1})
        self.assertEqual({cell.seed for cell in cells if cell.exp.startswith("B1-c")}, {None})
        self.assertTrue(all(cell.exp != "B1-d" for cell in cells))
        self.assertEqual(cells[0].ref_source, "exp/post_hoc_new/abalone_1/Oza(SGBT).csv")
        planned = json.loads((ROOT / "results/manifest/b1_cells.json").read_text())
        self.assertEqual([row["record_path"] for row in planned["cells"]],
                         [f"results/raw/{cell.path.as_posix()}" for cell in cells])

    def test_command_preserves_original_strings_and_seed_scope(self):
        conf = config()
        method = next(iter(b1.METHOD_FILES))
        command = b1.e1.e1_command(conf, "abalone", method, 2, "/jdk/bin/java", "/data/moa.jar")
        self.assertEqual(command[3:7], ["-Xmx16g", "-Xms50m", "-Xss1g", "moa.DoTask"])
        self.assertEqual(command[-1],
                         conf["evaluator"] + " -s (ArffFileStream -f stream.arff) "
                         "-l (meta.ExactOptions  -l (base.Exact -q 1) -Z 2) -d evaluation.csv")
        no_seed = b1.e1.e1_command(conf, "abalone", "HT", 1, "java", "moa.jar")
        self.assertNotIn(" -Z ", no_seed[-1])

    def test_decimal_boundaries_and_failed_row_count(self):
        ref = metrics()
        for value, verdict in (("0.500001", "Exact"), ("0.50000101", "Tolerance pass"),
                               ("0.495", "Tolerance pass"), ("0.4949999", "Fail")):
            with self.subTest(value=value):
                self.assertEqual(b1.parity(metrics(value), ref), verdict)
        self.assertEqual(b1.parity(metrics(count=4976), ref), "Fail")
        self.assertEqual(b1.parity(None, ref), "Incomplete")
        self.assertEqual(b1.gate_verdict([{"verdict": "Exact"}] * 120), "Incomplete")
        self.assertEqual(b1.gate_verdict([{"verdict": "Exact"}] * 121), "Exact")
        self.assertEqual(b1.gate_verdict([{"verdict": "Exact"}] * 120 + [{"verdict": "Tolerance pass"}]),
                         "Tolerance pass")
        self.assertEqual(b1.gate_verdict([{"verdict": "Fail"}, {"verdict": "Incomplete"}]), "Fail")

    def test_determinism_excludes_timing_but_compares_predictive_bits(self):
        self.assertTrue(b1.bits_match(metrics("0.5", wall="3"), metrics("0.500", wall="4")))
        self.assertFalse(b1.bits_match(metrics("0.5"), metrics("0.5000000000000001")))
        self.assertFalse(b1.bits_match(metrics("0"), metrics("-0")))

    def test_running_mean_adjusted_r2_matches_moa_evaluator_fixture(self):
        target = [3, 1, 4, 1, 5, 9, 2, 6]
        predicted = [2, 2, 3, 1, 6, 7, 3, 5]
        with (ROOT / "tests/fixtures/b1_moa_evaluator.csv").open(newline="") as file:
            moa = float(next(csv.DictReader(file))[b1.R2])
        computed = b1.adjusted_r2(zip(target, predicted), num_attributes=3)
        self.assertEqual(struct.pack(">d", computed), struct.pack(">d", moa))

    def test_per_cell_checkpoint_and_resume_evidence(self):
        with TemporaryDirectory() as directory:
            raw = Path(directory)
            conf = config()
            cell = b1.matrix(conf)[0]
            command = b1.e1.e1_command(conf, cell.dataset, cell.method_key, cell.seed, "java", "moa.jar")
            evidence = {"expected_instances": 4977, "sha256": "a" * 64}
            runtime = {
                "jar_sha256": "b" * 64, "build_jdk": "11", "java_version": "11", "gc": "G1GC",
                "xmx": "16g", "cpu_model": "fixture", "session_id": "test", "concurrency": 1,
            }
            config_hash = "c" * 64
            identity = b1.command_identity(command, runtime, evidence["sha256"], config_hash)
            path = raw / cell.path

            def monitor(checkpoint, result, attempt, groups, timeout, env, **options):
                self.assertTrue(path.is_file())
                self.assertEqual(json.loads(path.read_text())["reason"], "attempt_not_finalized")
                self.assertEqual(options["pass_fds"], (7,))
                evaluator_csv(attempt / "evaluation.csv", metrics())
                result.update(status="completed", exit_code=0, termination_signal=None,
                              peak_java_rss_bytes=123, wall_clock_seconds=5,
                              oom={"java_reported": False}, processed_instances=4977)

            with patch.object(b1.e1, "measure_java", side_effect=monitor):
                record = b1.run_cell(path, cell, command, identity, b"ARFF format",
                                     evidence, runtime, os.environ, {}, None, False, 7)
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["command_line"], shlex.join(command))
            self.assertEqual(record["command_hash"], identity)
            data = {"abalone": (b"ARFF format", evidence)}
            self.assertEqual(b1.load_records(raw, [cell], data, conf, config_hash)[cell.path], record)

            evaluator_csv(path.with_suffix(".csv"), metrics("0.51"))
            with self.assertRaisesRegex(ValueError, "verified evaluator CSV"):
                b1.load_records(raw, [cell], data, conf, config_hash)

            record["cell"]["seed"] = 5
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "identity"):
                b1.read_record(path, cell)

    def test_scheduler_skips_matching_completion_and_stops_on_parity_failure(self):
        with TemporaryDirectory() as directory:
            results = Path(directory)
            conf = config()
            config_bytes = json.dumps(conf).encode()
            cells = b1.matrix(conf)
            first, next_cell = cells[:2]
            data = {
                name: (b"fixture", {"expected_instances": count, "sha256": "a" * 64})
                for name, count in b1.COUNTS.items()
            }
            refs = {cell.path: metrics(count=b1.COUNTS[cell.dataset])
                    for cell in cells if cell.exp == "B1-a"}
            runtime = {
                "jar_sha256": "b" * 64, "build_jdk": "11", "java_version": "11", "gc": "G1GC",
                "xmx": "16g", "cpu_model": "fixture", "session_id": "test", "concurrency": 1,
            }
            command = b1.e1.e1_command(conf, first.dataset, first.method_key, first.seed, "java", "moa.jar")
            digest = b1.command_identity(command, runtime, "a" * 64, b1.sha256(config_bytes))
            cached = {**runtime, "status": "completed", "metrics": metrics(),
                      "peak_rss_bytes": 100, "command_hash": digest}
            divergent = {**cached, "metrics": metrics("0.51"), "reason": None}
            options = SimpleNamespace(results=results, session_budget_seconds=None,
                                      cell_timeout_seconds=None, session_id="test")
            b0 = b1.b0_row(None, metrics(count=3100666))
            with (
                patch.object(b1, "load_records", return_value={first.path: cached}),
                patch.object(b1, "java_runtime", return_value=("java", "moa.jar", {}, runtime)),
                patch.object(b1, "run_cell", return_value=divergent) as launch,
            ):
                self.assertEqual(b1.execute(options, conf, config_bytes, cells, data, refs, b0, 7), 1)
            launch.assert_called_once()
            self.assertEqual(launch.call_args.args[1], next_cell)
            report = json.loads((results / "summary/B1_gate.json").read_text())
            self.assertEqual(report["verdict"], "Fail")
            self.assertEqual(report["completed_b1_runs"], 2)
            logs = next((results / "logs/B1").glob("*.jsonl")).read_text()
            self.assertIn('"event": "cell_skipped"', logs)
            self.assertIn('"event": "gate_failed"', logs)

    def test_reference_only_row_does_not_impute_observations(self):
        cell = b1.matrix(config())[0]
        ref = metrics()
        row = b1.report_row(cell, None, ref, cell.ref_source, "Incomplete", ref)
        self.assertIsNone(row["r2"])
        self.assertIsNone(row["wall"])
        self.assertIsNone(row["sigma"])
        self.assertEqual(row["r2_ref"], ref[b1.R2])

    def test_malformed_or_nonfinite_csv_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing valid"):
            b1.final_metrics(io.StringIO("classified instances\n4977\n"))
        with TemporaryDirectory() as directory:
            path = Path(directory, "bad.csv")
            evaluator_csv(path, metrics("NaN"))
            with path.open() as file, self.assertRaisesRegex(ValueError, "nonfinite"):
                b1.final_metrics(file)


if __name__ == "__main__":
    unittest.main()
