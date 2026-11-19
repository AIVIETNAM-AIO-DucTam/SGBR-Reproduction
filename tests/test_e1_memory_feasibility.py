import json
import os
import signal
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


with patch.object(sys, "path", [str(Path(__file__).resolve().parents[1] / "scripts"), *sys.path]):
    from e1_memory_feasibility import measure_java, memory_deltas, memory_snapshot


class E1MemoryFeasibilityTest(unittest.TestCase):
    def test_reports_exit_and_rejects_partial_evaluator_output(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            manifest = work / "manifest.json"
            for rows, expected in ((8, "completed"), (7, "incomplete_stream")):
                with self.subTest(rows=rows):
                    program = (
                        "from pathlib import Path; "
                        f"Path('evaluation.csv').write_text('learning evaluation instances\\n{rows}\\n')"
                    )
                    result = {"command": [sys.executable, "-c", program], "dataset": {"expected_instances": 8}}
                    measure_java(manifest, result, work, {"limits": []}, None, os.environ)
                    self.assertEqual(result["status"], expected)
                    self.assertEqual(result["exit_code"], 0)
                    self.assertIsNone(result["termination_signal"])
                    self.assertGreater(result["peak_java_rss_bytes"], 0)
                    self.assertGreaterEqual(result["wall_clock_seconds"], 0)

    def test_timeout_and_jvm_oom_are_distinct(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            for program, timeout, expected in (
                ("import time; time.sleep(10)", 0.05, "timed_out"),
                ("raise SystemExit('java.lang.OutOfMemoryError: Java heap space')", None, "oom_observed"),
            ):
                with self.subTest(expected=expected):
                    result = {"command": [sys.executable, "-c", program], "dataset": {"expected_instances": 8}}
                    manifest = work / "manifest.json"
                    measure_java(manifest, result, work, {"limits": []}, timeout, os.environ)
                    self.assertEqual(result["status"], expected)
                    checkpoint = json.loads(manifest.read_text())
                    self.assertEqual(checkpoint["status"], "running")
                    if expected == "timed_out":
                        self.assertEqual(result["termination_signal"], signal.SIGKILL)
                        self.assertFalse(result["oom"]["java_reported"])
                    else:
                        self.assertEqual(result["exit_code"], 1)
                        self.assertTrue(result["oom"]["java_reported"])

    def test_preserves_existing_cgroup_peak_and_counts_new_oom_events(self):
        with TemporaryDirectory() as directory:
            group = Path(directory)
            groups = {"limits": [{"path": str(group), "memory.max": "1073741824"}]}
            (group / "memory.peak").write_text("500\n")
            events = group / "memory.events"
            events.write_text("oom 4\noom_kill 2\n")
            before = memory_snapshot(groups)
            events.write_text("oom 5\noom_kill 3\n")
            after = memory_snapshot(groups)
            self.assertEqual(before[str(group)]["peak_bytes"], 500)
            self.assertEqual(after[str(group)]["peak_bytes"], 500)
            self.assertEqual(memory_deltas(before, after), {str(group): {"oom": 1, "oom_kill": 1}})


if __name__ == "__main__":
    unittest.main()
